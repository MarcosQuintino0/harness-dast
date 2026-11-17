# Gabarito reservado: crapi-foco

O caso usa somente o crAPI, vulnerável em laboratório isolado. Nenhuma detecção
abaixo foi provada neste caso; todas permanecem `detectable: false`.

| ID | Operação | Limite da prova |
| --- | --- | --- |
| C1 | GET /identity/api/v2/vehicle/{vehicleId}/location | Controle BOLA; depende de IDs e duas contas, sem prova neste caso. |
| C10 | PUT /identity/api/v2/user/videos/{video_id} | Controle de atribuição em massa; não há prova e a escrita adicional de authz não foi autorizada. |
| C11 | POST /workshop/api/merchant/contact_mechanic | SSRF depende de infraestrutura e funcionalidade futura, sem prova de detecção. |
| C12 | POST /community/api/v2/coupon/validate-coupon | NoSQL ainda sem prova para este caso. |
| C15 | Login e leitura autenticada | JWT ainda sem prova para este caso. |
| C6 | POST /workshop/api/merchant/contact_mechanic | Falta de limite; DoS é proibido e teste limitado é apenas intenção futura. |

H11 é uma falha de cabeçalho prevista para a Clínica Piloto, não uma operação existente
na branch entregue nem no crAPI. L3/L5 estão congeladas após recusa; a prova de cabeçalho
está fora do escopo deste caso. Este caso de alvo único não cobre integralmente o requisito
de cabeçalho ou um caso multi-alvo.
Os 900 segundos são orçamento, não duração medida.
