# Relatório da versão 1.3.0

Data: 2026-11-14. Branch: `feat/v1-3`. Plano: [docs/plans/2026-11-14-ciclo-v1-3-a-v1-8.md](../plans/2026-11-14-ciclo-v1-3-a-v1-8.md).

## 1. Resumo

**Número:** 1.3.0 (a anterior é a 1.2.0).

**Objetivo:** deixar o uso da ferramenta mais seguro e mais fácil. Três proteções novas, que ficam no código da CLI e não dependem do agente de IA, e uma entrevista mais curta para cadastrar um produto.

**Funcionalidades:**

1. **Trava por pilha** (ADR 0035): só um comando por vez mexe no ZAP e no alvo.
2. **Carta estruturada** (ADR 0036): a carta de autorização vira um formulário (`carta.yml`) e a CLI gera o perfil a partir dele.
3. **Aprovação humana do escopo** (ADR 0037): uma pessoa trava os blocos de proteção do perfil; se o perfil mudar depois, os comandos que tocam o alvo recusam.
4. **Entrevista inicial nas skills:** as perguntas feitas de uma vez só, resumo antes de atacar, consulta da aprovação e tratamento de pilha ocupada.
5. **Documentos desatualizados corrigidos**, com verificador de links e teste de vazamento do gabarito para a cópia cega.
6. **Correção** na redação de segredos, que apagava a versão do protocolo.

**Mudança incompatível de uso:** todo perfil existente precisa ser aprovado uma vez por uma pessoa (`hdast profile approve <produto>`). Sem isso, `preflight`, `probe`, `scan`, `authz`, `run`, `cleanup` e `stack up` recusam com `SCOPE_NOT_APPROVED`.

**O que a versão é e o que não é:** código e testes, mais uma prova com Docker da trava no laboratório. Nada foi provado contra produto real.

## 2. Alterações

### 2.1 Trava exclusiva por pilha

- **Como era:** nada impedia dois comandos ao mesmo tempo. Cada `probe` abre uma sessão limpa no ZAP e a regra que injeta o token é global; um segundo comando atrapalhava o primeiro sem aviso.
- **Como é agora:** `probe`, `scan`, `authz` (fora do `--dry-run`), `run`, `stack up` e `stack down` tomam a trava `stack.lock` na partida e a soltam sempre. Pilha ocupada: erro `STACK_BUSY`, **código de saída 8** (novo), com a mensagem dizendo quem ocupa. Trava de processo morto é retomada com aviso. `stop` e `stack status` nunca são bloqueados; `stack status` mostra `data.lock`.
- **Arquivos e componentes:** `domain/stack_lock.py` (decisão pura: ocupada, órfã ou ilegível), `application/stack_lock.py` (o caso de uso que segura a trava), `adapters/storage/stack_lock.py` (o arquivo de trava), `cli/stack_lock_composition.py`, `StackBusy` em `domain/errors.py`. Documentos: ADR 0035, `docs/reference/exit-codes.md`, `docs/reference/cli.md`.

### 2.2 Carta estruturada

- **Como era:** o agente lia a carta em texto livre e escrevia o `target.yml` à mão; erro de transcrição virava um perfil válido e diferente da carta.
- **Como é agora:** a pessoa (ou o agente, com ela) preenche o `carta.yml`, onde cada resposta é `{value, source}` e `source` é `carta`, `pessoa` ou `desconhecido`. `hdast init <produto> --from-letter <carta.yml>` gera os blocos `environment`, `openapi`, `scope`, `limits`, `auth` e `scan.strength`; `--check` confere sem criar. Qualquer pendência recusa a carta inteira (`LETTER_REJECTED`, saída 2, com `data.issues`). Carta com validade vencida é recusada (`AUTHORIZATION_EXPIRED`). A carta pronta traz `data.warnings` (permissão em `/**`, `DELETE` autorizado, caminhos proibidos vazios, validade acima de um ano) e `data.example_data`.
- **Arquivos e componentes:** `domain/letter_review.py` (revisão e `GENERATED_BLOCKS`), o caso de uso `InitFromLetter` (`application/init_from_letter.py`, recebe o `Clock`), o comando `init --from-letter`, o guia `docs/guides/modelo-de-autorizacao.md`. Documentos: ADR 0036 e `docs/reference/cli.md`.

### 2.3 Aprovação humana do escopo

- **Como era:** o perfil era imposto pela CLI, mas ninguém o travava. Um agente que "ajudava" ampliando um método ou tirando um caminho proibido produzia um perfil válido, mais largo que a autorização, e a CLI o obedecia.
- **Como é agora:** uma pessoa roda `hdast profile approve <produto>` num terminal interativo. A CLI calcula uma impressão digital dos blocos de proteção (versão 2 do cálculo: `environment`, `scope`, `limits`, as partes de `auth` que dizem para onde vão as credenciais e com que contas, e `scan`, `authz` e `cleanup` inteiros) e a grava em `approvals/<produto>.json` na pasta de estado. Todo comando que toca o alvo confere a impressão antes de abrir qualquer conexão e recusa com `SCOPE_NOT_APPROVED` (saída 3) dizendo quais blocos mudaram. `hdast profile approval` só lê o estado; `profile validate` mostra `data.approval`. Os ajustes de alcançabilidade (`probe`, `auth.csrf`, `auth.account_map`, `openapi`) continuam livres. Para a avaliação cega, `python -m evals.runner approve` aprova fora do agente.
- **Arquivos e componentes:** `domain/scope_fingerprint.py`, `application/scope_approval.py` (`ApprovedProfileRepository`), portas `ApprovalStore` e `ApprovalPrompt`, `cli/terminal.py`, `evals/runner`. O `.claude/settings.json` nega ao agente rodar o comando e gravar na pasta de aprovações. Documentos: ADR 0037.

### 2.4 Entrevista inicial nas skills e guias

- **Como era:** as perguntas ao dono do produto saíam aos poucos, ao longo do cadastro.
- **Como é agora:** uma rodada só (portões, endereço, escopo, modo do caminho, janela, limites, contas, força do ataque, dados de exemplo); resumo do que será atacado antes de atacar; consulta de `hdast profile approval` antes de tocar o alvo; `STACK_BUSY` tratado (esperar ou perguntar, nunca contornar). O guia de autorização passou a usar um produto fictício no exemplo.
- **Arquivos:** as skills em `.claude/skills/` (`onboard-product`, `fix-reachability`, `run-scan`, `test-product`) e os guias em `docs/guides/`.

### 2.5 Documentos desatualizados e verificadores

- **Como era:** vários documentos diziam o que já não era verdade, e nada pegava link quebrado.
- **Como é agora:** documentos corrigidos; `tests/contract/test_docs_links.py` percorre os `.md` e falha com link relativo (arquivo ou âncora) inexistente; `tests/contract/test_letter_guide.py` e o teste de vazamento barram caminho proibido, isca e termo de gabarito em toda a cópia entregue ao agente cego.

### 2.6 Redação de segredos

- **Como era:** com o endereço terminando em `token`, `basic` ou `bearer`, a regra de esquema tratava a versão do protocolo (`HTTP/1.1`) como credencial e a apagava. Era perda de evidência, não vazamento.
- **Como é agora:** a versão do protocolo fica. Há teste que reproduz o caso (commit `48988b0`).

## 3. Evidências

Arquivos em `C:\harness-dast-artefatos\v1.3\` (fora do repositório).

**Trava com Docker** (`trava-docker\timeline.txt` e `trava-docker\pytest-output.txt`). O teste `tests/integration/test_lab_stack_lock.py`, contra a Clínica Piloto real: um `probe` completo termina e solta a trava; um `scan --only buscarPacientesPorNome` começa (a 71,8 s); `stack.lock` aparece (74,0 s); `stack status` mostra a trava como `held` (77,4 s); um segundo `probe` sai com **código 8** e a mensagem "A pilha está ocupada por `scan` do produto clinica-piloto (id ..., processo ..., há menos de 1 min)" (79,8 s); o `scan` termina com saída 0 (97,5 s); o mesmo comando depois do fim do primeiro sai com saída 0 (103,8 s). `pytest`: 1 passou em 155,46 s.

**Carta, 49 casos de borda** (`qa\letters\results.txt`). Cada carta foi rodada com `--check` e criando, 98 execuções. Nove cartas válidas (a base e variações aceitas, como BOM e `DELETE` com citação) geraram perfil; as demais foram recusadas com saída 2: carta com campo desconhecido, YAML malformado, chave repetida, valor de modelo, senha literal, `base_url` fora do escopo, apelido repetido, limites absurdos e outras. Nenhuma saiu com código inesperado (só 0 e 2).

**Edição do perfil depois da aprovação** (`qa\edit\mut-results.txt`). 37 edições de um perfil aprovado: 21 foram detectadas como alteradas (`SCOPE_NOT_APPROVED`, saída 3, com o bloco certo na mensagem: `environment`, `scope.allow`, `scope.deny_paths`, `scope.path_mode`, `scope.authorization`, `scope.windows`, `limits`, `auth`, `scan`, `authz`); 3 foram recusadas já pela validação do perfil (saída 2); 13 foram aceitas (seguiram até o `PREFLIGHT_FAILED` por falta de segredo). Atenção: esse arquivo é do QA e **anterior à correção da impressão digital** (versão 2): entre as 13 aceitas estão edições de `scan` (`disable_rules`, `fail_on`, tetos de tempo), `authz` e `cleanup`, que era exatamente o defeito. Depois da correção, `scan`, `authz` e `cleanup` inteiros mudam a impressão, o que os testes unitários conferem; **não repeti a medição à mão**. Seguem livres por decisão: comentário, ordem de chaves, `probe`, `auth.csrf`, `auth.account_map`, codificação do formulário e `openapi`.

**Corrida pela trava** (`qa\race\race-out.txt`). Oito processos, 40 tentativas cada, disputando a mesma trava: 95 tomadas, **0 violações** de exclusão (dois processos dentro ao mesmo tempo) e nenhuma sobra de arquivo ao fim.

**Gates** (`qa\gates.txt`). Saída do QA antes das correções finais: ruff sem problemas, 761 arquivos formatados, mypy sem problemas em 632 arquivos, import-linter analisou 330 arquivos e 1952 dependências, pytest `6959 passed, 3 skipped, 66 deselected` em 171,60 s. Os números finais estão na seção 4.

## 4. Qualidade e testes

**Gates finais:**

| Gate | Resultado |
| --- | --- |
| `ruff check` | sem problemas |
| `ruff format --check` | 764 arquivos |
| `mypy` | sem problemas em 635 arquivos, nas duas plataformas (Windows e `--platform linux`) |
| `lint-imports` | 6 contratos mantidos |
| `vulture` | limpo |
| `pytest` | 7012 passaram, 0 falharam, 3 pulados, 67 desselecionados |

**Cobertura:** não medida nesta versão.

**QA independente:** um agente que não programou a versão testou pelos critérios de aceite e tentou quebrar. Parecer: **aprovado com ressalvas**, com 10 defeitos (D1 a D10), todos corrigidos ou registrados. A numeração D1 a D10 é da lista do QA, que não está guardada no repositório; a tabela abaixo mostra o que as correções do ciclo fizeram, pelo commit, sem repetir a numeração.

| Defeito | O que foi feito |
| --- | --- |
| Campos fora da impressão digital: editar `fail_on`, `disable_rules`, `public_operations`, tetos de tempo ou o alvo da limpeza mantinha "aprovado" | `scan`, `authz` e `cleanup` inteiros entram na impressão digital; versão 2 do cálculo; aprovações da versão 1 passam a valer como não aprovadas (commit `453306a`) |
| A recusa da trava dizia o que não era verdade sobre `stop` e sobre PID reaproveitado | Mensagem corrigida (commit `418f13a`) |
| Carta com autorização vencida era aceita | Recusada com `AUTHORIZATION_EXPIRED`; a carta pronta traz avisos (commit `dc8257a`) |
| Português das mensagens novas e das skills (gênero, frase embolada, mensagem da aprovação com parênteses aninhados) e uma skill dizendo que o `validate` recusa por aprovação | Textos e skills corrigidos (commit `c9ea492`) |
| Vazamento do gabarito para a cópia cega (exemplos que citavam a isca; `CHANGELOG.md` e roadmap na cópia) | Teste de vazamento sobre toda a cópia entregue ao agente cego; exemplos trocados por genéricos; arquivos fora da cópia (commits `e5d6eb7` e `518d5c7`) |
| Agente podia gravar na pasta de aprovações | `.claude/settings.json` nega gravação e o comando de aprovar (commits `3152013` e `a5e9e7f`) |
| Redação apagava a versão do protocolo | Corrigida com teste (commit `48988b0`) |
| Teste intermitente que era defeito real; PID do lançador no Windows no teste de integração | Veja a seção 5 (ajustes de integração em `ac344d6`; não detalho aqui o que não consegui conferir no código) |

Esta tabela cobre o que os commits mostram; se o dono quiser a lista D1 a D10 original, ela está com o QA (não confirmei no repositório que cada D tenha uma linha acima).

## 5. Problemas e decisões

**O que o QA achou:**

- **Campos fora da impressão digital.** Era o defeito mais sério: a aprovação passava por cima de mudanças que ampliam a carga ou escondem achados. Corrigido pelo critério "entra tudo que amplia o que é tocado e tudo que reduz o que é relatado".
- **Vazamento do gabarito.** O agente cego podia ler a isca do caso nos exemplos dos documentos. Corrigido e agora coberto por teste de contrato.
- **Teste intermitente que era defeito real.** Uma falha que só aparecia às vezes não era problema do teste, e sim defeito do código (registro do QA; o detalhe não está nos documentos do repositório).
- **PID do lançador no Windows** no teste de integração da trava: o PID do lançador não é o do comando; o apoio do teste de integração foi ajustado.

**Decisões:**

- **Aprovação exigida sempre, sem atalho.** Não há variável de ambiente, flag nem modo "laboratório" que pule a conferência, porque tudo que o agente pode ligar valeria também em produto real. No laboratório, a pessoa roda `profile approve` uma vez.
- **O conteúdo do script de limpeza fica fora da impressão digital.** O cálculo é do domínio puro e ler arquivo é de um adaptador (obrigaria todo comando a ler o script, até os que não limpam nada); o script é de autoria humana, o agente não o altera, e a limpeza continua exigindo confirmação digitada de uma pessoa. A configuração da limpeza (nomes de segredo, caminho do script, tabelas, teto de linhas) entra.
- **Rodada cega com pausa e retomada.** A rodada para no primeiro comando que toca o alvo (`SCOPE_NOT_APPROVED`); o coordenador aprova fora do agente com `python -m evals.runner approve` e a rodada continua.

## 6. Sugestões descartadas

Nenhuma nesta versão.

## 7. Débitos e não provado

- **`profile approve` num terminal de verdade:** os testes usam o dublê do terminal. A prova é do dono.
- **Entrevista com uma pessoa:** as skills foram conferidas por teste de contrato, não com alguém respondendo.
- **Rodada cega no fluxo novo:** não houve.
- **`python -m evals.runner approve`:** só testado com o caso mínimo.
- **Consulta de processo vivo da trava:** só implementada no Windows.
- **Perfil gerado pela carta:** não foi rodado de ponta a ponta com Docker.
- **Produto real:** nada foi provado.
- **ADRs 0026 e 0032 a 0037** continuam "Proposto"; aceitar é decisão do dono.
- **Itens "a confirmar"** continuam nos documentos (veja a tabela de itens em aberto do [roadmap](../roadmap.md)).
- **Cobertura** não foi medida.

## 8. Conclusão

A versão 1.3.0 entrega as três proteções planejadas e a entrevista nas skills, com todos os gates verdes e QA independente aprovado com ressalvas, que foram tratadas. A trava foi provada com Docker no laboratório uma vez. O que falta é prova humana e em ambiente real (terminal, entrevista, produto), que este ciclo não prometeu.

**O que depende do dono:**

1. Aceitar (ou não) os ADRs 0026 e 0032 a 0037.
2. Rodar `hdast profile approve clinica-piloto` antes do próximo teste de laboratório manual.
3. Provar o `profile approve` num terminal de verdade.
4. Decidir o que fazer com a lista de itens "a confirmar" deixados nos documentos.
