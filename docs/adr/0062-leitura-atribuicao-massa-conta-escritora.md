# 0062. Leitura da atribui??o em massa pela conta escritora

- **Status:** Proposto
- **Data:** 2026-11-15

## Contexto

O probe pode provar a escrita e a leitura por contas diferentes. Sem um leitor da conta escritora, a atribui??o em massa dependia da resposta da escrita e podia deixar de observar uma altera??o.

## Decis?o

Prefere-se a leitura provada pela conta escritora. Na falta dela, um GET provado por outra conta do mesmo modelo de caminho pode ser repetido pela conta escritora. Para atualiza??o, o alvo concreto deve ser o mesmo; para cria??o, escolhe-se um GET irm?o e usa-se o identificador devolvido pelo POST. A leitura anterior, posterior e a verifica??o da restaura??o usam a conta escritora. O envio passa pelo mesmo emissor, cerca e limites; a autoriza??o de escrita n?o muda.

## Consequ?ncias

O GET pode falhar pela conta escritora, sem que isso prove seguran?a. No POST, mant?m-se o fallback existente para a resposta da cria??o. Caminhos, identificadores e m?todos n?o s?o adivinhados. A prova em laborat?rio nas duas APIs ? um gate posterior.
