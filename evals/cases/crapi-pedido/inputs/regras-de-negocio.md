# Regras de negócio do crAPI

O crAPI é o sistema de uma oficina de veículos com loja e comunidade. O cliente tem uma conta,
cadastra seus veículos, pede serviço a um mecânico, compra peças e conversa com outros clientes.
Este texto descreve o negócio para quem vai encadear as chamadas da API. É um ambiente de teste,
com dados sintéticos, que pode ser refeito a qualquer hora.

## Três áreas, três prefixos

| Área | Prefixo | Cuida de |
| --- | --- | --- |
| Identidade | `/identity/api` | conta, login, perfil, vídeo do perfil e veículos |
| Oficina e loja | `/workshop/api` | mecânicos, pedidos de serviço, produtos e pedidos de compra |
| Comunidade | `/community/api` | fórum de posts e comentários, e cupons de desconto |

## Conta e login

O cliente se cadastra com nome, e-mail, telefone e senha. O e-mail é o login. O login devolve um
token, que acompanha as demais chamadas no cabeçalho `Authorization`. O painel do usuário
(`GET /identity/api/v2/user/dashboard`) devolve os dados da conta, inclusive o identificador do
vídeo do perfil.

## Veículos

Cada veículo tem um identificador interno (`vehicleId`, um UUID), o VIN (o número de chassi, de 17
caracteres) e um PIN. A lista de veículos da conta devolve o `vehicleId` e o VIN de cada veículo.
A localização de um veículo é consultada pelo `vehicleId`. Cada veículo pertence à conta que o
cadastrou.

## Oficina

- A lista de mecânicos devolve o `mechanic_code` de cada um. Um exemplo é `TRAC_JHN`.
- O contato com o mecânico abre um pedido de serviço para um veículo da conta. Os campos principais
  são o `mechanic_code`, o `vin` (o de um veículo da própria conta, vindo da lista de veículos), o
  `problem_details` (texto livre), o `repeat_request_if_failed` (verdadeiro ou falso) e o
  `number_of_repeats` (um número inteiro, como `1`).
- O campo `mechanic_api` é o endereço do serviço da oficina que recebe o relatório do serviço. No
  ambiente de teste, ele é `http://localhost:8000/workshop/api/mechanic/receive_report`, o próprio
  serviço da oficina, visto de dentro do contêiner dele.
- A resposta do contato traz o link do relatório, e o número ao fim do link é o `report_id`. O
  relatório é lido por `GET /workshop/api/mechanic/mechanic_report`.

## Loja

- A lista de produtos devolve o `id`, o nome e o preço de cada produto. É a chamada mais simples
  para saber se a loja está de pé.
- O pedido de compra informa o `product_id` e a `quantity`. Cada conta nova começa com um saldo de
  crédito de teste. A resposta devolve o `id` do pedido. A lista de pedidos da conta
  (`GET /workshop/api/shop/orders/all`) também traz esses `id`.
- Um pedido pode ser atualizado e devolvido (`return_order`, com o `order_id`). A devolução tem um
  código QR (`return_qr_code`).

## Cupons

O cupom é um código de desconto, como o `TRAC075`. O cliente valida o cupom com o `coupon_code` e o
aplica a um pedido na loja. Os cupons de teste já vêm cadastrados.

## Comunidade

O fórum tem posts e comentários. A lista de posts recentes devolve, dentro do campo `posts`, o `id`
de cada post. É com esse `id` (o `postId`) que se lê um post ou se comenta nele. Criar um post pede
título e conteúdo.

## Vídeo do perfil

O cliente envia um vídeo de perfil (`POST /identity/api/v2/user/videos`, como arquivo em
`multipart/form-data`). A resposta traz o `id` do vídeo, o mesmo `video_id` que o painel do usuário
mostra depois. O vídeo é lido e atualizado pelo `video_id`
(`/identity/api/v2/user/videos/{video_id}`), e o nome do vídeo pode ser trocado. A conversão de
formato usa `convert_video`. O vídeo pertence à conta que o enviou.

## Cuidados com as contas de teste

- O fluxo de recuperação de senha (pedir o código por e-mail, confirmar o código e definir a nova
  senha) e a troca de e-mail mudam o acesso da conta. Uma conta de teste que passe por esses
  fluxos pode ficar sem login até alguém recriá-la.
- O cadastro de contas e o cadastro de mecânicos criam usuários novos no ambiente.
- Os e-mails do ambiente de teste vão para uma caixa interna, não para fora.
- As rotas de administração são de uso interno da oficina e as contas de teste não têm esse papel.
