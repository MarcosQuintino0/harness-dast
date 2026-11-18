# Problemas comuns

Erro, causa provável e o que fazer. Os códigos são os reais da CLI ([exit-codes.md](../referencia/exit-codes.md)); a mensagem e a dica (`error.message`, `error.hint`) dizem o específico, leia-as primeiro. Com `--json`, o erro vem em `error.code`.

## Por código de saída

| Saída | `error.code` | Causa mais comum | O que fazer |
| --- | --- | --- | --- |
| `2` | `CONFIG_ERROR` | Perfil, YAML, argumento ou pasta inválidos | Leia a lista de campos; corrija o arquivo. `profile validate` mostra a lista por caminho |
| `2` | `AUTHZ_CONFIG_INVALID` | A tabela "quem pode o quê" (`authz.access_matrix`) cita uma operação que não existe no OpenAPI, um papel que nenhuma conta tem, ou uma operação que também está em `public_operations` | A mensagem diz qual; corrija o `target.yml` (a tabela é da pessoa que aprova, não do agente) e peça nova aprovação do escopo |
| `3` | `SCOPE_VIOLATION` | Autorização vencida, janela fechada ou prazo esgotado | Não há flag que contorne. Janela: espere. Autorização: o dono do produto renova e você atualiza o perfil |
| `4` | `PREFLIGHT_FAILED` | Segredo ausente, ZAP fora do ar, login recusado ou alvo não saudável | Veja a tabela de verificações abaixo |
| `4` | `STACK_STALE` | O `target.yml` (ou a aprovação) mudou **depois do `stack up`**, por exemplo ao corrigir `auth.request_encoding` com a pilha de pé. O proxy prende o hash do arquivo e negaria todo pedido (403 `approval_changed`) | Nada foi enviado ao alvo. `uv run hdast stack down` e `uv run hdast stack up <produto>`, e repita. `hdast profile approval` continua dizendo `approved` se só um campo livre mudou: isso não evita a recriação. `uv run hdast stack status` mostra `binding: stale`. Se a aprovação mudou, uma pessoa roda `hdast profile approve` antes. Editar só `data-rules.yml` ou `flows.yml` não exige recriar |
| `5` | `EXTERNAL_TOOL_ERROR` | Docker ou ZAP falhou, ou caiu no meio | `uv run hdast --json stack status`; reinicie a pilha com `stack up` |
| `6` | `TARGET_ERROR` | O alvo parou de responder | Verifique o alvo; não repita em laço |
| `7` | `CLEANUP_FAILED` | Falha ou teto de linhas na limpeza | [limpeza-de-dados.md](limpeza-de-dados.md); a transação sofreu `ROLLBACK` |
| `8` | `STACK_BUSY` | Outra execução ocupa a pilha (ZAP e proxy) | A mensagem diz quem ocupa (comando, produto, início). Espere terminar; para parar agora, `uv run hdast stop` e espere o processo sair (o `stop` não solta a trava, e `stack down` também fica bloqueado até lá). Se **você** conferiu que não há execução nenhuma (outro programa reaproveitou o número do processo), apague o arquivo de trava que a mensagem cita; o agente não apaga. Não repita em laço |
| `10` | `INTERNAL` | Erro inesperado | Guarde a saída de `stderr` e reporte ao mantenedor |
| `130` | `INTERRUPTED` | Ctrl+C ou `hdast stop` | Esperado. Depois de `stop`, a pilha só volta com `stack up` |
| `1` | (nenhum) | Achado no limiar do `--fail-on` ou `scan.fail_on` | Não é erro; leia o relatório |

## Antes de começar: `doctor`

Na dúvida, rode `uv run hdast doctor [produto]` (não toca o alvo). Ele lista Python, `uv`, Docker, imagens, portas, pilha, perfil, autorização, janela e segredos, cada um com o que fazer.

| Conferência | Causa | O que fazer |
| --- | --- | --- |
| `docker` falha | Docker Desktop fechado, travado ou sem terminar de subir | Abra-o, espere ficar "running" (ou reinicie) e rode o `doctor` de novo |
| `images` avisa | Imagens ainda não baixadas ou construídas | Normal na primeira vez; o `stack up` cuida (precisa de internet) |
| `port:8080` ou `port:3128` falha | Outro programa usa a porta | Feche-o, ou defina `HDAST_ZAP_HOST_PORT` / `HDAST_PROXY_HOST_PORT` com outra porta |
| `stack` avisa que venceu | A validade da pilha acabou (duração máxima mais 60 minutos de folga, ou fim da janela ou da autorização) | `hdast stack up` de novo |
| `profile` falha | Perfil inválido ou com valores do modelo (`PLACEHOLDER_*`) | `hdast profile validate <produto>` mostra o que preencher |
| `secrets:<apelido>` falha | Segredo não definido: variável de ambiente (`env:`) ausente neste terminal, ou nome (`keyring:`) ainda não gravado no cofre | Para `env:`, defina a variável e abra o terminal de novo. Para `keyring:`, rode num terminal seu `uv run hdast secret set NOME` (o nome aparece no texto, nunca no JSON) |
| `secrets:<apelido>` ou outro comando falha com `SECRET_BACKEND_ERROR` | O cofre do sistema não está utilizável: contêiner, CI, Linux sem serviço de segredos, cofre bloqueado, ou backend que o harness não aceita | Em contêiner ou CI, use `secret_ref: env:NOME`. No Linux, instale e desbloqueie o GNOME Keyring ou o KWallet. No Windows e no macOS, confira se a sessão está desbloqueada |
| `hdast secret set` recusa: "só uma pessoa, num terminal interativo" | Rodou sem terminal (agente, script, entrada redirecionada) | Abra um terminal seu e rode o comando lá. Não há flag que o dispense |

## Cadastro e perfil

| Sintoma | Causa | O que fazer |
| --- | --- | --- |
| `init`: pasta de produtos inexistente | A CLI não cria a pasta | Crie-a, ou use `--products-dir`/`HDAST_PRODUCTS_DIR` |
| `init`: produto já existe | `init` nunca sobrescreve | Edite a pasta existente ou escolha outro nome |
| `init --from-letter` sai com `LETTER_REJECTED` | O `carta.yml` tem pendências (`data.issues`: campo e código) | Responda o que falta na entrevista e rode `--check` de novo. Portão "não" ou resposta desconhecida recusa tudo; valor de senha no lugar do nome do segredo é recusado |
| Comando que toca o alvo recusa por falta de aprovação (`SCOPE_NOT_APPROVED`) | A pessoa ainda não aprovou o escopo | Leia o resumo e rode `hdast profile approve <produto>` num terminal seu. O agente não aprova por você |
| `runnable: false` com `PLACEHOLDER_HOST`, `PLACEHOLDER_AUTHORIZATION` ou `PLACEHOLDER_SECRET_REF` | Valor do modelo ainda no perfil | Preencha com os dados da carta de autorização |
| `FILE_MISSING` | `openapi` ou script de limpeza não está na pasta do produto | Copie o arquivo para lá |
| `AUTHORIZATION_EXPIRED` ou `WINDOW_CLOSED` | Fora da validade ou da janela | Veja saída `3` |
| `spec inspect`: `needs_rule` | Campo obrigatório que o harness não sabe gerar | Escreva a regra em `data-rules.yml` (veja `hint`) |
| `DATA_RULES_MISMATCH`, `FLOWS_MISMATCH` | Operação ou campo inexistente no OpenAPI | Confira o `operationId` e o nome do campo |
| `servers_out_of_scope` | O Swagger lista outro servidor | Normal: a CLI usa `environment.base_url` |

## `preflight` e `stack`

Para instalação, falhas de download, portas ocupadas e versão do proxy, consulte [Problemas comuns do Docker](../comecar/docker.md#problemas-comuns).

| Verificação ou mensagem | Causa | O que fazer |
| --- | --- | --- |
| `secrets:<apelido>` falha | Variável de ambiente do segredo não definida neste terminal | Defina a variável (o nome está no perfil e na carta) e abra o terminal/Claude Code de novo |
| Tudo recusado com 403 e `approval_changed` no `audit.jsonl` do proxy, ou `stack status` com `binding: stale` | Perfil ou aprovação mudou depois do `stack up` ([ADR 0081](../decisoes/0081-pilha-desatualizada.md)); a CLI agora para antes do primeiro pedido com `STACK_STALE` | `stack down` e `stack up <produto>` |
| `zap` falha ou "chave de API errada" | ZAP fora do ar ou chave diferente da pilha | `stack up` de novo; não misture pilha antiga com variáveis `HDAST_ZAP_*` de outra |
| `target_setup` falha | O GET de `probe.setup_path` respondeu 4xx ou 5xx, ou o alvo não respondeu | Confira o caminho no perfil e se a carta autoriza esse GET; o caminho precisa estar em `scope.allow` |
| `target_health` falha | Alvo fora do ar ou `probe.health_path` errado | Suba o alvo; confira o caminho no perfil |
| `login:<apelido>` falha | Usuário ou senha errados, ou limite de logins por minuto | Confira a conta; espere um minuto; declare `auth.login_limit` se o alvo limita |
| `login:<apelido>` diz "não traz o token esperado" e o alvo respondeu 200 | Campo do token errado, ou a conta ainda não existe no banco (ambiente recém-subido, sem dados de exemplo) | Confira `auth.token_response_field`. Se a carta autoriza um GET idempotente que recria os dados de exemplo, declare-o em `probe.setup_path`: o `preflight` e o `run` o chamam antes dos logins. Não chame o alvo por fora da CLI |
| `csrf:<apelido>` falha | Rota ou nomes de cookie e cabeçalho do CSRF errados | Confira o bloco `auth.csrf` com a documentação do produto |
| "O comando docker não foi encontrado" | Docker fora do PATH | Instale ou abra o Docker Desktop |
| "O Docker não terminou de subir o projeto..." | Docker Desktop lento ou travado | Confira `docker ps`; rode `stack up` de novo (`--timeout N` aumenta o prazo) |
| "Suba a pilha com hdast stack up ou defina HDAST_SCOPE_POLICY_DIR" | `stop` sem pilha | Não há o que parar, ou a pilha foi derrubada |
| "Não encontrei o compose.yaml do repositório" | `hdast` rodado fora de uma cópia do repositório | Rode a partir da raiz (`uv run hdast ...`) |

## `probe`

| `outcome` | O que significa e o que fazer |
| --- | --- |
| `validation_error` (400/422) | Falta regra de dados: veja `errors[].field` e escreva em `data-rules.yml` |
| `conflict` (409) | Veja candidatos em `conflict_fields` (campo informado na resposta ou derivado do esquema); priorize `summary.blocked_producers` por `blocked_dependencies` e use `unique: true` na regra adequada |
| `not_found` (404) | Falta encadeamento: `flows.yml` |
| `auth_rejected_expected` (401/403) | Login do perfil recusou credenciais sintéticas: conta como alcançado, separado de sucesso 2xx; não prova autenticação real. Login fica fora do `scan` e `negative`; injeção nele não foi testada |
| `auth_error` (401/403) | Tente `auth.account_map` com contas da carta; se persistir, interrompa só essa operação, registre pendência no diário e nas lacunas e siga |
| `csrf_error` | CSRF não declarado ou errado |
| `rate_limited` (429) | O alvo limita; reduza, não insista |
| `server_error`, `timeout` | Interrompa só a operação; registre pendência no diário e nas lacunas e siga com as demais |
| `skipped_scope`, `skipped_denied`, `skipped_destructive` | Por desenho: fora do escopo, proibido ou `DELETE` |
| `build_error` em operação de envio de arquivo (`multipart/form-data`) | O esquema do corpo não é modelável (campo de arquivo que não é `string` com `format: binary`, mais de 20 partes) ou falta regra: leia o `hint`; para o tipo ou o nome do arquivo, regra `synthetic_file` em `data-rules.yml` |
| Envio de arquivo alcançado (`success`), mas sem varredura: `upload_scan_not_authorized`, `binary_body` ou `multipart_not_scannable` no `scan.json` | Por desenho: a carta não autoriza o ZAP a varrer upload (`attack.allow_upload_scan`), o arquivo sintético é binário (`png`) e o ZAP recebe o corpo como texto, ou o ZAP não consegue varrer esse corpo. Não é falha de alcance; só o dono do produto autoriza a varredura (a pessoa muda a carta e aprova de novo) |

Após esgotar as tentativas ou duas rodadas sem melhora, siga com varredura parcial e registre as operações e motivos do último `probe` no diário, relatório e resposta final. Paradas por autorização, janela, escopo, indisponibilidade da pilha/ZAP ou alvo, `STACK_BUSY` e 429 sem limite informado continuam valendo. O passo a passo desse laço é a skill `fix-reachability`.

## Varredura, relatório e limpeza

| Sintoma | Causa | O que fazer |
| --- | --- | --- |
| `run` sai com `3` e o relatório diz "RELATÓRIO PARCIAL" | Prazo, janela ou outro corte antes do fim | O que não foi varrido **não** está seguro. Rode de novo com mais tempo (se a carta permitir) ou em outra janela |
| `scan` recusa: ZAP sem o contexto do `probe` | Um `probe` mais novo trocou a sessão do ZAP | Rode o `probe` (ou `run`) de novo; o `scan` precisa do contexto do `probe` mais recente |
| `report` sai com `2` e cita `triage.json` | Campo não permitido, texto longo ou `reason` ausente | Corrija o arquivo (só `fingerprint`, `note`, `suspected_false_positive`, `reason`) |
| `report --compare` recusa | Outro produto, outra versão de fingerprint ou execução sem `findings.json` | Rode o `report` na execução base antes |
| `cleanup` recusa sem terminal (saída `2`) | A confirmação só vale digitada, em terminal interativo | Rode você, num terminal; `--dry-run` não exige terminal |
| `cleanup` recusa o script | O portão de SQL exige amarração por coluna real e variáveis permitidas | Peça à pessoa que escreveu o script ([cleanup.md](../referencia/cleanup.md)) |
| Relatório sem achados | Não prova segurança | Leia "O que este relatório não testou" |
| "Já existe mutação com resultado desconhecido para esta operação e conta" (no `probe`, `authz`, `negative` ou `scan`) | Uma escrita anterior pode ter chegado ao alvo e o resultado não foi confirmado; o harness não a repete às cegas | **Ação humana.** Confira o estado no ambiente de teste e, só depois, remova o arquivo `.jsonl` pendente citado na mensagem, em `<pasta de estado>/mutations/`. O agente não remove. Detalhes em [knowledge.md](../referencia/knowledge.md) |
| "Não foi possível gravar o diário de mutações (erro de E/S)" | Pasta de estado sem permissão ou sem espaço | Corrija a pasta indicada e repita; nada foi enviado |

Parar tudo, a qualquer momento: `uv run hdast stop`.
