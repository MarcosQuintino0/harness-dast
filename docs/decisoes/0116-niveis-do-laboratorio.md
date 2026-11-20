# 0116. Núcleo de integração, provas de versão e seleção por área

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** T4 da revisão do tempo do laboratório

## Contexto

A rodada histórica de `lab_fast` acumulou 29 arquivos e levou cerca de 3h55.
Provas que precisam de várias pilhas, modos ou medições entraram no mesmo nível
usado para conferir mudanças locais. O tempo passou a limitar o ciclo em que
quem desenvolve confere a área que acabou de mudar.

## Decisão

Vamos manter `lab_fast` para o núcleo e marcar as provas de versão com
`lab_prova`. O arquivo `tests/integration/lab_areas.toml` associa caminhos
alterados aos arquivos dos dois níveis. Um teste de contrato compara o mapa
com a coleta do pytest.

`changed` reúne as áreas afetadas, incluindo suas provas. Caminhos
compartilhados ou sem área acionam o núcleo inteiro. Mudanças só de
documentação dispensam a rodada. No fechamento, `fast` e `prova` selecionam
cada nível completo. `regressao` seleciona a regressão dirigida e `tudo`
seleciona toda a integração e ponta a ponta.

O comando de rodada usa a trava exclusiva do laboratório e arquiva a saída
do pytest, o JUnit e as métricas na mesma pasta.

## Alternativas consideradas

- Manter os níveis anteriores e repetir seleções manuais por arquivo. Exigiria
  que cada pessoa conhecesse a cobertura atual e lembrasse as provas afetadas.
- Mover as provas para um nível próprio e rodá-las apenas no fechamento. A
  mudança de uma área poderia esperar até o fechamento para receber sua prova.

## Consequências

O ciclo local deixa de rodar as provas de áreas que não mudaram. Quem acrescentar
ou remarcar um teste precisa atualizar o mapa e a tabela na escada de testes.
O fechamento continua cobrindo o núcleo e as provas inteiros. O paralelismo no
GitHub fica para a T6. A meta de 5 a 15 minutos na seleção local precisa ser
medida em pilha.

## Aceite verificável

- A união de `lab_fast` e `lab_prova` preserva os casos do núcleo anterior.
- A coleta e o mapa concordam em cada nível, sem depender de Docker.
- A seleção soma áreas, cobre caminhos sem correspondência com o núcleo e
  informa quando a mudança é só documental.
- Uma trava existente permanece intacta e apenas a própria trava é removida
  quando a rodada encerra.
