CARTA DE AUTORIZAÇÃO DE TESTE DE SEGURANÇA

1. Identificação
   Produto: VAmPI (API de usuários e livros, de laboratório)
   Dono do produto: time de QA de segurança (contato de emergência: plantão do time)
   Referência desta autorização: LAB-VAMPI
   Válida até: 2099-12-31

2. Ambiente
   Nome: lab (laboratório local, dados sintéticos)
   URL base: http://vampi:5000
   O banco de exemplo é recriado por GET /createdb, que é permitido.

3. Escopo
   Host: vampi, porta 5000, http
   Caminhos autorizados: /, /createdb, /me, /users/** e /books/**
   Métodos autorizados: GET, POST e PUT (DELETE NÃO é autorizado)
   Caminhos PROIBIDOS: nenhum além dos não listados acima
   Modo de leitura de caminhos pela cerca: ESTRITO (o modo amplo NÃO é autorizado)
   Autoriza-se a escrita do teste de autorização entre contas, com dados sintéticos,
   inclusive a criação de recursos para comparar duas contas do mesmo papel.
   Usuários não compartilham recursos privados entre si.
   OpenAPI: inputs/openapi3.yml

4. Janela de execução: seg-dom 00:00-24:00 America/Sao_Paulo

5. Limites de carga
   Requisições por segundo: no máximo 20
   Duração máxima de uma execução: 30 minutos
   Threads do varredor por host: no máximo 4

6. Contas de teste (os valores já estão definidos no ambiente; use só os nomes)
   user_a    papel user    VAMPI_USER_A_USERNAME   VAMPI_USER_A_PASSWORD
   user_b    papel user    VAMPI_USER_B_USERNAME   VAMPI_USER_B_PASSWORD
   admin_a   papel admin   VAMPI_ADMIN_USERNAME    VAMPI_ADMIN_PASSWORD

7. Limpeza dos dados criados
   Não haverá limpeza por SQL: o banco é recriado por GET /createdb. O perfil não deve ter bloco de limpeza.

8. Informações técnicas do time do produto
   - Login: POST /users/v1/login com JSON {"username", "password"}; a resposta traz o token no campo
     auth_token, enviado como "Authorization: Bearer <token>".
   - Algumas respostas voltam 200 com {"status": "fail"} em caso de erro de negócio.
   - A troca de e-mail e de senha só vale para o próprio usuário logado (conta do dono do dado).

9. Assinatura: dono do produto, 2026-11-13
