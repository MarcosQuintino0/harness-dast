# V1.9: investigação de autorização

Data: 2026-11-16. Análise estática e testes T1 offline; nenhuma prova com Docker ou alvo nesta
investigação. As conclusões do laboratório V1.5.5 são históricas, não repetidas aqui.

## Par criado

A versão anterior exigia 201 e comparava o identificador devolvido apenas com as leituras já
provadas no probe. Essa lista é amostra, não prova de ausência. A implementação agora extrai o
identificador do corpo novo, consulta dona e par antes do POST e exige 404 em ambas, compara o
identificador devolvido em qualquer 2xx e exige na leitura da dona um marcador novo e independente,
gerado por regra `unique`, antes da leitura da conta par. Não envia o POST se não
houver identificador prévio ou se a leitura prévia falhar. Um 404 pode ocultar objeto existente:
a prova é apenas de ausência visível, não global. APIs que geram o identificador no servidor,
sem identificador no corpo enviado, ficam não testadas. Esta restrição pode reduzir cobertura
frente à V1.8 e precisa ser medida; não se afirma que as provas anteriores permanecem válidas.
O OpenAPI do VAmPI também descreve criação de livro com resposta de mensagem e status, sem
identificador. A coleção de livros não declara garantia de completude: ausência de parâmetros
de paginação não prova que a listagem não seja parcial ou filtrada. Não se usa essa lista como
prova de que um identificador gerado pelo servidor não existia antes.

Testes sintéticos cobrem 201, 200 com ID novo, 200 sem ID e 200 com ID divergente já observado,
além de leitura prévia recusada, escopo e falha da dona. As respostas e IDs não vão ao diário.

## Cadastro e atribuição em massa no VAmPI

O contrato `lab/vampi/openapi3.yml` declara resposta do cadastro com mensagem e status, sem ID
ou efeito do campo de privilégio. A leitura por identificador declarada não contém esse campo;
a leitura da sessão apresenta o campo aninhado, mas lê a conta autenticada e o contrato não
estabelece que ela corresponde à conta recém-criada. Além disso, o POST de cadastro não é irmão
do GET por identificador na regra de família e usa dados únicos: repetir o corpo provado pode
gerar conflito. O relatório V1.5.5 registra oito candidatos sem achado e efeito sem leitura
compatível; não se pode afirmar por isso que o alvo rejeitou o campo.

A carta `evals/cases/vampi/authorization.md` autoriza GET, POST e PUT no escopo descrito e
escritas de autorização com dados sintéticos. A lacuna identificada é de vínculo e observação,
não falta comprovada de permissão na carta. Criar sessão para a conta nova exigiria credenciais
e associação de identidade não previstas no contrato genérico existente. Não foi acrescentada
regra específica de nome de produto, campo, caminho ou papel; V4 permanece sem prova.

## Diário e limitações

O emissor de authz reserva intenção antes de mutações, com chave derivada de produto, operação,
conta e método; não armazena ID, corpo ou credencial. Resposta HTTP inferior a 500 encerra a reserva
como resposta observada, sem atestar efeito. Recusa antes do envio encerra como falha; ausência de
resposta, 5xx ou exceção mantém a pendência e impede reenvio da mesma classe de
operação automaticamente, inclusive em nova execução. Isso também pode impedir restauração
automática quando o efeito é desconhecido; é necessário reconciliar o estado antes de prosseguir.
O diário usa o diretório de estado, fora dos arquivos exportáveis. Os limites de durabilidade e
o procedimento de recuperação constam no ADR 0077; não apague pendência como recuperação cega.
