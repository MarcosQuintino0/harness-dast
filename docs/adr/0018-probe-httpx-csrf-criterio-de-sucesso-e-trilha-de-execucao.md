# 0018. `probe` com httpx, CSRF, critério de sucesso e trilha de execução

- **Status:** Proposto
- **Data:** 2026-11-13
- **Origem:** M3 (`spec inspect`, `preflight`, `probe`); spike do M0 (Q1, Q2, Q3, Q5, Q7); detalha os ADR [0007](0007-zap-alimentado-por-requisicoes-validas.md), [0009](0009-segredos-por-referencia.md) e [0010](0010-contrato-json-da-cli-e-codigos-de-saida.md)

## Contexto

O `probe` envia uma requisição válida por operação pelo proxy do ZAP e mede a alcançabilidade. O spike do M0 confirmou o mecanismo e trouxe quatro fatos que o desenho precisa respeitar: HTTP 2xx esconde falha lógica (o VAmPI devolve 200 com `"status":"fail"`); alvos reais com Spring Security exigem token XSRF por cookie duplicado; as regras do Replacer e as opções do ZAP sobrevivem a uma sessão nova; e o alvo pode saturar. Faltavam um cliente HTTP, o formato dos artefatos de uma execução e a forma de impedir, por construção, que algo saia sem passar pelo `ScopeGuard`.

## Decisão

**1. Dependência nova de runtime: `httpx` 0.28.1.** Licença BSD-3-Clause; dependências transitivas `httpcore` 1.0.9 (BSD-3-Clause), `h11` 0.16.0 (MIT) e `anyio` 4.16.0 (MIT) e `idna`/`certifi`, já presentes. Mantida pela Encode, com releases regulares e API estável. Usada em dois adaptadores independentes: `adapters/http` (cliente do alvo) e `adapters/zap` (API de controle do ZAP, sem biblioteca específica do ZAP). Entra na lista proibida do `domain` no import-linter. Travada no `uv.lock`.

**2. Invariante "nada sai sem o guarda".** O único tipo que o cliente HTTP envia é `ApprovedRequest` (`domain/http_messages.py`). Só `approve(guard, request)` o cria, e só depois de `ScopeGuard.ensure_allowed`; o construtor exige uma marca privada do módulo, subclasses são proibidas e a instância é imutável. Toda saída da camada `application` passa por `GuardedSender` (ritmo, janela e prazo, `approve`, linha de auditoria de decisão, envio, linha de resultado). Redirecionamentos não são seguidos; um 3xx é reportado (`redirect`), com a informação de o destino estar ou não no escopo. O cliente ignora variáveis de proxy do ambiente, limita tempo e tamanho do corpo e verifica TLS por padrão.

**3. Duas rotas de saída.** A rota `zap` (operações do `probe` e checagem de saúde) sai pelo proxy do ZAP, que aprende a requisição. A rota `auth` (login e busca do token CSRF) sai direto, ou por `HDAST_AUTH_PROXY_URL`, para a senha não entrar no histórico do ZAP. O token continua passando pelo ZAP, como no spike.

**4. Schema v1 do perfil, aditivo e opcional** (sem subir `schema_version`; perfis antigos continuam válidos):

- `auth.csrf` (nos dois tipos de autenticação): `fetch_path` (GET literal, no escopo), `cookie_name` (padrão `XSRF-TOKEN`), `header_name` (padrão `X-XSRF-TOKEN`) e `methods` (padrão POST, PUT, PATCH e DELETE). O cliente guarda o cookie por conta, envia cookie e cabeçalho nos métodos listados e renova o token uma vez ao receber um 403 que parece rejeição de CSRF.
- `probe.success.json_field_absent_or_not_equal`: `{field, value}`. Uma resposta 2xx só é sucesso se o campo estiver ausente ou tiver valor diferente do de falha. Sem o bloco, vale 2xx.
- `probe.health_path`: GET leve para o `preflight`; precisa estar no escopo.
- `environment.verify_tls` (padrão `true`): só pode ser `false` para host local (regra com `allow_local: true`).

**5. Classes de resultado e trechos do alvo.** O resultado de cada operação é uma de: `success`, `logical_failure`, `validation_error`, `conflict`, `auth_error`, `csrf_error`, `not_found`, `rate_limited`, `server_error`, `client_error`, `redirect`, `timeout`, `skipped_scope`, `skipped_denied`, `skipped_destructive`, `skipped_dependency`, `build_error` e `dry_run`. Alcançabilidade = sucessos / operações tentadas (enviadas), mais uma segunda razão sobre todas as operações do OpenAPI. Só falhas levam um trecho da resposta, sob a chave `untrusted_target_data`: no máximo 300 caracteres, valores de texto de no máximo 80, sem ANSI, controle nem bidi, com JWT, CPF, e-mail e sequências parecidas com token redigidos, valores de campos sensíveis mascarados e segredos registrados trocados por `***`. Do cabeçalho de resposta só `Content-Type` e `Retry-After`.

**6. Trilha de execução em `<runs_dir>/<run_id>/`:** `manifest.json` (identificador, produto, versão do harness e do ZAP, id do contexto do ZAP, SHA-256 de `target.yml`, `data-rules.yml`, `flows.yml` e OpenAPI, limites, semente, contas, início e fim, estado), `audit.jsonl` e `probe.json`. Cada requisição gera duas linhas de auditoria com o mesmo `seq`: `decision` (antes do envio, `allowed` ou `denied`) e `result` (status ou erro de transporte e duração); decisão sem resultado indica interrupção. Só acréscimo, com `fsync`; da consulta ficam apenas os NOMES dos parâmetros; nunca cabeçalho, corpo, token, senha nem cookie. `manifest.json` e `probe.json` são gravados de forma atômica. O `preflight` também grava manifesto e auditoria, pois envia requisições. `--dry-run` não grava nada e não envia nada.

**7. Higiene do ZAP.** No início do `probe`: versão (outra versão que 2.17.x é avisada), regras do Replacer com o prefixo `hdast-` removidas (as de outros nomes nunca), sessão nova por execução e contexto restrito aos hosts e caminhos do perfil (`deny_paths` como exclusão). O id do contexto vai ao manifesto. A chave da API segue no cabeçalho `X-ZAP-API-KEY`, nunca na URL. Erro de API do ZAP vira `ExternalToolError`; no início do `probe` vira `PreflightError` (saída 4), no meio da execução, parada com saída 5.

**8. Códigos de saída** (sem mudar a tabela): `probe` sai com 0 quando rodou, mesmo com falhas de operação; 2 configuração; 3 janela fechada, autorização vencida ou prazo (`limits.max_duration_minutes`) esgotado, inclusive no meio da execução, com o resultado parcial em `data`; 4 falha ao começar (ZAP fora do ar, segredo ausente, login recusado); 5 proxy do ZAP caiu no meio; 6 cinco falhas de transporte seguidas (timeout, conexão recusada, 502, 503 ou 504). `preflight` sai com 0 se pronto, 3 se autorização ou janela falharam, 4 nos demais casos. Nesses casos o envelope traz `ok: false`, `error` e também `data`.

**9. Nomes de variáveis de ambiente de segredos** aparecem só no texto para a pessoa que opera; o JSON do `preflight` mostra apenas `apelido.campo`. O agente não precisa do nome (ele o escreveu no `target.yml`).

## Alternativas consideradas

- **Cliente ZAP de terceiros (`python-owasp-zap-v2.4`, `zaproxy`).** Mais métodos do que o necessário, manutenção irregular e mais superfície; a API usada cabe em quatro chamadas.
- **`requests` ou `urllib3`.** `httpx` tem cliente com proxy por instância, tempo limite granular e streaming do corpo com teto, tudo de que o cliente precisa, com tipagem completa.
- **Sucesso só por código HTTP.** Superestima a alcançabilidade (spike, seção 4).
- **Login pelo proxy do ZAP.** Simplifica a rede do laboratório, mas grava a senha no histórico do ZAP.
- **Autenticação nativa do ZAP.** Exige entregar a senha ao ZAP; adiado (M4 decide a entrega do token para a varredura).
- **Aprovar a requisição no cliente.** Duplicaria a decisão de escopo num adaptador; o tipo aprovado no domínio mantém a decisão num só lugar.

## Consequências

- Mudança de contrato do perfil (aditiva) e da CLI (três comandos novos, `data` de cada um documentado em [../reference/cli.md](../reference/cli.md)); `target-yml.md` e o modelo `products/_template` documentam os blocos novos.
- `ApprovedRequest` não é à prova de um desenvolvedor que acesse a marca privada de propósito; a defesa é o nome privado, a revisão e o teste de mutação (remover a chamada do guarda quebra testes).
- A heurística de 403 de CSRF (corpo cita csrf/xsrf, ou 403 sem mensagem) pode repetir uma requisição 403 de autorização uma vez; o custo é limitado.
- Os cookies são guardados por conta e por processo; um alvo com vários hosts compartilharia o nome do cookie entre eles (o `probe` usa um único host, `environment.base_url`).
- Operações multipart e binárias viram `build_error` até haver suporte.
- Não verificado contra o ZAP real nesta rodada (somente contra um ZAP falso com as formas do spike): veja a seção de verificação em [../roadmap.md](../roadmap.md).
- O M4 acrescenta a regra do Replacer com o token usando o prefixo `hdast-`, que a limpeza de regras antigas já cobre.
