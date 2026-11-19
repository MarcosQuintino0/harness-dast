# 0025. Limpeza: confirmação só em terminal, amarração por coluna real e demais mudanças de contrato do QA M2 a M5

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** parecer de QA independente [2026-11-13-qa-m2-m5](../arquivo/reviews/2026-11-13-qa-m2-m5.md) (Q-01, Q-03, Q-07, Q-09, Q-15, Q-16) e relatório do lab [2026-11-13-e2e-lab](../arquivo/reviews/2026-11-13-e2e-lab.md); altera o que os ADRs [0020](0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md), [0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md) e [0024](0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md) decidiram (eles seguem imutáveis; este os substitui nos pontos abaixo)

## Contexto

O QA achou que a confirmação "humana" da limpeza (ADR 0020) não era humana: o token do `--dry-run` saía no `stderr` de quem rodou o comando, quem roda é, por desenho, o agente, e a mensagem de erro ensinava o caminho (`--dry-run`, depois `--confirm TOKEN`). O portão de SQL aceitava uma "amarração" que não amarra nada (`SYSDATE >= :run_start`) e faixas contra variável de texto. O `--fail-on none` relaxava o gate do perfil, a severidade desconhecida abria o gate, o prazo do `run` valia por etapa e o relatório do lab mostrou que o plano de varredura (leituras, depois escritas) deixava as escritas para depois do prazo. Cada ponto muda um contrato (códigos de saída, schema do relatório, comportamento do `cleanup`), por isso um ADR.

## Decisão

Vamos:

1. **Confirmação da limpeza só digitada, em terminal interativo.** `hdast cleanup` sem `--dry-run` recusa (`CONFIG_ERROR`, saída 2) quando a entrada padrão ou o `stderr` não é um terminal, com mensagem que diz que só uma pessoa num terminal interativo confirma. A confirmação é o nome do produto digitado no prompt. **Sem** flag, arquivo nem variável de ambiente de escape. A flag `--confirm TOKEN` foi removida; o `--dry-run` continua (não apaga, roda sem terminal) mas **não emite mais token** em lugar nenhum. A interatividade entra no caso de uso pelo parâmetro `CleanupRequest.interactive` (a CLI o calcula; os testes injetam o dublê do terminal e o prompt). O caso de uso continua capaz de aceitar `confirm_token` (os testes de QA o exercitam em processo), mas a CLI nunca o preenche: o token é resíduo e fica fora do alcance de quem opera pela linha de comando. Remover o resíduo é tarefa futura que exige trocar esses testes.
2. **Amarração do `WHERE` por coluna real.** A condição de amarração só vale se compara uma coluna (identificador) da tabela com uma variável permitida. Pseudo-colunas e funções sem argumento (`SYSDATE`, `SYSTIMESTAMP`, `CURRENT_DATE`, `CURRENT_TIMESTAMP`, `LOCALTIMESTAMP`, `ROWNUM`, `ROWID`, `LEVEL`, `USER`, `UID`, `SESSIONTIMEZONE`, `DBTIMEZONE`, `DUAL`...) e literais não valem. Faixa (`>=`, `>`) só contra `:run_start`; variáveis de texto (`:run_id`, `:run_tag`, `:account_N`) só com `=`, `IN` ou `LIKE`. O que o portão não reconhece, recusa.
3. **Cabeçalhos de roteamento nunca saem.** Parâmetro `in: header` do OpenAPI com nome de roteamento ou de enquadramento (`Host`, `Content-Length`, `Transfer-Encoding`, `Connection`, `Upgrade`, `TE`, `Expect`, `Trailer`, `Keep-Alive`, `Forwarded`, `Via`, `Proxy-*`, `X-Forwarded-*`) é pulado pelo montador e aparece em `skipped_fields` com o motivo; `encode_built_request` os filtra de novo e `approve()` recusa (`ScopeViolation`) uma requisição que os traga. A decisão fica em `domain/routing_headers.py`.
4. **Segredo do harness não é segredo de produto.** `secret_ref` recusa nomes `HDAST_*`.
5. **Redação cobre formas codificadas.** O `SecretRegistry` registra também as formas percent-encoded (`quote`, `quote_plus`, com `%2F` e `%2f`) de cada segredo; `Authorization: <esquema> <credencial>` em texto livre mascara a credencial e mantém o esquema.
6. **Gate de severidade falha fechado e flags só endurecem.** Severidade `unknown` conta como acima de qualquer limiar diferente de `none`. `--fail-on` só endurece o `scan.fail_on` do perfil (`effective_fail_on`): `--fail-on none` com perfil `high` continua `high`.
7. **Prazo único no `run`.** O `run` calcula um prazo absoluto no início do `probe` (`limits.max_duration_minutes`, reduzido por `--max-minutes`) e o repassa ao `probe` e ao `scan` (`ProbeRequest.deadline`, `ScanRequest.deadline`, `RunGate(deadline=...)`); nenhum estágio recomeça a contagem.
8. **O `scan` parado não perde o relatório.** No `run`, se o `scan` parar antes do fim e tiver gravado `scan.json`, o `report` roda sobre o que foi coletado, o código de saída final continua sendo o do estágio que parou e `findings.json` ganha `coverage.partial` (campo aditivo; `report.md` traz o aviso "RELATÓRIO PARCIAL").
9. **Trava de emergência não mascara erro real.** Com a trava acionada, só vira 130 o erro que a própria trava causou (mensagem do `KillSwitchEngaged`) ou a interrupção observada depois de uma etapa; um erro de outra origem mantém o código dele (`stop_requested: true` registra a trava). `FileKillSwitch.engaged()` falha fechado se o sistema de arquivos nega acesso.
10. **`run.json` e a trilha da limpeza também em exceção inesperada.** Com `try/finally` (sem `except` genérico): o `run` grava `run.json` (estágio `failed`, saída 10) e relança; a limpeza desfaz, grava `finished` e `cleanup.json` e relança.
11. **Ordem do plano de varredura (substitui a do ADR 0022).** Por conta; dentro da conta, leituras e escritas **intercaladas** de modo determinístico: uma escrita (de `POST` a `PUT`/`PATCH`) depois de cada bloco de `leituras // escritas` leituras (no mínimo 1), começando por uma leitura. Um prazo curto passa a cobrir as duas classes. O risco de rodar uma escrita mais cedo é o mesmo de rodá-la: o plano só inclui `POST` (cria dado sintético que a limpeza apaga) e `PUT`/`PATCH` sobre recurso criado na execução ou liberado pelo perfil.
12. **Fingerprint sem colisão.** Quando algum ingrediente contém o separador U+001F (dado do ZAP), o hash usa uma forma com o tamanho de cada parte, que começa com U+001E e nunca coincide com a forma simples. O fingerprint de entradas sem o separador **não muda** (conferido pelo golden `findings.golden.json`), então `FINGERPRINT_VERSION` continua 1.
13. **Cookie de sessão por origem.** O jar de cookies do cliente do alvo é por conta **e** por `host:porta`: um cookie recebido de um host permitido não vai a outro.

Entradas externas: inteiro com mais de 4300 dígitos no YAML vira `ConfigError`; `constant` com `NaN` ou infinito e `unique` que não seja booleano são recusados; o `Host` do cliente no proxy só vale como `host[:porta]` estrito.

## Alternativas consideradas

- **Manter o token e exigir TTY só na emissão.** O agente ainda leria o token de outro `--dry-run`, mas num terminal falso; o que resolve é a confirmação digitada, não o transporte do token. Descartada.
- **Flag de escape para CI (`--assume-yes-i-am-a-person`).** Qualquer flag um agente também passa. Descartada: quem precisa limpar sem pessoa recria o ambiente descartável.
- **Remover já o mecanismo de token do caso de uso.** Os testes de QA o exercitam e não podem ser editados nesta rodada; fica como resíduo declarado.
- **Elevar `FINGERPRINT_VERSION` para escapar o separador.** Invalidaria todo histórico por um caso raro. Descartada pela forma que só atua quando o separador aparece.
- **Mudar o código de saída do `run` para 130 sempre que houver `KILL`.** É o que mascarava o erro real; descartada.

## Consequências

- O agente não consegue mais completar a confirmação destrutiva pela CLI. Limite honesto: um pseudoterminal ainda cumpriria; o que fecha isso é a permissão do Claude Code (M6) e os privilégios do usuário de banco.
- Script de limpeza que usava `>=` contra variável de texto ou pseudo-coluna passa a ser recusado (era defeituoso).
- Quem usava `--confirm TOKEN` em CI deixa de poder fazê-lo.
- `findings.json` ganha `coverage.partial` (aditivo, sem mudar `schema_version`); o golden foi regravado só nesse campo.
- A cobertura de escritas num prazo curto melhora; a ordem do `scan.json` e do `probe` muda para quem comparava ordem.
- O parecer segue com itens abertos que não são mudança de contrato (auditoria do proxy gravada só depois da resposta, NAT64 no Python 3.13, `ON DELETE CASCADE` fora do teto): ver [docs/roadmap.md](../roadmap.md).
