# 0033. Diário de comandos por produto

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** painel da execução ([`docs/design/execution-panel/`](../arquivo/design/execution-panel/README.md)), aba Terminal: "lista de comandos do agente, com hora, resultado e resposta" é um dado que ainda não existe. Estende o [ADR 0010](0010-contrato-json-da-cli-e-codigos-de-saida.md) (envelope e códigos de saída) sem alterá-lo.

## Contexto

A aba Terminal mostra cada comando `hdast` que o agente deu, com a hora, uma frase que o traduz, o estado numa palavra e a resposta. Hoje nada disso fica gravado: o envelope vai para o stdout e some. Dois fatos pesam na escolha de onde guardar:

1. Comandos como `init`, `profile validate`, `doctor` e `stack up` ainda não têm execução (`run_id`), mas precisam aparecer no painel do teste seguinte. Um arquivo dentro de `runs/<run_id>/` não os alcançaria.
2. O que se grava vem de um agente e de um alvo: flags e argumentos livres podem carregar segredo, e a resposta pode conter texto do alvo. Nada disso pode ir para um arquivo que as pessoas abrem e compartilham.

## Decisão

Vamos gravar uma linha por invocação do `hdast` num diário **por produto**, em JSONL, na pasta de estado da ferramenta, fora do repositório e fora de `runs/`.

### Onde

`<pasta de estado>/journal/<produto>.jsonl`. A pasta de estado é a que já existe para a pilha (`HDAST_STATE_DIR`; senão `%LOCALAPPDATA%\hdast` no Windows; senão `$XDG_STATE_HOME/hdast` ou `~/.local/state/hdast`; `adapters/storage/stack_state.default_state_dir`). Comandos sem produto (`version`, `stop`, `stack status`, `secret set`...) vão para `_sem-produto.jsonl`. O nome do arquivo só aceita slug de produto (`journal_file_stem`); qualquer outro valor cai em `_sem-produto`, então nada escapa da pasta. Pasta 0700 e arquivo 0600 no POSIX; no Windows vale a ACL herdada. Só acréscimo, uma linha por escrita.

### O que cada linha tem (`schema_version: 1`)

`started_at` e `finished_at` (com fuso; o relógio entra por porta, `Clock`), `command` (subcomando por extenso: `probe`, `stack up`), `product`, `run_id` (do envelope; senão de `--run`), `flags` (nome e, quando há, valor), `args` (posicionais além do produto), `exit_code`, `state`, `error_code` e `summary`.

- **`state`** é uma palavra da lista fechada de `docs/design/execution-panel/system/formats.html`: `ok` (saída 0, ou 1 quando a varredura terminou com achados), `parcial` (saída diferente de 0, mas o envelope trouxe `data`) e `erro` (não terminou).
- **`summary`** é tirado do envelope da CLI: números, booleanos, identificadores curtos (`[A-Za-z0-9_.:-]`, até 64 caracteres), listas viram `<chave>_count`, um nível de objeto é achatado (`summary.successes`), no máximo 16 itens. Chave de nome sensível e texto livre são descartados. Nunca entra a mensagem do erro nem corpo do alvo; do erro vai só o código.
- **Mascaramento** (em `domain/command_journal.py`, testado): flag de nome sensível guarda `***` no lugar do valor; os demais valores e argumentos livres passam por `redact_text` (a redação que o projeto já usa: segredos registrados na execução, JWT, `Bearer`, CPF, e-mail e sequências longas) e são cortados em 120 caracteres. `secret set` e `secret delete` guardam **só o subcomando e o NOME**, sem flags nem resumo.
- A **tradução** de cada comando para português simples **não** é gravada: sai de uma tabela fixa no domínio (`domain/command_translation.py`), e um teste falha se existir comando na árvore da CLI sem tradução. Assim melhorar a frase vale também para diários antigos.

### Onde é gravado

No único ponto por onde todo comando passa: `run_app`, em `cli/app.py`, depois do desfecho. O comando não sabe do diário. Para ler o envelope sem tocar em cada comando, `cli/output.emit` entrega uma cópia de cada envelope a um coletor da invocação (um `ContextVar` definido por `capture_envelopes`; o objeto do módulo nunca muda, só o valor dentro do contexto da invocação). Subcomando, flags e produto vêm da árvore de comandos do Typer, só do que foi digitado (`--help` e comando desconhecido não são registrados).

**Falha ao gravar nunca derruba o comando:** `record_invocation` captura qualquer exceção, registra `diario_nao_gravado` no log estruturado (só a classe do erro) e o código de saída não muda.

### Leitura e recorte por teste

O diário é por produto, mas o painel é por teste. `slice_for_run` (domínio, puro) recorta do fim do teste anterior até o fim do teste pedido. O "fim" de um teste é o último comando com o `run_id` dele que aparece antes do primeiro comando de uma execução mais nova; assim um `report` refeito depois sobre um teste antigo não engole o teste seguinte. Comandos sem `run_id` dentro do intervalo pertencem ao teste. A leitura é tolerante: linha corrompida, de versão desconhecida ou com campo a mais é pulada e contada (`JournalLoad.skipped_lines`). A função pública para o painel é `application.command_journal.load_journal_for_run(store, product, run_id)`.

### Porta

`CommandJournalStore` em `application/ports.py` (`append`, `load`): existe por ser fronteira com o sistema de arquivos e para testar sem disco. Adaptador: `adapters/storage/command_journal.py`.

## Alternativas consideradas

- **Arquivo dentro de `runs/<run_id>/`.** Descartada: os comandos anteriores à primeira execução (`init`, `doctor`, `stack up`) não têm onde ficar, e `runs/` costuma ser anexado a chamados.
- **Um diário global.** Descartada: mistura produtos, e o painel de um produto teria de filtrar tudo. Por produto também limita o que um arquivo compartilhado revela.
- **Gravar a saída humana ou o envelope inteiro.** Descartada: o envelope traz o que o alvo respondeu. O resumo por regra fixa dá ao painel contagens e identificadores sem esse risco.
- **Gravar a tradução em cada linha.** Descartada: congela o texto e duplica a tabela; a tabela única corrige tudo de uma vez.
- **Chamar o diário dentro de cada comando.** Descartada: espalharia a regra por 20 comandos e um comando futuro esqueceria de chamá-la.
- **Guardar o diário no repositório.** Descartada: pode conter nomes de produto e caminhos locais, e o repositório não é lugar de dado de execução.

## Consequências

- Cada invocação passa a gravar uma linha pequena na pasta de estado; o custo é uma escrita de acréscimo. Nos testes, a fixture `autouse` de `tests/conftest.py` já aponta `HDAST_STATE_DIR` para uma pasta temporária, então nenhum teste escreve no estado real.
- `emit` ganha um efeito colateral invisível (copiar o envelope para o coletor, quando há um). Fora de `run_app` o coletor não existe e nada muda.
- O diário não é prova de auditoria: quem escreve é o mesmo processo que roda o comando, e o arquivo é só acréscimo, não imutável. A trilha de auditoria de verdade continua sendo `audit.jsonl` do proxy.
- Duas invocações em paralelo no mesmo produto acrescentam linhas curtas; a ordem final pode divergir do tempo por milissegundos, e por isso o recorte ordena por `started_at`.
- Mudar o formato da linha exige subir `schema_version`; leitores antigos pulam e contam as linhas novas.
- Fica para depois: tokens e tempo por comando (`agent-metrics.json`, ADR a definir), que não vêm do `hdast` e não entram neste diário.

## Nota de 2026-11-14 (ADR ainda Proposto): o painel final mostra o próprio comando

O painel que `run`, `report` e `panel` geram dentro do comando nascia antes de a linha dele existir no diário, e o Terminal dizia "teste anterior à versão 1.2". Decisão: `run_app` grava a linha e, em seguida, refaz o painel (e os índices) do teste desses três comandos quando terminaram com sucesso (`cli/journal_recording.py`). Descartado: uma linha "em andamento" no diário (o formato é fechado, e um comando que nasce sem `run_id` não se liga ao teste). O recorte `slice_for_run` ignora o `run_id` dos comandos `stack` e `stop`: ele é o da pilha, anterior ao teste, e não de outro teste; assim o `stack up` entra no recorte do teste que usou a pilha. O estado vazio distingue "não há diário nenhum" (`PanelView.commands` é `None`) de "o diário existe, mas não tem comando deste teste" (`commands` é uma tupla vazia).
