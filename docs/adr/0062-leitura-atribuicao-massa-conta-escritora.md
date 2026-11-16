# 0062. Leitura da atribuição em massa pela conta escritora

- **Status:** Proposto
- **Data:** 2026-11-15

## Contexto

O probe pode provar a escrita e a leitura por contas diferentes. Sem um leitor da conta escritora, a atribuição em massa dependia da resposta da escrita e podia deixar de observar uma alteração.

## Decis?o

Prefere-se a leitura provada pela conta escritora. Na falta dela, um GET provado por outra conta do mesmo modelo de caminho pode ser repetido pela conta escritora. Para atualização, o alvo concreto deve ser o mesmo; para criação, escolhe-se um GET irmão e usa-se o identificador devolvido pelo POST. A leitura anterior, posterior e a verificação da restauração usam a conta escritora. O envio passa pelo mesmo emissor, cerca e limites; a autorização de escrita não muda.

## Consequ?ncias

O GET pode falhar pela conta escritora, sem que isso prove segurança. No POST, mantém-se o fallback existente para a resposta da criação. Caminhos, identificadores e métodos não são adivinhados. A prova em laboratório nas duas APIs é um gate posterior.
