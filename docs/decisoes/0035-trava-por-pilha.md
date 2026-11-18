# 0035. Trava exclusiva por pilha

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** revisão do consultor e plano do ciclo V1.3 a V1.8 ([`docs/plans/2026-11-14-ciclo-v1-3-a-v1-8.md`](../arquivo/plans/2026-11-14-ciclo-v1-3-a-v1-8.md)), item "Trava por pilha". Estende o [ADR 0010](0010-contrato-json-da-cli-e-codigos-de-saida.md) (novo código de erro e de saída) e usa a pasta de estado do [ADR 0033](0033-diario-de-comandos.md).

## Contexto

Verificado no código: cada `probe` abre uma sessão limpa no ZAP (`core/action/newSession` com sobrescrita, em `adapters/zap/api_client.py`, chamada por `application/probe.py`), a regra do Replacer que injeta o token é global no ZAP e o contexto e o histórico também. Não existe trava de execução. Duas execuções na mesma pilha (ZAP e proxy) se corrompem: uma apaga o histórico e o contexto da outra, a regra de token de uma vale para as requisições da outra, e o relatório pode sair "sem achado" ou com evidência trocada, sem erro nenhum. A falha é silenciosa, o pior tipo para uma ferramenta que diz o que é seguro.

O que identifica "a pilha" hoje:

- `hdast stack up` mantém **uma** pilha gerenciada por pasta de estado: um só `stack.json` em `HDAST_STATE_DIR` (padrão: `%LOCALAPPDATA%/hdast` no Windows, `$XDG_STATE_HOME/hdast` ou `~/.local/state/hdast` no resto), um só projeto compose (`hdast`, mais `hdast-pilotrun` para a Clínica Piloto), uma só porta do ZAP e uma só do proxy (`HDAST_ZAP_HOST_PORT`, `HDAST_PROXY_HOST_PORT`) e um só `policy.json`.
- Os comandos seguintes (`probe`, `scan`, `authz`, `run`) descobrem o ZAP pela configuração efetiva: o `HDAST_ZAP_BASE_URL` do ambiente, ou, na falta dele, o `zap_url` do `stack.json` da mesma pasta de estado.

Ou seja: a pasta de estado é o que liga todos os comandos à mesma pilha. Quem usa duas pastas de estado diferentes tem, em regra, duas pilhas diferentes.

## Decisão

Vamos tomar uma **trava exclusiva por pilha** no início de todo comando que toca o ZAP ou o alvo por ela, e soltá-la sempre.

**Identidade da pilha.** A pasta de estado (`HDAST_STATE_DIR` ou o padrão do sistema). A trava é o arquivo `stack.lock` dentro dela, ao lado de `stack.json` e fora de `runs/` (dois produtos e duas pastas de `runs/` ainda usam o mesmo ZAP). Um produto não tem trava própria: a pilha é uma só para todos os produtos da pasta de estado.

**Conteúdo.** JSON com `schema_version`, `lock_id` (identificador único da tomada, hexadecimal, sorteado a cada tomada), `command` (`probe`, `scan`, `authz`, `run`, `stack up`, `stack down`), `product`, `pid` e `started_at` (ISO 8601 com fuso). Não há segredo nele. O `run_id` não serve de identificador porque o `run` só o conhece depois de tomar a trava; o `lock_id` é a identidade da tomada e aparece na mensagem de quem é recusado.

**Criação atômica e exclusiva.** O texto completo é gravado num arquivo temporário na mesma pasta e publicado com `os.link` para `stack.lock`. `os.link` falha se o nome já existe (`FileExistsError`: pilha ocupada) e o arquivo nasce completo. Um `O_EXCL` seguido de escrita deixaria uma janela em que outro processo lê uma trava vazia e a trataria como lixo. Funciona em NTFS e em sistemas POSIX.

**Soltar.** O bloco `with` do caso de uso solta a trava em `finally`: sucesso, erro esperado (`HarnessError`), exceção inesperada, `KeyboardInterrupt` e `SystemExit`. Só apaga se o arquivo ainda tiver o conteúdo que este processo gravou. Falha ao soltar é registrada em log e não esconde o resultado nem o erro do comando; a trava que sobrar fica órfã quando o processo termina e é retomada pela próxima execução.

**Trava órfã.** O domínio decide (`domain/stack_lock.py`, puro): `judge_lock` recebe o dono lido do arquivo e "o processo está vivo?" e devolve `HELD`, `ORPHAN` ou `UNREADABLE`. O relógio e a pergunta "processo vivo?" entram por porta. Processo morto: a trava é retomada (log de aviso) apagando-a só se o conteúdo ainda for o da trava órfã lida, sob um arquivo de exclusão (`stack.lock.guard`, criado com `O_EXCL`, abandonado depois de 30 s), para que duas execuções que retomam ao mesmo tempo não apaguem a trava nova uma da outra; quem perde relê e vê um dono vivo. **Processo vivo: a trava nunca é apagada**, por mais velha que seja; a recusa diz o PID e as saídas, sem prometer o que não acontece: se a execução citada existe, esperar ou rodar `hdast stop` **e esperar o processo sair** (o `stop` para o trabalho, mas não solta a trava; quem a solta é a própria execução ao terminar, e `stack down` também fica bloqueado até lá); se uma pessoa conferiu que não há execução nenhuma (outro programa reaproveitou o número do processo), ela apaga o arquivo de trava, cujo caminho a mensagem traz. Apagar é ação de pessoa: não existe comando que apague trava de processo vivo. Na dúvida sobre o processo (sem permissão para consultar), conta como vivo. No Windows a consulta usa `OpenProcess` e `GetExitCodeProcess`, porque `os.kill(pid, 0)` lá encerra o processo.

**Arquivo de trava vazio, corrompido ou malformado.** Falha fechada com `STACK_BUSY`: não se sabe de quem é, então ninguém o apaga sozinho. A mensagem diz o caminho e manda conferir com `hdast stack status` e apagar à mão se nenhuma execução estiver rodando. Isso só acontece por edição manual ou disco corrompido (a criação atômica não deixa arquivo pela metade).

**Erro e código de saída (mudança de contrato do envelope, ADR 0010).** Novo `StackBusy(HarnessError)` com `error.code = STACK_BUSY` e novo código de saída **8** (`ExitCode.BUSY`). Mensagem: "A pilha está ocupada por `<comando>` do produto `<produto>` (id ..., processo ..., desde ..., há ...)." e dica: esperar terminar, ou `hdast stop` e esperar o processo sair; só uma pessoa, conferindo que não há execução (PID reaproveitado), apaga o arquivo de trava, e a dica diz o caminho. O 8 é novo e não reaproveita nenhum existente: o chamador (agente ou CI) precisa distinguir "tente depois, nada deu errado" de erro de configuração (2), escopo (3), ambiente (4) e ferramenta (5). Mudança aditiva: um valor novo de `error.code` e de saída, sem alterar os campos nem os códigos existentes; o teste de contrato e `docs/reference/` são atualizados.

**Quais comandos tomam a trava.**

| Comando | Toma? | Motivo |
| --- | --- | --- |
| `probe`, `scan`, `authz` | Sim, exceto com `--dry-run` | Abrem sessão e contexto no ZAP e mandam requisições. A simulação só planeja, não toca o ZAP nem o alvo |
| `run` | Sim, **uma vez** para a sequência inteira (preflight, probe, scan, authz, report) | As etapas usam os casos de uso direto, não os comandos; por isso o `run` nunca se bloqueia a si mesmo |
| `stack up`, `stack down` | Sim | Recriam ou derrubam os contêineres: acontecer debaixo de uma execução a destruiria. A pessoa que quer derrubar com algo rodando usa `hdast stop` antes |
| `preflight` | Não | Só lê a versão do ZAP e confere login e alvo; não abre sessão, não altera contexto nem regra do ZAP. Tomar a trava o impediria de rodar de dentro de uma execução (`doctor`, diagnóstico) sem ganho de segurança |
| `stack status` | Não, e **mostra** quem ocupa | Campo `lock` do `data` e uma linha no texto: `held`, `orphan` ou `unreadable`, com comando, produto, id, processo e início |
| `stop` | Não, nunca | É a parada de emergência: precisa funcionar com a pilha ocupada, e não mexe na trava (o dono a solta ao terminar) |
| `report`, `panel`, `cleanup`, `doctor`, `init`, `profile`, `spec`, `secret`, `version` | Não | Não tocam o ZAP (a limpeza fala com o banco do produto, não com a pilha) |

**Camadas.** Regra de decisão, formato e mensagens em `domain/stack_lock.py`; caso de uso `StackLockService` em `application/stack_lock.py`; portas novas `StackLockFile` e `ProcessProbe` em `application/ports.py`; arquivo de trava em `adapters/storage/stack_lock.py` e consulta de processo em `adapters/system_process.py`; montagem em `cli/stack_lock_composition.py`, usada pelos comandos. O modelo `StackLockInfo` entra em `StackReport` (`lock`). Sem dependência nova.

**Porta nova (justificativa, CLAUDE.md).** `StackLockFile` é a fronteira com o sistema de arquivos e `ProcessProbe` é a fronteira com o sistema operacional (processo vivo). Os dois precisam de dublê de teste: sem eles não se prova "trava de processo vivo respeitada" e "trava órfã retomada" sem criar processos e arquivos de verdade em todo teste (o que existe também, nos testes do adaptador). Há segunda implementação real: a memória nos testes.

## Alternativas consideradas

- **Trava em `runs/<run_id>/`.** Descartada: cada execução tem a própria pasta, então duas execuções nunca se veriam. A trava tem de ser da pilha, não da execução.
- **Trava por produto.** Descartada: dois produtos diferentes usam o mesmo ZAP e se corrompem do mesmo jeito. A pilha é a unidade.
- **Bloqueio do sistema operacional (`msvcrt.locking`, `fcntl.flock`).** Solta sozinho quando o processo morre, o que seria bom, mas é diferente em cada sistema, não deixa dizer quem é o dono (a mensagem útil) e não vale entre contêineres e hosts montados em rede. Fica um arquivo com dono explícito.
- **Esperar a trava aparecer (fila) em vez de recusar.** Descartada: um agente travado esperando horas sem dizer nada é pior que um erro claro. Falhar fechado com a identidade de quem ocupa deixa a pessoa ou o agente decidir.
- **`O_EXCL` e depois escrever.** Descartada pela janela de arquivo vazio descrita acima.
- **Tempo máximo da trava (expira sozinha).** Descartada: apagar a trava de um processo vivo é exatamente o dano que a trava evita. Execução longa legítima (até 8 horas) não pode perder a trava.
- **Identificar a pilha pela URL do ZAP.** Cobriria duas pastas de estado apontando para o mesmo ZAP, mas faria a identidade depender de configuração que muda por comando (`HDAST_ZAP_BASE_URL` pode estar em um e não em outro). Ficou como limitação abaixo.
- **Tomar a trava também no `preflight`.** Descartada, ver tabela.

## Consequências

- Duas execuções na mesma pilha deixam de se corromper em silêncio: a segunda sai com `STACK_BUSY` (8), antes de tocar o ZAP ou o alvo, dizendo quem ocupa.
- O agente e o CI ganham um código para "tente depois". As skills e os guias devem dizer isso (item do coordenador, fora desta entrega).
- `stack up` e `stack down` passam a recusar enquanto há execução: quem quer derrubar a pilha de uma execução em andamento roda `hdast stop` primeiro, espera o processo terminar e então derruba.
- **Limitações assumidas.** (1) A identidade é a pasta de estado: duas pastas diferentes apontando para o mesmo ZAP (por `HDAST_ZAP_BASE_URL`) não se enxergam. (2) A consulta de "processo vivo" é local: trava em pasta de estado compartilhada entre máquinas não é detectada como órfã (falha fechada: continua recusando). (3) PID reaproveitado por outro processo depois de a execução morrer faz a trava órfã parecer viva (falha fechada). A saída é uma pessoa conferir (`stack status` e o gerenciador de tarefas) e apagar o arquivo de trava, que a mensagem de recusa cita pelo caminho; `hdast stop` não resolve, porque não solta a trava e não há execução a parar. (4) Execuções concorrentes na mesma pilha, com a taxa dividida, são tema da V1.7 e mudam o [ADR 0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md); esta trava é a base que ela usa, não a contradiz.
- **Não provado nesta entrega:** duas execuções reais com Docker e ZAP. Foi provado por teste unitário e de contrato (a trava é o arquivo real; os casos de uso e a rede são falsos).
- Se o ADR for aceito, `CHANGELOG.md`, `docs/roadmap.md`, `docs/adr/README.md`, o `CLAUDE.md` e as skills `run-scan` e `test-product` devem citar a trava e o código 8.
