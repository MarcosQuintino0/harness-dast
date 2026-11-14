# Diário de comandos e dados auxiliares do painel

> **Status: implementado como código e testes (V1.2), sem prova com Docker.** Decisão: [ADR 0033](../adr/0033-diario-de-comandos.md) (status Proposto). Consumidor: o painel da execução ([`docs/design/execution-panel/`](../design/execution-panel/README.md)), que ainda não usa estas funções. Nenhum comando novo da CLI: o diário é gravado por todo comando existente.

## Diário de comandos

Toda invocação do `hdast` deixa uma linha JSON num arquivo por produto, **fora do repositório e de `runs/`**:

| O quê | Onde |
| --- | --- |
| Pasta de estado | `HDAST_STATE_DIR`; senão `%LOCALAPPDATA%\hdast` (Windows) ou `$XDG_STATE_HOME/hdast` ou `~/.local/state/hdast` |
| Diário de um produto | `<estado>/journal/<produto>.jsonl` |
| Comandos sem produto (`version`, `stop`, `stack status`, `secret set`...) | `<estado>/journal/_sem-produto.jsonl` |

Só acréscimo. Pasta 0700 e arquivo 0600 no POSIX; no Windows vale a ACL herdada. Falha ao gravar nunca derruba o comando: vira o aviso `diario_nao_gravado` no log (stderr), sem mudar o código de saída. `--help` e comando desconhecido não são registrados.

### Linha (`schema_version: 1`)

| Campo | Tipo | Observação |
| --- | --- | --- |
| `schema_version` | inteiro | `1`. Linha de outra versão é pulada na leitura |
| `started_at`, `finished_at` | data e hora com fuso | Relógio por porta (`Clock`) |
| `command` | texto | Subcomando por extenso: `probe`, `stack up`, `secret set` |
| `product` | texto ou `null` | Slug do produto |
| `run_id` | texto ou `null` | Do envelope (`run_id`); senão de `--run` |
| `flags` | lista de `{name, value}` | `value` é `null` em flag sem valor. Flag de nome sensível guarda `***`; os demais valores são redigidos (`redact_text`) e cortados em 120 caracteres |
| `args` | lista de texto | Posicionais além do produto, redigidos e cortados |
| `exit_code` | inteiro | Saída do processo ([exit-codes.md](exit-codes.md)) |
| `state` | `ok`, `parcial` ou `erro` | `ok`: saída 0, ou 1 (varredura terminou com achados). `parcial`: saída diferente de 0, mas o envelope trouxe `data`. `erro`: não terminou |
| `error_code` | texto ou `null` | Código estável do erro; nunca a mensagem |
| `summary` | objeto | Contagens, booleanos e identificadores curtos do `data` do envelope; lista vira `<chave>_count`; um nível de objeto é achatado (`summary.successes`); no máximo 16 itens. Sem texto livre, sem mensagem, sem corpo do alvo |

`secret set` e `secret delete` guardam só o subcomando e o **NOME** (primeiro argumento): sem flags e sem resumo. Nenhum valor de segredo passa pela CLI nesses comandos (a senha é lida por prompt, ADR 0030).

### Leitura

```python
from harness_dast.application.command_journal import load_journal_for_run

entries: tuple[JournalEntry, ...] = load_journal_for_run(store, product, run_id)
```

Devolve, em ordem cronológica, os comandos que pertencem ao teste `run_id`: do fim do teste anterior até o fim deste (regra em `domain.command_journal.slice_for_run`). Inclui `init`, `profile validate`, `doctor` e `stack up`, que ainda não têm execução. O "fim" de um teste é o último comando com o `run_id` dele antes do primeiro comando de uma execução mais nova; um `report` refeito depois, sobre um teste antigo, não engole o teste seguinte. Comando de outra execução dentro do intervalo fica de fora. Sem comando dessa execução, devolve `()`. Linha corrompida, de versão desconhecida ou com campo a mais é pulada e contada no log (`diario_linhas_puladas`); `store.load(produto)` devolve também `skipped_lines`.

Frase em português simples de cada comando: `domain.command_translation.translate_command("probe")` (tabela fixa; um teste falha se a árvore da CLI tiver comando sem tradução; comando fora da tabela devolve uma frase honesta dizendo que não há tradução). **Quem criar um comando novo precisa acrescentar a tradução.**

## Explicação de falha (`domain/finding_explain.py`)

`explain_finding(finding)`, `explain_zap_alert(plugin_id=, cwe=, title=)` e `explain_authz_technique(technique)` devolvem uma `FindingExplanation`: `title`, `what_happened`, `why_it_matters`, `what_to_do` (passos, cada um com `who`), `who` (`QA`, `dono do produto` ou `time de desenvolvimento`), `technical_name` (etiqueta cinza), `key` e `known`. Chave: regra do ZAP primeiro, depois o CWE; as quatro técnicas do `authz` têm entrada própria. Tipo desconhecido recebe a explicação genérica (`known=False`, `key="desconhecido"`) que cita só o nome da regra, limpo e cortado em 80 caracteres. O texto é fixo no código, nunca vem do alvo, não usa "seguro" nem "aprovado", não promete que a correção resolve e nunca muda severidade, confiança ou status. O `fix_hints` continua sendo a direção sugerida de correção do `report.md` e do `report.html`.

## Degrau de confiança (`domain/finding_confidence.py`)

`confidence_step(finding, triage=None, *, confirmed_by_person=False)` devolve `a confirmar`, `prova forte` ou `confirmada`:

- `prova forte`: há evidência guardada, o ZAP apontou um trecho dela e propôs confiança alta ou confirmada, e o agente não suspeita de falso positivo;
- `a confirmar`: qualquer outro caso, inclusive quando o agente suspeita de falso positivo;
- `confirmada`: **só** com `confirmed_by_person=True`.

**Lacuna:** o `triage.json` ([relatorio.md](relatorio.md#triagem-triagejson)) não tem campo que diga que uma pessoa confirmou: seus quatro campos são escritos pelo agente. Hoje nada alimenta `confirmed_by_person`, e o terceiro degrau não é alcançável pela CLI. Fechar a lacuna pede um campo aditivo, escrito por uma pessoa (quem e quando), em ADR próprio. O contrato do `triage.json` não foi alterado.

## Como reproduzir à mão (`domain/manual_repro.py`)

`build_manual_repro(finding, account="user_a")` devolve uma `ManualRepro` ou `None` (sem evidência guardada ou linha de requisição ilegível): `method`, `base_url` (sempre `$BASE_URL`), `target` (caminho e consulta relativos), `account` (apelido), `headers` (nome e, quando mostrável, valor: `Bearer $TOKEN`, `$TOKEN`, `$CSRF_TOKEN` ou um `Content-Type` seguro; cabeçalhos de transporte somem), `body` (ou `None`), `received_status`, `response_excerpt` (até 40 linhas), `response_total_lines`, `response_cut` e `personal_data_masked`. CPF, e-mail e telefone formatado são mascarados por padrão (`***.***.***-**`, `***@***`, `(**) *****-****`); telefone sem hífen não é reconhecido. O token nunca aparece. O texto da evidência é dado do alvo: o painel o mostra sempre como texto.
