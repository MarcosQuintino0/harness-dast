# Carta curta de autorização

O dono do produto preenche e assina esta carta antes do cadastro. Use somente ambiente de teste com dados sintéticos.

| Campo | Preenchimento pelo dono do produto |
| --- | --- |
| Produto e responsável | Nome do produto, nome e contato do dono. |
| Declarações | Confirme cada uma: o ambiente é de teste, os dados são sintéticos e a autorização está vigente. |
| Ambiente e contrato | Nome do ambiente, URL base com esquema, host e porta quando aplicável, e localização do Swagger/OpenAPI. |
| O que está autorizado | Para cada host, informe esquema, porta quando aplicável, caminhos e métodos permitidos. Declare se o uso de host local é autorizado. |
| O que está proibido | Liste os caminhos proibidos mesmo dentro dos autorizados. Use padrões com curinga para abranger o recurso e suas variações. Se não houver caminhos proibidos, declare expressamente “nenhum”. |
| Referência, validade e janelas | Referência da autorização, data final no formato AAAA-MM-DD e, para cada janela, dias, hora inicial, hora final e fuso. A CLI conta a data de validade em UTC. |
| Limites | Máximo de requisições por segundo, duração máxima em minutos e máximo de threads por host. Se houver limite de logins, informe quantos por minuto. |
| Autenticação | Para login com senha, indique a rota de login. Para chave de API, indique o nome do cabeçalho. |
| Contas de teste | Para cada conta, liste apelido, papel e referências de credencial. Login com senha precisa das referências do usuário e da senha. Chave de API precisa da referência da chave. Use `keyring:NOME` ou `env:NOME`. |
| Assinatura | Assinatura do dono do produto e data. |

Entregue os valores das credenciais pelo canal seguro da equipe. A carta leva só as referências.

Antes de aprovar o escopo no seu terminal, confira o resumo do perfil com a carta assinada. [Guia de cadastro](cadastrar-um-produto.md)
