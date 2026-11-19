# Glossário

Uma **operação** é uma ação que a API oferece. Cada uma tem um método, como `GET`, e um caminho.

## Alcance

Também chamado de *reachability*. É a proporção de operações alcançadas entre as que o `probe` tentou e para as quais enviou uma requisição. O resultado `1.0` significa que todas as operações tentadas foram alcançadas.

## Operação alcançada

Operação que respondeu com sucesso ao `probe` ou devolveu a recusa de login esperada. O relatório conta esses dois resultados separadamente.

## Operação varrida

Operação que o ZAP chegou a testar na etapa de varredura. Uma operação alcançada pode ficar de fora da varredura, por exemplo quando a janela de execução termina.

## Achado

Sinal de um possível problema que a ferramenta registra para revisão. Confira a evidência para decidir se o problema se confirma.

## Lacuna de cobertura

Operação ou verificação que ficou sem teste ou sem prova suficiente. O relatório indica o motivo, como falta de uma segunda conta de teste.

## BOLA

Falha de autorização no acesso a um objeto (*Broken Object Level Authorization*). Uma conta consegue acessar ou alterar um recurso que pertence a outra conta sem ter permissão.

## BFLA

Falha de autorização no acesso a uma função (*Broken Function Level Authorization*). Uma conta consegue usar uma ação reservada a outro papel, como uma função administrativa.

## Atribuição em massa

Quando a API copia automaticamente os campos recebidos para um registro. A falha ocorre se ela grava um campo que a conta não tem permissão para alterar.

## Cerca de escopo

Proteção que confere se uma requisição pode sair para a API. A CLI e o proxy aplicam as regras aprovadas, como endereço, caminho, método e janela. [Autorização e escopo](../como-funciona/operacao/authorization-and-scope.md).

## Carta

Autorização escrita do dono do produto que identifica o ambiente de teste, o que a equipe pode testar, por quanto tempo e sob quais limites. Inclui as referências das contas de teste. [Modelo de carta curta](../usar/carta-curta.md).
