# 0024. `hdast run`: etapas encadeadas em um processo, `run.json`, trava de emergência e Oracle na pilha

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** M5; detalha os ADRs [0010](0010-contrato-json-da-cli-e-codigos-de-saida.md), [0019](0019-pilha-gerenciada-politica-por-execucao-e-login-pelo-proxy.md), [0020](0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md) e [0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md)

## Contexto

Quatro comandos separados fazem cada conta logar mais de uma vez (cada processo tem seu cache de tokens e seu orçamento de login) e deixam ao agente a tarefa de ler o código de saída de cada um. A parada de emergência (`hdast stop`) só negava pedidos no proxy: o `scan` interpretava isso como "alvo sem resposta" (saída 6). O contrato público (envelope e códigos de saída) não muda, mas o comando novo e o arquivo `run.json` são contrato novo.

## Decisão

Vamos:

1. Criar `hdast run <produto>` (`--seed`, `--skip-scan`, `--fail-on`, `--compare`, `--max-minutes`, `--json`), caso de uso `RunPipeline` em `application/run.py`. Roda `preflight`, `probe`, `scan` e `report` no mesmo processo, com **um** cache de tokens e **um** orçamento de login. Para no primeiro estágio que falha e sai com o código DELE (a tradução do estado final de cada etapa em erro mora em `application/stage_errors.py`, usada também pelos comandos soltos). O código `1` continua sendo do `report`.
2. Sempre gravar `run.json` (`domain/run_summary.py`): estágios (`ok`, `failed`, `interrupted`, `skipped`, `not_run`), tempos, código de saída, artefatos existentes, achados por severidade, `stop_requested` e o comando de limpeza. Fica na pasta do `probe` (a do preflight se o `probe` não começou, ou uma pasta própria se nenhuma foi criada).
3. Nunca rodar a limpeza. O resumo traz o comando exato (`hdast cleanup <produto> --run <id> --dry-run`) quando o perfil tem `cleanup`; quem confirma é uma pessoa.
4. Criar a porta `KillSwitch` (adaptador `FileKillSwitch`, lê o arquivo `KILL` ao lado da política do proxy). O `RunGate` a consulta antes de todo envio e antes de cada consulta de andamento do `scan` (a cada 2 s): trava acionada levanta `KillSwitchEngaged` (um `WindowClosed`), a varredura em curso é parada, as regras do Replacer são removidas e o artefato parcial é gravado. O `run` classifica o fim como interrompido: saída **130**, `status: interrupted`, `stop_requested: true`. Ctrl+C tem o mesmo desfecho (130). Comandos soltos (`scan`, `probe`) também respeitam a trava e saem com 3, como qualquer janela fechada.
5. `hdast stop` lê os `scan-progress.json` com `status: running` atualizados há até 120 s ANTES de acionar a trava e diz o que estava rodando (`scans_running`).
6. `hdast stack up clinica-piloto --oracle`: anexa o perfil `oracle` do compose do piloto e um arquivo que publica o banco só em `127.0.0.1:21521`; gera as senhas do Oracle, do usuário `clinica` e do usuário de limpeza (guardadas só no estado local) e fixa DSN e usuário da limpeza. A criação do usuário de banco da limpeza continua sendo ato humano (`lab/pilot/cleanup/create-cleanup-user.sql`).

## Alternativas consideradas

- **Um `run` que chama os comandos como subprocessos.** Perde o cache de tokens e o orçamento de login compartilhados e esconde os estados parciais. Descartada.
- **Um código de saída novo para a trava.** Mudaria o contrato dos códigos. O 130 já significa "interrompido deliberadamente".
- **Criar o usuário de limpeza pela própria CLI.** Daria à CLI privilégio de DDL no banco; a limpeza existe justamente para ter o mínimo. Descartada.

## Consequências

- O agente tem um comando para o caminho normal e `--skip-scan` para o laço de regras de dados.
- A trava passa a parar a varredura em até um intervalo de consulta (2 s), em vez de produzir uma falsa falha de alvo.
- Estágios compartilham `RunGate`/`LoginBudget` por injeção opcional; os comandos soltos seguem funcionando como antes.
- Processo morto à força não passa pelo tratamento de interrupção; as regras do Replacer são varridas na próxima partida.
