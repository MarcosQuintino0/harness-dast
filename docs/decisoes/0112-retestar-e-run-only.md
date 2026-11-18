# 0112. `hdast retestar` e `run --only`

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** pacote 2.5 da reestruturação (reteste visível). Usa o `--compare` do `report` ([ADR 0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md)), o `run` encadeado ([ADR 0024](0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md)), a aprovação do escopo ([ADR 0037](0037-aprovacao-humana-do-escopo.md)) e o contrato JSON ([ADR 0010](0010-contrato-json-da-cli-e-codigos-de-saida.md)).

## Contexto

O ciclo de uso é achar, relatar, o time do produto corrigir e **retestar**. O reteste existia só como `hdast run --compare RUN_ID`: uma varredura inteira, com a comparação escondida no relatório (`new`, `persistent`, `not_observed`). Quem quer saber "este achado ainda acontece?" precisa repetir tudo e achar a linha certa.

Dois cuidados pesam:

- **Honestidade.** O varredor não é determinístico e os limites cortam a cobertura. "O fingerprint não apareceu" não significa "corrigido". O texto ao usuário não pode induzir essa leitura (`COMPARISON_NOTICE`).
- **Controles.** Reteste toca o alvo. Não pode existir caminho de tráfego que fuja da aprovação do escopo, da pilha atual (`STACK_STALE`), da janela, do prazo, do limite por segundo, da trava da pilha e da mutação pendente.

## Decisão

Vamos criar `hdast run --only` e `hdast retestar`, sem caminho novo de tráfego.

### 1. `run --only OPERATION_ID` (repetível)

O `probe`, o `scan` e o `negative` já aceitavam `--only`; o `run` passa a aceitá-lo e a repassá-lo aos três. O `authz` roda inteiro (só lê). A seleção só **reduz**: nunca amplia escopo, limites ou autorização. Fica em `run.json` (`options.only`, padrão vazio). Operação inexistente no OpenAPI é erro de uso (`CONFIG_ERROR`, saída 2) com dica, levantado antes de qualquer envio.

### 2. Classificação pura em `domain`

`classify_retest` (`domain/finding_diff.py`) recebe os achados escolhidos, os achados novos e as operações varridas agora, e devolve um resultado por achado anterior:

- `reproduced`: o mesmo fingerprint apareceu de novo;
- `not_reproduced`: a operação foi varrida agora e o fingerprint não apareceu;
- `not_tested`: a operação não foi varrida (corte, limite ou falha de alcance), ou o achado não tem operação.

`compare_findings` usa a mesma função, então `operation_scanned_now` e o reteste não podem divergir. `domain/retest.py` escolhe os achados e monta o `retest.json`.

### 3. Caso de uso e comando

`hdast retestar PRODUTO --run RUN_ANTERIOR [--finding FINGERPRINT]... [--max N] [--fail-on L] [--max-minutes N]`:

- Sem `--finding`, escolhe os achados de severidade alta e média da execução anterior (do mais grave ao menos), até `--max` (padrão 10, de 1 a 30). Achado sem operação do `probe` não entra por padrão e é recusado se pedido.
- Monta um `RunRequest` com `only` (operações dos achados, sem repetição), `compare` (a execução anterior), `authz` e `negative` desligados (só reduz: o reteste classifica os achados do varredor) e entrega ao **mesmo** `RunPipeline` do `run`. Quem aplica os controles é o pipeline; o caso de uso não envia nada.
- O perfil é carregado primeiro (aprovação e pilha atual, via repositório verificado); sem aprovação nada mais acontece. Depois valida a execução anterior (existe, mesmo produto, mesma versão de fingerprint) e a seleção.
- Grava `runs/<novo>/retest.json` (`schema_version: 1`): execução anterior, nova, `only`, contagem por resultado, um item por achado com `result` e `reason`, e `notice` (`COMPARISON_NOTICE`). Se o `run` parar antes de gerar `findings.json`, não grava e devolve o erro dele.
- Envelope JSON: `data` = `{"retest": <retest.json ou null>, "run": <run.json>}`, `ok` e `error` como no `run`.
- Saída: a do `run` se ele falhou; senão `1` se algum achado **reproduzido** tem severidade no limiar de falha (`scan.fail_on` do perfil, que `--fail-on` só endurece); senão `0`. Achado novo não muda a saída do reteste (está no relatório do `run`).
- Texto: "não reproduzido nesta execução" e o aviso. Nenhuma saída diz "corrigido".

## Alternativas consideradas

- **Só documentar `run --compare`.** Não resolve a visibilidade e deixa a varredura inteira como único jeito de retestar.
- **Um estágio novo, com envio próprio.** Duplicaria os controles do `run`; qualquer divergência seria um caminho sem trava. Descartado.
- **Dizer "corrigido" quando a operação foi varrida.** O varredor é não determinístico; seria afirmação sem base.
- **Manter `authz` e `negative` no reteste.** Mais tráfego sem ganho: os achados classificados são os do `findings`.

## Consequências

- Retestar vira um comando, com resposta por achado e o limite de leitura declarado.
- `run --only` serve também ao laço de ajuste de uma operação só.
- `run.json` ganha `options.only` (aditivo; arquivos antigos leem como vazio).
- O reteste só cobre achados do varredor; achados de `authz`, `negative` e sinais da cerca continuam exigindo um `run` completo.
- Um achado reproduzido não é prova nova: a verificação e a declaração humana seguem em `confirm` e `finding acknowledge`.
