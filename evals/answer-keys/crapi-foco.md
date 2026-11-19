# Gabarito reservado: crapi-foco

Versão 2 do caso (V1.12, 2026-11-17). A versão 1 marcava todos os desafios como
`detectable: false`; a versão 2 muda o valor só onde há prova no laboratório (o C3 voltou a `false` na correção da validação independente) (execuções
de integração com `run_id` no [relatório da V1.12](../../docs/arquivo/reviews/relatorio-v1.12.md)).
A carta passa a ligar, na seção `attack`, o ritmo `proxy` e as cinco capacidades da V1.12,
cada uma com frase de autorização (ADR 0096). A verificação de OTP da v2 entra no escopo
(só POST); a v3 e a recuperação de senha continuam negadas.

O caso usa somente o crAPI, vulnerável em laboratório isolado. As provas foram feitas por
comandos dirigidos, não por agente cego: a rodada cega da V1.12 ainda está pendente.

| ID | Operação | `detectable` | Base e limite da prova |
| --- | --- | --- | --- |
| C1 | GET /identity/api/v2/vehicle/{vehicleId}/location | não | Controle BOLA; depende de IDs e duas contas, sem prova neste caso. |
| C3 | POST /identity/api/auth/v2/check-otp | não | Limite de consumo (ADR 0101): a primeira prova (`crapi-338a`) achou por 20 respostas HTTP 500 iguais, o que não é rejeição de credencial. Depois da correção, a tentativa com dígitos do tamanho do contrato ainda recebe 500 do crAPI e a checagem fica inconclusiva, sem achado (`crapi-4c29`). Não é detectável com a regra atual. A v3 não está no escopo. |
| C6 | POST /workshop/api/merchant/contact_mechanic | não | O teste de limite de consumo só cobre autenticação e verificação; nenhuma prova neste endpoint. DoS continua proibido. |
| C10 | PUT /identity/api/v2/user/videos/{video_id} | não | Controle de atribuição em massa; ID de vídeo e detecção não foram provados; escrita adicional de authz não autorizada. |
| C11 | POST /workshop/api/merchant/contact_mechanic | sim | SSRF guiado pelo contrato com `attack.oast` (ADR 0100): campo `mechanic_api`, 1 pedido e 1 retorno (`crapi-7b43`, `crapi-11fa`). Sem a chave, zero interações (`crapi-0efe`). |
| C12 | POST /community/api/v2/coupon/validate-coupon | não | Esperado não achar: as regras NoSQL experimentais rodaram em força baixa e não acharam (`crapi-d197`). |
| C15 | Login e leitura autenticada | sim | `authz` achou `alg_none` e claims alteradas (`crapi-a379`, ADR 0098). Chave fraca só em unidade; `kid`, `jku` e confusão de algoritmo não avaliados. |

Controles: C1 e C10 medem regressão. A injeção de SQL em cabeçalho (H11) é uma falha da
Clínica Piloto, não uma operação do crAPI; a prova de cabeçalho não pertence a este caso.
Alarmes falsos de regras experimentais e de limite de consumo devem ser lidos como
achados marcados `[experimental]` ou de severidade média, sem ser contados como acerto
além dos desafios acima.
Os 900 segundos são orçamento, não duração medida.

**Régua (V1.12.1).** Até a versão 3 do caso, C11 e C15 estavam `detectable: true` sem critério `match`, e a régua nunca as dava como achadas. Agora C15 casa com a técnica `authz_tampered_token`, C11 com o título do SSRF guiado em `contact_mechanic`, e os controles C1 e C12 têm critério só para o relatório dizer se foram reportados. A detectabilidade não mudou.
