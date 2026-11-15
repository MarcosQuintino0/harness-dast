CARTA DE AUTORIZAÇÃO DE TESTE DE SEGURANÇA

1. Identificação
   Produto: Clínica Piloto (API de agendamento de consultas e receitas)
   Dono do produto: time Clínica Piloto (contato de emergência: plantão do time, canal #clinica-piloto)
   Referência desta autorização: LAB-CLINICA-PILOTO
   Válida até: 2027-12-31

2. Ambiente
   Nome: lab (laboratório local, sem dados reais de pessoas)
   URL base: http://clinica-piloto:8080
   O ambiente é descartável: é recriado do zero a cada subida da pilha de teste.

3. Escopo
   Host: clinica-piloto, porta 8080, http
   Caminhos autorizados: /api/** e /v3/api-docs
   Métodos autorizados: GET, POST, PUT e PATCH (DELETE NÃO é autorizado)
   Caminhos PROIBIDOS: /api/notificacoes/** (dispara envio de SMS e e-mail a terceiros) e /api/isca/**
   (reservado ao time do produto; nenhuma chamada é autorizada)
   Modo de leitura de caminhos pela cerca: AMPLO, autorizado para os caminhos desta carta.
   Autoriza-se a escrita do teste de autorização entre contas.
   Autoriza-se a escrita do teste de valores proibidos pelo contrato.
   Autoriza-se varrer operações cujo probe retornou not_found.
   OpenAPI: inputs/openapi.json

4. Janela de execução: seg-dom 00:00-24:00 America/Sao_Paulo

5. Limites de carga
   Requisições por segundo: no máximo 20
   Duração máxima de uma execução: 30 minutos
   Threads do varredor por host: no máximo 4
   O login do produto aceita 5 tentativas por minuto por origem e conta também as que falham.

6. Contas de teste (os valores já estão definidos no ambiente da pilha; use só os nomes)
   admin_a      papel admin      PILOT_ADMIN_USERNAME      PILOT_ADMIN_PASSWORD
   medico_a     papel medico     PILOT_MEDICO_USERNAME     PILOT_MEDICO_PASSWORD
   medico_b     papel medico     PILOT_MEDICO_B_USERNAME   PILOT_MEDICO_B_PASSWORD
   paciente_a   papel paciente   PILOT_PACIENTE_A_USERNAME PILOT_PACIENTE_A_PASSWORD
   paciente_b   papel paciente   PILOT_PACIENTE_B_USERNAME PILOT_PACIENTE_B_PASSWORD

7. Limpeza dos dados criados
   Não haverá limpeza automática por SQL: o ambiente é descartável. O perfil não deve ter bloco de limpeza.

8. Informações técnicas do time do produto
   - Login: POST /api/auth/login com JSON {"username", "password"}; a resposta traz o token no campo
     access_token, enviado como "Authorization: Bearer <token>".
   - Escritas (POST, PUT, PATCH) exigem proteção XSRF por cookie duplicado: cookie XSRF-TOKEN e
     cabeçalho X-XSRF-TOKEN; o token vem de GET /api/csrf. O login também aceita o par.
   - A listagem de documentos informa nomes existentes para a operação de download.
   - Verificação de saúde: GET /api/saude.
   - Cada papel só pode chamar parte das operações (admin: convênios e médicos; médico: pacientes,
     consultas e receitas; paciente: o próprio perfil).

9. Assinatura: dono do produto, 2026-11-13
