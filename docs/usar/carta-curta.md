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
| Limites | Máximo de requisições por segundo, duração máxima em minutos e máximo de threads por host. Se houver limite de logins, informe quantos por minuto. Se o dono não souber, a CLI usa o mínimo (1 requisição por segundo, 30 minutos, 1 thread e 1 login por minuto) e avisa no cadastro. |
| Autenticação | Para login com senha, indique a rota de login. Para chave de API, indique o nome do cabeçalho. |
| Contas de teste | Para cada conta, liste apelido, papel e referências de credencial. Login com senha precisa das referências do usuário e da senha. Chave de API precisa da referência da chave. Use `keyring:NOME` ou `env:NOME`. |
| Nuclei (opcional) | O Nuclei é o segundo motor, que procura falhas conhecidas de produtos de prateleira, configuração errada e exposição fora do Swagger. Escreva uma frase por item que você autoriza; sem a frase, o item fica desligado. **Usar o Nuclei** (`attack.nuclei`). **Login com a conta de teste** (`attack.nuclei_login`): o Nuclei entra com uma conta de teste e só lê. **Caminhos amplos** (`attack.nuclei_wide_paths`): o Nuclei pode consultar qualquer endereço das origens autorizadas, inclusive fora do Swagger; os caminhos proibidos continuam proibidos. A escrita do Nuclei não tem frase própria: ela vale só se você também autorizou as três escritas de dados (entre contas, valores inválidos e envio de arquivo), e o `DELETE` só se você o listou nos métodos permitidos. |
| Assinatura | Assinatura do dono do produto e data. |

Entregue os valores das credenciais pelo canal seguro da equipe. A carta leva só as referências.

Antes de aprovar o escopo no seu terminal (`hdast setup <produto>`), confira o resumo do perfil com a carta assinada. [Guia de cadastro](cadastrar-um-produto.md)
