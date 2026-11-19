# 0122. Nuclei restrito a exposições conhecidas

- **Status:** Proposto
- **Data:** 2026-11-19
- **Origem:** Spike do Nuclei de 2026-11-19 ([relatório na branch `spike/nuclei`](https://github.com/MarcosQuintino0/harness-dast/blob/spike/nuclei/docs/reviews/2026-11-19-spike-nuclei.md)). Decisão do dono, depois do spike, de seguir só com o módulo de exposições. Relaciona-se com o [ADR 0102](0102-inventario-de-versoes-e-documentacao.md) (inventário), o [ADR 0120](0120-pedido-minimo-com-padroes-e-aprovacao.md) (pedido mínimo) e o [ADR 0121](0121-digests-empacotados-e-build-so-no-clone.md) (digests empacotados).

## Contexto

O ZAP ataca o que o contrato descreve, mas não procura o que o produto deixou exposto fora dele: o Actuator do Spring Boot aberto, arquivos de configuração, painéis e documentação. O inventário do ADR 0102 cobre só versões irmãs e a documentação da API. O Nuclei, da ProjectDiscovery (licença MIT), traz milhares de modelos de assinatura para essa classe de falha.

O spike mediu o Nuclei como segundo motor geral atrás da cerca, nos três alvos do laboratório e num alvo Spring Boot com Actuator aberto, montado para a prova:

| Critério | Medida | Resultado |
| --- | --- | --- |
| Ganho real | 0 achados exclusivos na Clínica Piloto, no VAmPI e no crAPI. No alvo Spring: 0 com a seleção estrita do plano e 13 com a seleção relaxada (`env`, `configprops`, `beans`, `mappings`, `threaddump` e outros) | Só em parte |
| Escopo | Pedidos do Nuclei iguais às linhas da auditoria em 13 execuções e nenhum fora da cerca. `Host` divergente e redirecionamento para fora foram negados. A rede interna não resolve nomes externos | Atendido |
| Ruído | 0 achados médios ou maiores falsos no VAmPI e no crAPI | Atendido |
| Tempo | Máximo de 10 s (321 modelos, 329 pedidos, `-rl 50`) | Atendido |
| Custo-benefício | ZAP com as regras 40034 e 40035 religadas: 0 achados nos 4 alvos, inclusive no Actuator aberto | O Nuclei só ganha na classe de exposições |
| Login | Token ausente de argumentos, logs e artefatos nos dois caminhos medidos | Atendido, com ressalvas |

O spike também mostrou três falhas no desenho original:
- Os modelos do Actuator ficam em `http/misconfiguration/springboot/`, fora de `http/exposures/`, de onde a lista saía.
- Eles usam `stop-at-first-match`, que a seleção estrita rejeitava: só 1 dos 33 modelos Spring entrava, e 29 caberiam inteiros sem essa recusa.
- O contêiner travou na partida em 3 execuções quando a entrada padrão ficou aberta.

Sem decisão, o hdast continua sem detectar uma classe real e comum de exposição, e o ZAP religado não a cobre.

## Decisão

Vamos acrescentar o Nuclei como **módulo de exposições conhecidas**, não como segundo motor geral. Ele roda só modelos de leitura que procuram arquivos, painéis e endpoints de gerência expostos.

### Imagem e manifesto
- A imagem `docker/nuclei` traz o binário do Nuclei e os modelos `nuclei-templates` em versões fixas. Cada versão tem pelo menos duas semanas de publicação e SHA-256 conferido contra o arquivo de checksums da própria release. O spike usou o Nuclei v3.11.1 e os modelos v10.5.1.
- O usuário não é root, não há atualização em execução e a imagem entra no `images.lock.json` com `schema_version` 2, estendendo o ADR 0121.
- O build gera um **manifesto** com o arquivo, o SHA-256, os métodos e os caminhos literais de cada modelo admitido. A CLI decide pelo manifesto e nunca lê os modelos em tempo de execução.

### Modelos admitidos
- Só das pastas `http/exposures/` e `http/misconfiguration/`, só HTTP, e só modelos cujos pedidos todos sejam `GET`, `HEAD` ou `OPTIONS`.
- Ficam vetados: `unsafe` e `raw`, `code`, `headless`, OAST (`interactsh`), os modelos DAST e de fuzz, e as etiquetas `dos`, `intrusive`, `bruteforce`, `fuzz` e `default-logins`.
- A projeção aceita chaves sem efeito no tráfego, como `stop-at-first-match`, e trata o `{{BaseURL}}` puro como `/`.
- Um caminho que o perfil recusa por desenho (com `;`, `..` ou codificação como `%72`) não entra na lista. O modelo continua rodando, a cerca nega esse pedido e a auditoria o registra.

### Lista de exposições e escopo
- O manifesto gera a lista literal de caminhos `GET`, sem curinga e sem `heapdump`, despejos de memória ou downloads grandes.
- Quando a carta, a resposta da pessoa ou o padrão do pedido mínimo a ligam, a CLI soma essa lista ao escopo como regras literais `GET` (no limite de 200 caminhos por regra).
- A lista entra na impressão digital da aprovação. A pessoa vê e aprova esses caminhos no `hdast setup`. Neste ponto este ADR substitui o ADR 0102, que deixava a documentação exposta como checagem própria fora da aprovação.
- Só rodam os modelos que, com a lista somada, cabem **inteiros** no escopo aprovado pelo `ScopeGuard`.

### Execução
- O Nuclei roda num contêiner de uso único na rede interna `zap_net`, atrás da cerca, com:
  - `-ni` (sem OAST), `-duc`, `-pt http`, `-rl` igual a `limits.requests_per_second`, `-jsonl -omit-raw` e `-proxy` para a cerca;
  - `cap_drop: ["ALL"]`, `read_only`, `no-new-privileges`, `tmpfs` e limites de memória e de processos.
- O runner liga a entrada padrão a `/dev/null`, impõe um prazo e derruba o contêiner se ele estourar.
- Vira a etapa `nuclei` do `run`, depois do `scan` e antes do `authz`, com `--nuclei/--no-nuclei`. O `run --only` a pula.
- Ganha também um comando próprio, `hdast nuclei`, para rodar só o Nuclei, como já acontece com `scan`, `authz` e `negative`.

### Login
- Usa o arquivo de segredos do Nuclei (`-sf`):
  - gravado pela CLI em `tmpfs`, com modo `0400`, dono igual ao usuário do contêiner e montagem só leitura;
  - apagado no fim, inclusive quando o runner falha.
- O token nunca vai para argumento, variável de ambiente nem log.
- Com login, também só rodam modelos de leitura.

### Saída e relatório
- A saída passa por uma projeção por **lista branca**. Do valor extraído ficam só o tipo, a contagem e o tamanho em bytes; `curl-command`, `request`, `response` e `extracted-results` são descartados (o Nuclei traz `curl-command` mesmo com `-omit-raw`).
- Os achados ficam em `nuclei.json` e numa seção própria do relatório:
  - modelo `NucleiFinding`, com `origin: "nuclei"`, identificador com prefixo `U-` e `NUCLEI_FINGERPRINT_VERSION` próprio;
  - gravidade fixa: `critical` e `high` viram alta, `medium` vira média, `low` vira baixa, `info` e `unknown` viram informativa.
- O `confirm` reproduz um achado do Nuclei repetindo o modelo.

### Carta e pedido mínimo
- Duas chaves novas, falsas por padrão para manter as aprovações antigas:
  - `extra_checks.nuclei` liga o módulo;
  - `extra_checks.known_exposures` soma a lista ao escopo.
- No pedido mínimo, as duas vêm ligadas por padrão. Uma 5ª pergunta pede o "sim" para testar caminhos conhecidos fora do Swagger. Isso altera o ADR 0120.
- Só a carta, a resposta da pessoa ou esse padrão ligam as chaves, sempre pela CLI e com aprovação humana.

### Opções para o dono decidir no aceite
1. **Comando `hdast nuclei` próprio.** Está incluído na decisão acima. O dono pode retirá-lo e deixar o Nuclei só como etapa do `run`.
2. **Seleção pela lacuna do ZAP.** A CLI calcularia, de forma determinística e testada, o que o ZAP cobriu em cada operação e escolheria só os modelos que cobrem o resto. O agente poderia apenas reduzir a seleção. **Fica fora desta decisão**, porque o spike mediu sobreposição zero (as regras 40034 e 40035 do ZAP não acharam nada nos 4 alvos), então a lacuna seria o módulo inteiro. O dono pode reabri-la se o uso real mostrar sobreposição.

## Alternativas consideradas

- **Nuclei como segundo motor geral.** Descartada: no desenho do plano o spike mediu ganho zero sobre o ZAP e o inventário nos três alvos.
- **Religar as regras 40034 e 40035 do ZAP com a lista no escopo.** Descartada: as regras têm a sua própria lista, e a nossa só abre a cerca. Deram 0 achados nos 4 alvos, inclusive no Actuator aberto, com 53 pedidos a mais por varredura.
- **Login pelo Replacer do ZAP, com o Nuclei usando o ZAP como proxy.** Descartada:
  - prende o Nuclei à janela do `scan` e à conta da operação varrida;
  - 813 dos 1.060 alertas passivos do ZAP (77%) vieram do tráfego do Nuclei.

  O ponto forte, de o Nuclei nunca ver o token, não compensou.
- **Estender o inventário do ADR 0102 com caminhos do Actuator.** Possível, mas mais caro: para chegar à cobertura que os modelos já trazem com confirmação por conteúdo, seria preciso reescrever e manter assinaturas próprias. O crAPI, que responde 200 a qualquer caminho, não gerou falso positivo no Nuclei justamente por essa confirmação.
- **Não fazer nada.** Descartada: a classe de exposição continua sem cobertura.

## Consequências

- **Mais fácil:** achar Actuator aberto, arquivos de configuração e painéis expostos, com custo de segundos por alvo e confirmação por conteúdo.
- **Mais difícil:**
  - mais uma imagem para manter;
  - atualizar os modelos exige novo censo, novo manifesto e novos SHA-256;
  - a lista de exposições aumenta o que a pessoa precisa conferir na aprovação.
- **Gravidade:** a tabela fixa marca como baixa o `/actuator/env` que expõe valores de configuração, o que subestima o risco. A tabela não muda aqui; o ajuste fica para decisão própria se o uso real pedir.
- **Dependência nova:** o Nuclei (MIT, mantido ativamente pela ProjectDiscovery) e o `nuclei-templates` (MIT), travados por versão e SHA-256.
- **Limites da prova:**
  - os 13 achados vieram de um alvo que nós mesmos expusemos, não de um alvo independente;
  - o login por `-sf` só foi provado com marcador sintético, sem token real;
  - não houve captura de pacotes para descartar telemetria; a prova é a falta de rota e de DNS e a auditoria da cerca;
  - a causa da partida travada não foi isolada, só contornada.
- **Depois:** implementar pelos pacotes do plano, ajustados a este escopo, e provar no laboratório os aceites abaixo.

### Aceites verificáveis
1. O manifesto é reproduzível: o mesmo ZIP conferido gera o mesmo manifesto, e um teste unitário cobre cada veto e a projeção com `stop-at-first-match` e `{{BaseURL}}` puro.
2. No alvo Spring do laboratório, a etapa `nuclei` acha pelo menos os 13 achados do Actuator com a seleção da CLI, sem projeção manual.
3. Em todas as execuções da prova, os pedidos do Nuclei batem com a auditoria da cerca, e nenhum sai do escopo aprovado.
4. Com login por `-sf`, o token real não aparece em `docker inspect`, na lista de processos, nos logs, no `nuclei.json` nem no relatório, e o arquivo some no fim, inclusive após falha forçada.
5. O runner encerra o contêiner ao estourar o prazo, e a entrada padrão fechada é verificada por teste.
6. Aprovações antigas continuam válidas com as chaves novas desligadas, e ligar qualquer uma delas exige nova aprovação.
