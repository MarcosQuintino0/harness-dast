CARTA DE AUTORIZAÇÃO DE TESTE DE SEGURANÇA

1. Identificação
   Produto: OWASP crAPI (API de oficina e loja de veículos, de laboratório)
   Dono do produto: time de QA de segurança (contato de emergência: plantão do time)
   Referência desta autorização: LAB-CRAPI
   Válida até: 2027-12-31

2. Ambiente
   Nome: lab (laboratório local, dados sintéticos)
   URL base: http://crapi
   O ambiente é descartável. O coordenador sobe o crAPI (docker compose) e cadastra as contas de teste;
   você sobe só a pilha de teste (`hdast stack up`) e a conecta ao alvo conforme o item 8.

3. Escopo
   Host: crapi, porta 80, http
   Caminhos autorizados: /identity/api/**, /community/api/** e /workshop/api/**
   Métodos autorizados: GET, POST e PUT (DELETE e PATCH NÃO são autorizados)
   Caminhos PROIBIDOS (enviam e-mail, trocam senhas, criam contas ou fazem o servidor chamar URLs):
     /identity/api/auth/forget-password
     /identity/api/auth/v2/check-otp
     /identity/api/auth/v3/check-otp
     /identity/api/auth/signup
     /identity/api/v2/user/change-email
     /identity/api/v2/user/reset-password
     /identity/api/v2/user/verify-email-token
     /identity/api/v2/vehicle/resend_email
     /workshop/api/merchant/contact_mechanic
     /workshop/api/mechanic/signup
   OpenAPI: inputs/openapi.json

4. Janela de execução: seg-dom 00:00-24:00 America/Sao_Paulo

5. Limites de carga
   Requisições por segundo: no máximo 20
   Duração máxima de uma execução: 30 minutos
   Threads do varredor por host: no máximo 4

6. Contas de teste (os valores já estão definidos no ambiente; use só os nomes)
   user_a    papel user    CRAPI_USER_A_EMAIL   CRAPI_USER_A_PASSWORD
   user_b    papel user    CRAPI_USER_B_EMAIL   CRAPI_USER_B_PASSWORD

7. Limpeza dos dados criados
   Não haverá limpeza: o ambiente é descartável. O perfil não deve ter bloco de limpeza.

8. Informações técnicas do time do produto
   - Login: POST /identity/api/auth/login com JSON {"email", "password"}; a resposta traz o token no
     campo token, enviado como "Authorization: Bearer <token>". O nome de usuário é o e-mail.
   - Cada conta já tem um veículo cadastrado.
   - Verificação de saúde: GET /workshop/api/shop/products (exige login).
   - O crAPI NÃO faz parte da pilha do `hdast stack up` (que só conhece o VAmPI e a Clínica Piloto): a
     pilha sobe sem alvo e o coordenador liga o crAPI à rede dela. Rode `uv run hdast --json stack up
     crapi` e, em seguida, escreva no diário "pilha de pé, aguardando o coordenador ligar o alvo".
     Faça o `probe` e o `run` só depois de o coordenador avisar que o alvo está ligado.

9. Assinatura: dono do produto, 2026-11-13
