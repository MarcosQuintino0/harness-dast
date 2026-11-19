# 0034. Índices do painel (produtos e histórico) e a página ao vivo

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** completa o [ADR 0032](0032-painel-da-execucao.md), que deixou para depois os índices de produtos e de histórico e a página "ao vivo" (telas `products.html`, `product-history.html` e `live.html` do desenho em `docs/design/execution-panel/`)

## Contexto

O painel de um teste existe, mas o caminho do alto (`hdast / Produto / data · hora`) era só texto, porque as páginas de destino não existiam. Quem faz QA também precisa ver todos os produtos, o histórico de cada um e, durante o `hdast run`, em que passo o teste está. O desenho manda HTML parado, sem JavaScript.

## Decisão

1. **Índices em `runs/`**, ao lado das pastas de execução: `runs/index.html` (um cartão por produto e os últimos dez testes) e `runs/history-<produto>.html` (histórico de um produto). O prefixo `history-` impede que um produto chamado `index` colida com o índice. Os nomes são conferidos pelo adaptador (só `index.html` e `history-<slug>.html`) e a gravação é atômica.
2. **Quando são refeitos:** sempre que um painel é gerado (`hdast panel PRODUTO`, `hdast report` e `hdast run`) e, de forma explícita, por `hdast panel --index` (sozinho: sem produto e sem `--run`). Falha ao refazer os índices dentro de `report` e `run` vai para o log (`panel_index_not_written`); em `hdast panel` é erro de configuração (saída 2). O modo `--index` não usa o perfil para nada além da validade da carta e do modo da cerca.
3. **Uma linha por execução, lida dos mesmos arquivos do painel** (`run.json`, `manifest.json`, `probe.json`, `scan.json`, `findings.json`, `authz.json`, `metrics.json`) e resumida pelo `PanelView`. Execução sem nenhum arquivo legível vira a linha "sem dados"; com algum arquivo ilegível (por exemplo, versão antiga do formato) vira linha com "dados incompletos". Nenhuma some nem derruba o índice. Tokens aparecem como traço (ainda não medidos).
4. **"Mudou desde o anterior"** compara as falhas graves pelo código curto (`finding_id`, que vem do fingerprint e não muda entre testes) com o teste anterior **do mesmo tipo** (varredura, teste entre contas, só alcance, só conferência). Usa só o que `findings.json` já tem; não depende de `--compare`. O que sumiu aparece como "não apareceu", não como "corrigida" (o desenho diz "corrigida"): a função pode não ter sido atacada desta vez, e o mesmo cuidado já existe em `report --compare`. Sem teste anterior do mesmo tipo: "primeira vez"; sem relatório de falhas em um dos dois: traço.
5. **Links do caminho do alto** passam a ser relativos e fixos (`../../index.html` e `../../history-<produto>.html`) em toda página do painel; a data leva a `summary.html`. A geração do painel e a dos índices acontecem no mesmo comando, então os destinos existem. No índice, a data de um teste só vira link se `panel/summary.html` existe; testes anteriores à V1.2 aparecem com a data em texto e o aviso "sem painel".
6. **A carta** (validade e modo da cerca) vem do perfil quando ele pode ser lido: "válida até", "vence em N dias" (sete dias ou menos) e "venceu em". Sem perfil, a linha diz que a carta não foi consultada; nunca inventa validade.
7. **"Falhas graves abertas"** (cartão e topo do histórico) vêm do teste mais recente que tem relatório de falhas: um teste mais novo sem relatório (por exemplo, erro na conferência) não apaga as falhas conhecidas.
8. **Gráfico de quantidade em branco e cinza**, como manda o README do desenho (a tela de exemplo usava vermelho): as barras do histórico usam a cor do texto.
9. **Página ao vivo sem JavaScript.** `hdast run` regrava `runs/<run_id>/panel/live.html` a cada mudança de etapa e, na varredura, a cada função (começo de cada uma e o fim da última), usando os pontos que `run` e `scan` já têm: nenhum laço de tempo, thread ou espera novos. A página se recarrega sozinha com `<meta http-equiv="refresh" content="15">`. A política de conteúdo do painel (CSP) **não muda**: `default-src 'none'` não restringe o recarregamento por `<meta>` (navegação não é recurso; conferido num Chrome sem cabeça com exatamente essa política, que seguiu um `<meta http-equiv="refresh">`), e a página continua sem script, sem recurso externo e sem formulário.
10. **Conteúdo e horário:** etapa em curso no trilho, o que já terminou, funções varridas e na fila, pedidos que passaram e barrados (quando há auditoria do proxy; senão "não medido"), a hora da última gravação ("atualizado às HH:MM:SS") e a frase de que, se o horário não muda há mais de um minuto, o teste parou. Aviso de como parar (`hdast stop`). Trava de emergência acionada: a página diz "Parando".
11. **A aba "Ao vivo" só existe enquanto o teste roda.** Durante o teste, as abas cujas páginas ainda não existem saem como texto apagado (nunca link quebrado). No fim, `live.html` é regravada uma última vez, sem a recarga automática, dizendo como o teste terminou e ligando para `summary.html` e `stages.html`; o menu volta a ser o das páginas do painel, com "Etapas". A página só existe depois do `preflight` (antes dele ainda não há pasta de execução).
12. **Falha ao regravar a página ao vivo nunca derruba nem atrasa o `run`:** o erro vai para o log (`panel_live_not_written`) e o teste segue. Também os avisos de progresso da varredura nunca levantam erro do harness.

### Portas

Novas, em `application/panel_index_ports.py` (arquivo à parte de `ports.py`, que é compartilhado): `PanelIndexFiles` (lista as pastas de execução, diz se o Resumo existe e grava os índices; fronteira com o sistema de arquivos e dublê de teste), `RunLive` (o que o `run` avisa a cada etapa e ao fim) e `ScanLive` (o que a varredura avisa a cada função). Implementações: `adapters/reporting/panel_index_files.py` e, no caso de uso, `LiveBoard` (`application/panel_live.py`). `RunnerDeps` ganha o campo opcional `on_progress`, e `Scan` e `RunPipeline` ganham o parâmetro opcional `live`; sem ele nada muda.

## Alternativas consideradas

- **`<produto>.html` em `runs/`.** Colide com `index.html` se um produto se chamar `index`. Descartada pelo prefixo.
- **Guardar o índice dentro de cada execução.** Os índices são do conjunto de execuções, não de uma.
- **Atualizar a página ao vivo por intervalo de tempo.** Exigiria laço ou thread novos. Descartada: o ritmo das gravações é o do próprio teste (etapa e função), e o `refresh` do navegador faz o resto.
- **JavaScript para o terminal rolar.** Quebra a regra de página sem script. Descartada (decisão do dono).
- **Comparar com `findings.json` de `--compare`.** Só existe se a pessoa pediu a comparação; o histórico precisa funcionar sempre.

## Consequências

- Toda execução que gera painel refaz os índices: com centenas de execuções isso lê os arquivos de todas, mas só gravando uma vez por página e sem rede.
- Se a gravação dos índices falhar durante `report` ou `run`, as páginas do teste podem apontar para um índice que não existe até a próxima geração; `hdast panel --index` o refaz.
- Um teste que morre sem terminar deixa `live.html` com a recarga ligada e a hora parada; a frase da página orienta quem lê. O próximo `hdast panel` não a regrava (ela só é tocada pelo `run`).
- **Fora desta entrega:** a página ao vivo não mostra "tipos de teste nesta função" nem "sinais de falha até agora" (os dados não existem durante a varredura), nem o terminal (a aba Terminal é de outra frente); o estado "sistema testado fora do ar" como etapa transitória não existe (a guarda de saúde já encerra o teste e o motivo aparece no fim).

## Nota de 2026-11-14 (ADR ainda Proposto): a página ao vivo e a conferência do `run`

O `preflight` do `run` abre uma pasta de execução só dele e o `probe` abre a da execução de verdade. A página ao vivo era gravada na primeira e o índice listava essa sobra como um teste com erro. Decisão: a página ao vivo só começa na etapa de varredura (a pasta do `probe` já existe) e o índice esconde a pasta que o `run.json` de outra execução cita como etapa dela (`PanelIndexer._absorbed`). Consequência: durante o alcance ainda não há página ao vivo. Uma pasta de conferência que nenhum `run.json` cita (o `hdast preflight` avulso) continua listada como "só conferência". O início de um teste, no painel e nos índices, é o do `run.json` ou, sem ele, o carimbo do id; as horas do `manifest.json` e do `probe.json` são de estágio e não entram.
