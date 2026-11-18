CARTA DE AUTORIZAÇÃO DE TESTE — LAB-CRAPI-FOCO

O time de QA autoriza o laboratório local descartável crAPI, com dados sintéticos,
até 2027-12-31, diariamente das 00:00 às 24:00 em America/Sao_Paulo.
Base: http://crapi, porta 80. A carta estruturada entregue em `inputs/carta.yml`
é a fonte dos caminhos e métodos, limites e contas. Use-a com `hdast init --from-letter`;
o contrato está em `inputs/openapi.json`. O modo de caminhos é estrito.

Autorizam-se somente POST no login, na verificação de OTP da v2, no contato do mecânico e na validação de cupom;
GET na lista e localização de veículos, detalhe de vídeos e produtos; PUT no detalhe
de vídeos. A lista de veículos fornece identificadores e produtos é a verificação de saúde.
No contato com o mecânico, `mechanic_api` deve receber
`http://localhost:8000/workshop/api/mechanic/receive_report`: `localhost` é o próprio
serviço `crapi-workshop`, dentro do contêiner e da rede interna do laboratório, sem
saída à internet. O código do mecânico é `TRAC_JHN` e `number_of_repeats` é o inteiro `1`.
Esse endereço é um dado do pedido de contato; não autoriza o agente a chamar outro caminho.
Não são autorizados testes de negação de serviço. A verificação de OTP da v2
só admite o teste de limite de consumo da carta, com teto de pedidos e parada no primeiro
bloqueio. A v3 do OTP e a recuperação de senha estão explicitamente negadas. DELETE e
PATCH não são autorizados. Os caminhos negados são /identity/api/auth/v3/check-otp
e /identity/api/auth/forget-password.

Limites: 20 requisições por segundo, 15 minutos por execução e 4 threads por host;
força LOW. Não são autorizados testes adicionais de escrita entre contas, valores
proibidos, uploads ou operações sem sucesso. O ambiente é descartável, sem limpeza.
As contas user_a e user_b, papel user, são providas pelo coordenador por referências
CRAPI_USER_A_EMAIL, CRAPI_USER_A_PASSWORD, CRAPI_USER_B_EMAIL e CRAPI_USER_B_PASSWORD.
O login recebe JSON com email e password e devolve token. Cada conta tem um veículo.

Versão 2 do caso (V1.12): a carta estruturada liga, na seção `attack`, o ritmo `proxy`
e as capacidades de injeção em cabeçalhos e cookies, retorno fora de banda, limite de
consumo, regras experimentais e inventário, cada uma com a frase de autorização. O limite
de consumo tem teto de 66 pedidos e parada no primeiro bloqueio. A meta total da rodada
é 900 segundos, ainda não medida. O coordenador prepara e conecta a infraestrutura.

Versão 3 do caso (V1.12.1): explicita os dados locais do contato do mecânico, já usados
no OpenAPI e na prova de integração OAST. Caminhos, métodos, limites e capacidades
permanecem os mesmos da versão 2.

Esclarecimento do contato (V1.12.2): o campo `vin` do contato deve ser o de um veículo da
própria conta, o mesmo `0.vin` que a lista de veículos devolve. Um `vin` inventado não existe
no alvo e o contato responde 500, com ou sem a ponte de retorno. Ligue-o em `flows.yml`
(`get_vehicles` campo `0.vin`, consumido por `contact_mechanic` campo `vin`). Caminhos,
métodos e limites seguem os mesmos.
