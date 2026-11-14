# 0032. Painel da execução: páginas HTML estáticas por teste

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** desenho final do painel, aprovado pelo dono do projeto em 2026-11-14 (`docs/design/execution-panel/`). Estende o [ADR 0029](0029-relatorio-agrupado-pagina-html-e-skill-de-um-pedido-so.md) (`report.html`) e usa os arquivos do [ADR 0024](0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md) (`run.json`) e do [ADR 0031](0031-medicao-da-execucao-metrics-json-e-tempo-por-regra-do-zap.md) (`metrics.json`)

## Contexto

O `report.html` é uma página única, boa para quem corrige. Quem faz QA e o dono do produto não dominam segurança, rede nem arquitetura e perguntam outras coisas: deu certo? o que faço agora? o que foi testado e o que ficou de fora? o que o agente fez? O desenho do painel responde isso em seis abas. Falta decidir como a CLI o gera, sem criar uma segunda fonte de verdade nem abrir mão da segurança do `report.html` (sem JavaScript, sem recurso externo, todo texto do alvo escapado).

## Decisão

1. **Várias páginas por teste**, em `runs/<run_id>/panel/`, com os nomes do desenho: `summary.html`, `stages.html`, `findings.html`, `coverage.html`, `terminal.html` e `time-and-tokens.html`. Cada página leva o CSS embutido (sem arquivo externo): os tokens do `tokens.css` do desenho (cópia em `domain/panel_tokens.py`, com teste que falha se divergir do arquivo) e as regras dos componentes. Um registro simples (`domain/panel_pages.py`: arquivo, rótulo, função de desenho) diz quais páginas existem; acrescentar uma aba é um módulo novo e uma linha.
2. **Comando novo `hdast panel PRODUTO [--run ID] [--json]`**: gera ou atualiza o painel a partir dos arquivos da execução (`run.json`, `manifest.json`, `probe.json`, `scan.json`, `findings.json`, `authz.json`, `metrics.json`, que são todos opcionais) e do perfil e do OpenAPI do produto. Sem `--run`, usa a execução mais recente do produto. Não usa rede nem o ZAP. Envelope e códigos de saída são os dos outros comandos: `0` com as páginas gravadas, `2` (`CONFIG_ERROR`) para execução inexistente, de outro produto, sem nenhum arquivo conhecido ou com `run_id` inválido. `hdast report` e `hdast run` também o geram no fim (o `run` depois de gravar `run.json`). **Falha ao gerar o painel nunca derruba `report` nem `run`**: vai para o log (`panel_not_written`) e o comando segue.
3. **Segurança igual à do `report.html`**: sem JavaScript, sem recurso externo, CSP por `<meta>` (`default-src 'none'`), `lang="pt-BR"`, todo texto do alvo, do OpenAPI, do ZAP, do agente ou de arquivo passa por `html_safe` (sem controle, ANSI e bidi, redigido, escapado). O painel nunca mostra token, senha ou cookie.
4. **Tema:** escuro é o principal; o claro segue o aparelho (`prefers-color-scheme`), como em `summary-light.html`.
5. **Nome simples de cada função:** o `summary` da operação no OpenAPI quando existir, senão o `operation_id`; a parte do sistema é a primeira `tag`, senão "Outras". Não há campo novo no perfil: `Operation` ganha só `summary` (opcional, até 200 caracteres, sem controle).
6. **Linguagem:** nunca "seguro" nem "aprovado"; estado nunca só por cor (forma e palavra); lista fechada de palavras de estado e formato de números do desenho (`domain/panel_format.py`: 151 mil, 28 min, 16.854); dado ausente é traço e "não medido", nunca zero.
7. **Modelo de visão** (`domain/panel_model.py`): um `PanelView` congelado por teste, montado por função pura (`build_panel_view`) a partir dos modelos que os arquivos já têm. Carrega tudo que as seis abas precisam, inclusive as que ainda são provisórias. Dois **ganchos** entram por parâmetro, já prontos, e podem vir vazios: `commands` (diário de comandos) e `explanations` (catálogo de explicação de falha, por `finding_id`). Tokens ficam `None` até existir a medição do agente.
8. **Regra de confiança desta versão** (o medidor de três degraus), UMA só, em `domain/finding_confidence.confidence_step` (a montagem do painel a chama): "prova forte" quando a evidência foi gravada, o ZAP apontou um trecho dela como prova e nem o ZAP (`false_positive`) nem o agente (`suspected_false_positive`) a marcaram como falso positivo; "a confirmar" nos demais (por exemplo, falha por demora, sem trecho na resposta). A confiança que o ZAP propõe (`low`, `medium`, `high`) não entra: um erro 500 depois de uma aspa costuma vir "low" e a resposta gravada prova a falha. Medido na Clínica Piloto (execução f087): dos 3 achados graves, 2 são prova forte e 1 a confirmar. O terceiro degrau ("confirmada") só existe quando uma pessoa confirma, e nenhum arquivo registra isso ainda: a aba Falhas explica isso em uma frase. Falha de autorização entre contas conta como prova forte (a comparação entre respostas é determinística). Nada disso muda a severidade proposta.

### Porta

Uma porta nova, `PanelFiles` (em `application/ports.py`): lê os arquivos da execução que o painel usa (todos devolvem `None` quando não existem), acha a execução mais recente de um produto e **grava as páginas** em `runs/<run_id>/panel/`. Ela existe por ser a fronteira com o sistema de arquivos e para os testes usarem um falso em memória. O adaptador (`adapters/reporting/panel_files.py`) escreve de forma atômica, só dentro da pasta `panel/`, e confere o nome de cada página. `PanelRefresher` (em `scan_ports.py`) é o ponto de chamada de `report` e `run`, no mesmo molde de `RunMetricsRecorder`.

## Alternativas consideradas

- **Um arquivo só (como o `report.html`).** Seis assuntos numa página única ficam longos, e o link de uma falha não poderia ir num chamado. Descartada.
- **JavaScript para abas e para o terminal rolar.** Quebra a regra de página sem script. Descartada; o "ao vivo" com recarga automática fica para outro ADR.
- **Campo novo no perfil para o nome simples da função.** Obriga todo produto a manter mais um dado. O `summary` do OpenAPI já existe e é o lugar natural. Descartada.
- **Reescrever `report.html` como uma aba.** Mexeria num contrato que já está em uso. O painel é novo e o `report.html` continua como está.
- **Gerar o painel só pelo comando novo.** A pessoa teria de lembrar de rodar mais um comando; `report` e `run` o geram sozinhos, e o comando serve para refazer (por exemplo, depois de uma triagem).

## Consequências

- Em toda execução que chega ao `report` ou ao `run` há um painel; quem não o quer ignora a pasta `panel/`. Execução antiga, sem `metrics.json`, sai com "não medido" onde faltar dado.
- O painel mostra o modo da cerca que a execução gravou (`metrics.json`, depois o tráfego do `scan.json`), e só na falta deles o do perfil, que pode ter mudado.
- **Fora desta entrega** (os ganchos e o registro já existem): abas Falhas, Cobertura, Terminal e Tempo e tokens (hoje páginas provisórias com a casca completa), página "ao vivo", índices de produtos e de histórico (o caminho do alto mostra `hdast` e o produto como texto, não como link, até esses índices existirem), diário de comandos, catálogo de explicação, tokens do agente, máscara de CPF, e-mail e telefone na prova (pergunta ainda sem resposta do dono).
- Uma etapa cortada e as seguintes aparecem em amarelo e cinza com a palavra "não rodou", que não está na lista fechada do desenho (o desenho pede só as etapas em cinza; "a seguir" seria falso num teste que já acabou). Se o dono preferir outra palavra, é uma troca em `panel_format.py`.

## Atualização: abas Cobertura e Tempo e tokens

- **Tokens do agente.** A CLI não mede tokens. Quando existe `runs/<run_id>/agent-metrics.json` (`schema_version` 1, gravado pela avaliação cega em `evals/`), o painel o lê por um modelo tolerante e mínimo em `domain/agent_metrics.py` (o domínio não importa de `evals/`). A porta `PanelFiles` ganha `read_agent_metrics`: arquivo ausente, grande demais, malformado ou de outra versão devolve `None`, e o painel mostra "não medido". O total de tokens soma entrada, saída e cache gravado; o cache relido (o mesmo contexto lido a cada passo) é mostrado à parte e não entra na soma.
- **Etapas do agente x etapas da CLI.** `leitura` e `cadastro` contam na conferência; `alcance`, `varredura` e `triagem` (os achados) têm a etapa própria; o que sobra (`outro`) vai para "outras tarefas do agente". O teste entre contas não tem trabalho de agente separado.
- **Palavras de estado da função.** A aba Cobertura usa as quatro palavras da lista fechada (`atacada`, `com falha grave`, `não testada`, `proibida pela carta`); a diferença entre "tentou e não conseguiu" e "não tentada" fica no motivo, escrito ao lado da função.
