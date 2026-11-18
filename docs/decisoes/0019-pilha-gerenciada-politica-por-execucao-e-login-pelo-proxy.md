# 0019. Pilha gerenciada, política do proxy por execução e login pelo proxy de escopo

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** Integração do `probe` com o ZAP real e o proxy de escopo; detalha os ADRs 0008, 0017 e 0018
- **Nota de aceitação (2026-11-13):** aceito depois da implementação e da verificação no laboratório (ZAP 2.17 real, proxy de escopo real, VAmPI e Clínica Piloto); veja docs/reviews/2026-11-13-e2e-lab.md. O dono do projeto aprovou o desenho e pediu a conclusão do trabalho.

## Contexto

Até aqui a política do proxy de escopo (`policy.json`) era escrita à mão, a chave do ZAP era um `export` do operador e o login
e o token CSRF saíam direto da máquina (ou por um proxy qualquer em `HDAST_AUTH_PROXY_URL`). Isso deixava três furos entre o
que o perfil autoriza e o que a pilha impõe: a política podia divergir do perfil; o tráfego de login, que carrega a senha e por
isso não passa pelo ZAP, não passava por nenhum ScopeGuard de rede; e não havia comando para a parada de emergência prevista
no ADR 0017.

## Decisão

Vamos:

1. **Gerar a política a partir do perfil.** `adapters/scope_proxy/generate.py` monta um `ProxyPolicy` (o esquema continua
   definido só em `policy.py`) com o `scope` e os `limits` do perfil, sem acréscimo; `not_after` é o menor entre a duração
   máxima, o fim do último dia da autorização (UTC) e o primeiro minuto sem janela aberta (`domain/proxy_deadline.py`);
   `tls_verify_upstream` só vira `false` se o perfil desliga a verificação E toda regra é local. O resultado é relido pelo
   validador do contêiner antes de gravar.
2. **`hdast stack up|status|down`** (`application/stack.py`): `up` confere autorização e janela, grava a política numa pasta
   por execução (`<estado>/stacks/<run_id>/{policy,audit}`), sorteia a chave do ZAP se `HDAST_ZAP_API_KEY` não está definida
   e sobe os contêineres recriando-os (o proxy só lê a política na partida). Alvos de laboratório são reconhecidos pelo host de
   `environment.base_url`: `vampi` sobe no compose raiz (perfil `lab`); `clinica-piloto` sobe como projeto próprio
   `hdast-pilotrun`, anexado à `hdast_lab_net`, com credenciais descartáveis sorteadas e portas 28080 e 29091 no host.
3. **Estado fora do repositório.** A chave do ZAP, os endereços e as senhas descartáveis ficam em `stack.json`
   (`HDAST_STATE_DIR`; padrão `%LOCALAPPDATA%\hdast` ou `~/.local/state/hdast`), modo 0600 em POSIX e ACL herdada do perfil do
   usuário no Windows. Os comandos seguintes leem o arquivo só para o que o ambiente não define (`HDAST_*` sempre vence), e
   as senhas só são consultadas quando um `secret_ref: env:` do perfil cita o nome.
4. **Login e CSRF pelo proxy de escopo.** Novo serviço `proxy-gateway` (socat, destino fixo `scope-proxy:3128`, porta publicada
   só em `127.0.0.1`); `stack up` registra `auth_proxy_url` apontando para ele, e `preflight` e `probe` o usam por padrão.
   O ZAP não vê a senha; o ScopeGuard do proxy vê cada requisição de login.
5. **`hdast stop`**: cria o `KILL` primeiro (não depende do ZAP) e depois tenta parar as varreduras pela API do ZAP; ZAP
   fora do ar não é erro.

## Alternativas consideradas

- **Política escrita à mão pelo operador:** simples, mas permite divergir do perfil. Descartada.
- **Segundo ScopeGuard só para o login, dentro da CLI:** o `GuardedSender` já confere o escopo na CLI; o que faltava era a
  camada de rede independente da CLI. O proxy a fornece sem código novo de decisão.
- **Chave do ZAP só no ambiente:** não sobrevive entre processos; exigiria `export` manual a cada comando. Mantida como
  prioridade (o ambiente vence), com o arquivo de estado como padrão da pilha gerenciada.
- **Cofre do sistema (Credential Manager, Keychain):** melhor proteção, mas dependência nova e específica de plataforma para
  segredos de laboratório descartáveis. Adiada.
- **Porta do proxy publicada sem ponte:** contêiner em rede `internal` não é alcançável por porta publicada no Docker Desktop.

## Consequências

- A nova porta `127.0.0.1:3128` permite a qualquer processo da máquina enviar pedidos ao scope-proxy; o proxy nega tudo que a
  política da execução não permite (host, porta, caminho, método, taxa, prazo, `KILL`). Não dá acesso ao ZAP, à rede do lab nem
  ao Docker, e não fica visível fora da máquina.
- Cada `stack up` recria ZAP, proxy e alvo: estado limpo e `KILL` sempre novo, ao custo de ~35 s por subida.
- O arquivo de estado contém segredos de laboratório em texto puro; vale a proteção do sistema de arquivos.
- Políticas e auditorias de pilhas antigas ficam em `<estado>/stacks/` (a auditoria é evidência) e são apagadas à mão.
- `stack up` só atende alvos de laboratório conhecidos e perfis externos para os quais o `egress_net` tenha rota; produtos
  reais exigem revisão específica.
- Dependências novas: nenhuma (usa `subprocess` da biblioteca padrão e o compose existente).
