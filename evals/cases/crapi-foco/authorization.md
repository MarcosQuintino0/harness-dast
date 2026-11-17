CARTA DE AUTORIZAÇÃO DE TESTE — LAB-CRAPI-FOCO

O time de QA autoriza o laboratório local descartável crAPI, com dados sintéticos,
até 2027-12-31, diariamente das 00:00 às 24:00 em America/Sao_Paulo.
Base: http://crapi, porta 80. A carta estruturada entregue em `inputs/carta.yml`
é a fonte dos caminhos e métodos, limites e contas. Use-a com `hdast init --from-letter`;
o contrato está em `inputs/openapi.json`. O modo de caminhos é estrito.

Autorizam-se somente POST no login, contato do mecânico e validação de cupom;
GET na lista e localização de veículos, lista e detalhe de vídeos e produtos; PUT no detalhe
de vídeos. As listas fornecem identificadores e produtos é a verificação de saúde.
O contato com mecânico só pode usar infraestrutura isolada do laboratório, sem saída
à internet. Não são autorizados força bruta de OTP nem testes de negação de serviço.
OTP e recuperação de senha estão explicitamente negados. DELETE e PATCH não são autorizados.

Limites: 20 requisições por segundo, 15 minutos por execução e 4 threads por host;
força LOW. Não são autorizados testes adicionais de escrita entre contas, valores
proibidos, uploads ou operações sem sucesso. O ambiente é descartável, sem limpeza.
As contas user_a e user_b, papel user, são providas pelo coordenador por referências
CRAPI_USER_A_EMAIL, CRAPI_USER_A_PASSWORD, CRAPI_USER_B_EMAIL e CRAPI_USER_B_PASSWORD.
O login recebe JSON com email e password e devolve token. Cada conta tem um veículo.

Para um futuro teste de limite de taxa, a intenção é teto de 20 pedidos e parada no
primeiro 429; isso não está representado no contrato vigente nem autoriza execução
antes de existir suporte e autorização formal correspondente. A meta total da rodada
é 900 segundos, ainda não medida. O coordenador prepara e conecta a infraestrutura.
