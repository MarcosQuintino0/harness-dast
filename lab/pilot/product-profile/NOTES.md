# Notas do perfil da Clínica Piloto: o que o alvo exigiu do schema v1

Histórico para o orquestrador. A primeira versão desta página listava o que o schema v1 não conseguia dizer sobre este alvo. Todos os
itens abaixo foram atendidos por campos **opcionais e aditivos** (o schema continua na versão 1; decisão no
[ADR 0021](../../../docs/adr/0021-esquema-aditivo-do-perfil-para-o-alvo-piloto.md)) e o `target.yml`, o `flows.yml` e o
`data-rules.yml` desta pasta os usam. Verificado de ponta a ponta contra o alvo real, o ZAP 2.17 e o proxy de escopo
(`uv run pytest -m integration tests/integration/test_lab_pilot.py`).

| # | O que o alvo exige | Como o perfil expressa agora |
| --- | --- | --- |
| 1 | XSRF por cookie duplicado nas escritas, exceto no login | `auth.csrf` (`fetch_path: /api/csrf`, cookie `XSRF-TOKEN`, cabeçalho `X-XSRF-TOKEN`, métodos de escrita). O login também recebe o par; `GET /api/csrf` está no escopo |
| 2 | Token de 300 s; 401 `TOKEN_EXPIRADO` | `auth.token_expired: {field: code, value: TOKEN_EXPIRADO}`: um novo login por requisição, contado no orçamento. O 401 `TOKEN_INVALIDO` não renova |
| 3 | Classificar o erro pelo `code` do corpo | `probe.error_codes` (`VALIDACAO`, `CONFLITO`, `XSRF_INVALIDO`...). Regras de estado (`TRANSICAO_INVALIDA`, `CONSULTA_CANCELADA`, `EM_USO`) vão para `client_error`. O trecho do erro mantém `errors[].field` e `rule` |
| 4 | 5 logins por minuto por origem, contando os errados, `Retry-After` no 429 | `auth.login_limit.max_per_minute: 5` (janela deslizante antes de cada POST de login) e espera do `Retry-After` no 429 |
| 5 | Cadeia `convênio -> paciente -> consulta -> receita` | `flows.yml` com vários níveis (grafo sem ciclos, até 6 operações). Os ids de semente constantes deixaram de ser necessários |
| 6 | CRM único `NNNNNNN-UF` | Gerador `br.crm` com `unique: true` e `digits: 7` (com 5 dígitos a chance de colisão entre duas execuções seguidas é de 10%) |
| 7 | Papel por operação | `auth.default_account: admin_a` e `auth.account_map` (admin: convênio e médico; médico: paciente, consulta, status e receita; paciente A: `/api/me`) |
| 8 | Limpeza: quais binds a CLI fornece | [`docs/reference/cleanup.md`](../../../docs/reference/cleanup.md): `:run_start`, `:run_id`, `:run_tag` e `:account_1..N` na ordem de `auth.accounts` (as quatro contas daqui) |

## O que o `probe` mede aqui

Com o alvo recém-subido, `preflight` e depois `probe` criam a cadeia inteira (cada elo com a conta do mapa) e uma segunda execução
seguida, sem reiniciar, não dá 409 (`codigo`, `cpf`, `email` e `crm` são únicos por execução). A operação `login` do OpenAPI vai
com credenciais **geradas**, que o alvo recusa de propósito (`auth_error`, `CREDENCIAIS_INVALIDAS`); ela entra nas tentadas e é a
única que não tem sucesso. `enviarNotificacao` é `skipped_denied` (o contador `notifications_sent` do alvo fica em 0) e os dois
`DELETE` são `skipped_scope` (o escopo não autoriza `DELETE`).

## O que continua valendo

- **Limpeza.** O `cleanup.sql` desta pasta (cópia de `lab/pilot/cleanup/cleanup.sql`) usa o contrato acima. `PILOT_ORACLE_CLEANUP_CONNECTION`
  é o DSN de um usuário Oracle só com `DELETE` nas cinco tabelas (`allowed_tables`, `max_rows`: veja `docs/operations/cleanup.md`). Com o
  banco H2 padrão não há conexão externa: a limpeza se prova pelo `POST /internal/eval/reset` do avaliador.
- **Logins seguidos.** O orçamento é por comando. `preflight` (4 logins) seguido de `probe` (3 contas mais a operação de login) passa
  de 5 em 60 s; o alvo responde 429 com `Retry-After` e o `probe` espera. Leva cerca de um minuto a mais, e o resultado é o mesmo.
- O `servers` do OpenAPI é `http://localhost:8080`, fora do escopo do perfil (`clinica-piloto:8080`); `spec inspect` avisa em
  `servers_out_of_scope`. Está certo: a CLI usa a `base_url` do perfil.
- `GET /api/documentos/download` responde `application/octet-stream`; o `probe` não exige JSON. O parâmetro `arquivo` usa um documento
  de semente (`data-rules.yml`).
- O alvo ignora corpo extra e exige `Content-Type: application/json` nas escritas (415 caso contrário).
- O estado de avaliação (`/internal/eval/*`, porta 9091) está fora do OpenAPI e do escopo; só o avaliador e os testes de integração o usam.
