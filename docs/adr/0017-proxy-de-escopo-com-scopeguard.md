# 0017. Proxy de escopo com ScopeGuard

- **Status:** Proposto
- **Data:** 2026-11-13
- **Origem:** Spike M0 ([2026-11-13-m0-zap.md](../spikes/2026-11-13-m0-zap.md), Q4, Q6, Q7 e seção 6); detalha o [ADR 0008](0008-escopo-em-tres-camadas.md); itens A-08 e A-18 da [revisão de QA](../reviews/2026-11-13-qa-m1-m2.md). Dependência nova (mitmproxy): este ADR é o registro exigido por `CLAUDE.md`.

## Contexto

O [ADR 0008](0008-escopo-em-tres-camadas.md) prevê o escopo em três camadas: `ScopeGuard` na CLI, ZAP protegido e proxy de saída. O spike M0 mediu o que cada uma garante de fato:

- **A varredura ativa do ZAP ignora o contexto.** Numa varredura de uma única requisição `GET /books/v1`, com o contexto restrito a `/books/v1.*`, 288 de 467 requisições saíram para caminhos fora da regra (`/WEB-INF/web.xml`, `/.git/config`, `/latest/meta-data/`, `/server-status`). O ZAP também troca o método por conta própria (um `POST` aprendido gera `GET`; nós `DELETE` aprendidos geram centenas de `DELETE`). O modo protegido não bloqueia `accessUrl` nem tráfego pelo proxy fora do contexto.
- **O Squid só decide por host e porta.** Em HTTP não vê o caminho que o ScopeGuard permitiu; em HTTPS só vê `CONNECT host:porta`, de modo que caminho e método ficam fora de qualquer controle de rede em ambiente de teste real (que é HTTPS). Observou-se ainda 20 túneis `CONNECT vampi:5000` permitidos.
- **Os padrões do ZAP saturam o alvo** (32 threads por host, sem duração máxima, sem atraso), e nada na pilha limitava taxa nem duração do que sai.

Resultado: sem uma camada que veja caminho e método, o escopo de caminho "não tem dono" (spike, seção 7, risco 3). Essa camada precisa ser a **mesma** regra que a CLI aplica, e não uma segunda implementação, para que as duas nunca divirjam.

## Decisão

Vamos substituir o proxy de saída Squid por um **proxy de escopo** (`scope-proxy`): mitmproxy fixado (12.3.1) com um addon fino que chama o `ScopeGuard` para **toda** requisição de saída.

1. **Uma só implementação de escopo.** A decisão de cada requisição é `ScopeGuard.ensure_allowed(método, URL)`, o código de domínio já testado e com falha fechada. O proxy só acrescenta recusas (prazo, trava de emergência, endereço resolvido, taxa, `Upgrade`, `Host` incoerente); nunca permite o que o `ScopeGuard` recusa. Um teste de propriedade verifica que o decisor do proxy e o `ScopeGuard` nunca divergem.
2. **HTTPS com interceptação de TLS.** O `CONNECT` é decidido por host e porta; o proxy então intercepta o TLS e decide cada requisição interna com URL completa, caminho e método. A CA de interceptação nasce ao iniciar o contêiner, em tmpfs.
3. **Política por execução, em arquivo.** JSON validado (`schema_version`, `run_id`, `scope`, `limits`, `not_after`), montado somente leitura. Sem política válida o proxy não sobe; não existe política padrão. A CLI gerará o arquivo a partir do perfil (não faz parte deste ADR a geração).
4. **Falha fechada para o que não se inspeciona:** TCP cru, HTTP/2, `Upgrade` (WebSocket, h2c) e UDP são recusados; opções inseguras do mitmproxy fazem o addon se recusar a iniciar.
5. **Taxa por atraso, não por falha**, com fila limitada; prazo absoluto (`not_after` e duração máxima); **trava de emergência** por arquivo `KILL` no diretório da política, **permanente até reiniciar** (justificativa no README do proxy).
6. **Trilha de auditoria** (JSON, uma linha por decisão, só nomes de parâmetros de consulta, sem cabeçalhos nem corpos), em pasta do host e na saída padrão; falha de gravação trava a execução.
7. **Endereço resolvido:** os endereços do DNS são conferidos antes de conectar (sem `allow_local`, só globais; link-local e metadados nunca) e o IP conferido é o IP usado na conexão.
8. **Verificação de certificado do destino ligada por padrão;** a política só pode desligá-la quando todas as regras têm `allow_local: true`.
9. A lógica pura mora em `src/harness_dast/adapters/scope_proxy/` (sem mitmproxy, testada no host); a cola em `docker/scope-proxy/addon.py`. O mitmproxy vive **só na imagem** e não é dependência da CLI.
10. Limites de memória e de processos para todos os serviços do `compose.yaml` (item A-18).

## Alternativas consideradas

- **Squid com `urlpath_regex` (só HTTP).** Resolveria caminho para HTTP, mas é uma segunda implementação da semântica de escopo (regex no lugar dos padrões e da normalização do ScopeGuard, com risco de divergência e de contornos por codificação), não filtra por método de forma equivalente e, em HTTPS sem interceptação, continua cego a caminho e método. Interceptar TLS no Squid (`ssl_bump`) exigiria compilação específica e daria uma terceira implementação de política. Descartado.
- **Script do ZAP (camada 2).** O código rodaria dentro do processo que queremos conter: um defeito ou uma configuração errada do ZAP o desligaria junto, e não cobre o tráfego que o ZAP não passa pelo seu pipeline (`accessUrl`, API). Fica a ideia de reforço futuro, não de substituição.
- **Confiar só no contexto do ZAP.** Medido no spike: não contém o varredor.
- **Escrever um proxy próprio em Python (asyncio).** Daria controle total, mas obrigaria a implementar interceptação de TLS, parser HTTP/1 seguro e emissão de certificados: superfície grande e sensível a contrabando de requisições. O mitmproxy já faz isso e é amplamente usado; reutilizamos o parser e escrevemos só a decisão.
- **Outros proxies de interceptação** (Envoy com `ext_authz`, Squid com `ssl_bump`): exigem mais configuração e uma ponte de decisão fora do Python; sem ganho sobre o mitmproxy para o nosso caso.

## Consequências

- **Fica mais fácil:** o escopo de caminho e método passa a ter dono e valer para tudo que sai, inclusive o que o varredor inventa e o HTTPS de ambientes reais; há prova auditável do que foi enviado e do que foi negado. Mudança no `ScopeGuard` vale no proxy na próxima construção da imagem.
- **Dependência nova (mitmproxy 12.3.1)**, licença MIT; mantida pelo projeto mitmproxy (versão de outubro de 2026). Fixada com hashes em `docker/scope-proxy/requirements.txt`; atualizar exige repetir as provas do lab, porque nomes de hooks e opções mudam entre versões. Alternativa de dependência rejeitada: Squid com `ssl_bump` (acima). Base `python:3.13-slim-bookworm` fixada por digest.
- **Interceptação de TLS:** o proxy vê corpos e cabeçalhos em claro (dados de teste sintéticos, ver `CLAUDE.md` Parte B). A CA é efêmera (tmpfs) e não sai do contêiner. O ZAP 2.17.0 aceitou o certificado interceptado sem importar a CA: ele não valida o certificado do que está no túnel, de modo que a autenticidade do destino passa a depender da verificação do proxy (ligada por padrão) e do isolamento da rede `zap_net`.
- **Riscos residuais** (detalhe no README do proxy): HTTP/2, WebSocket, TCP cru e UDP são recusados e não filtrados (um alvo que exija HTTP/2 não funciona); DNS de um nome permitido que aponte para outro IP público continua permitido (o ScopeGuard decide por nome); o motivo da recusa é classificado pela mensagem do ScopeGuard (que não expõe código); a política só é lida ao iniciar; a trava não corta conexões em andamento; o proxy só vale para quem o usa, e o isolamento real continua sendo a rede `internal`.
- **Custo:** um contêiner Python/mitmproxy (cerca de 60 MiB em repouso) no lugar do Squid; latência de poucos milissegundos por requisição (medida em 5 a 20 ms com o VAmPI); a taxa máxima passa a ser imposta (padrão do perfil, teto 50 req/s), o que alonga varreduras.
- **A fazer depois:** gerar o `policy.json` por execução e acionar a trava pela CLI (marcos de execução); copiar a trilha ao fim da execução; decisão sobre alvos corporativos em IP privado (M7), que agora se expressa com `allow_local` por regra em vez de uma lista de exceção do Squid; revisar a aceitação deste ADR por uma pessoa antes do primeiro commit.
- O [ADR 0008](0008-escopo-em-tres-camadas.md) recebe uma nota apontando para este; a camada 3 continua sendo "rede interna e proxy de saída com lista", agora com decisão por requisição.
