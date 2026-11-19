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

## Nuclei

O segundo motor do hdast ([ADR 0122](../decisoes/0122-nuclei-como-segundo-motor.md)). O ZAP ataca o que o contrato descreve; o Nuclei procura falhas conhecidas de produtos de prateleira, configuração errada e exposição fora do contrato, como o Actuator aberto. Ele usa modelos de assinatura da comunidade, fixados por versão. Só roda se o perfil tem `extra_checks.nuclei`, que vem da carta ou do pedido mínimo, e atrás da segunda cerca. Comando: [`hdast nuclei`](cli.md#hdast-nuclei).

## Modelo (do Nuclei)

Uma assinatura do catálogo `nuclei-templates` que descreve uma verificação conhecida, como um CVE ou um painel exposto. A CLI escolhe os modelos pelo manifesto fixado na instalação, nunca pelo que o alvo diz.

## Segunda cerca

A segunda instância do proxy de escopo, `scope-proxy-nuclei`. Só o Nuclei passa por ela, com política própria derivada do perfil aprovado. O ZAP nunca usa essa política. [Arquitetura](../como-funciona/arquitetura.md#a-segunda-cerca-do-nuclei).

## Caminhos amplos

Liberação de `extra_checks.nuclei_wide_paths`: a segunda cerca aceita qualquer caminho das origens aprovadas, mesmo fora do Swagger. Origem, `deny_paths` e ritmo continuam valendo. Só o Nuclei tem esse modo; o ZAP e as outras etapas seguem estritos.

## Tecnologia identificada

Informação que o Nuclei dá só para identificar (produto, versão). Vai para a seção "Tecnologias identificadas" do relatório e não conta como achado.
