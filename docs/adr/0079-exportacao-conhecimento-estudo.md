# ADR 0079: canal de conhecimento para estudo de reutilização

Status: **Proposto**. Data: 2026-11-16.

O estudo exige duas rodadas com contextos independentes. A segunda só pode receber
informação explicitamente entregue na carta, sem levar execução, aprovação ou gabarito.

O coordenador exporta `knowledge.yml`, a projeção `target.reuse.yml` e, se presentes
e válidos, `data-rules.yml`, `flows.yml` e `strategy.yml`, com manifesto de hashes.
As receitas são serializadas dos modelos validados, sem comentários. A projeção
do perfil contém só produto, tipo de autenticação, contas e referências declaradas
no caso e o caminho de login quando consta do OpenAPI; não é um `target.yml` válido.
Ela omite escopo, limites, autorização e demais campos do perfil. Contas fora da
carta e tipos de autenticação não previstos pelo caso são recusados.

O runner exige caso e segredos lacrados e coleta; recusa segredo conhecido, formas
reconhecíveis de credencial, termos do gabarito, links, arquivos extras e alterações.
Constantes de dados, inclusive listas, precisam constar do enum de cada campo do
OpenAPI a que a regra se aplica; argumentos textuais livres e início de sequência
são recusados. Limites numéricos de geradores `integer` e `number` também precisam
corresponder aos limites de todos os campos cobertos. Fluxos precisam corresponder às operações e aos esquemas declarados;
estratégia deve ter vínculo atual às fontes. Recalcula os vínculos da origem a partir
do perfil e dos documentos coletados, exceto motor. Revalida tudo ao preparar a
segunda rodada. A cópia recebe as propostas em `inputs/reuse/`, declaradas na carta;
conhecimento e escolhas de estratégia ficam `review_required`. Como a serialização
canônica muda os bytes das receitas, seus hashes são recalculados nessas propostas,
depois da validação das fontes originais; isso não valida o segundo contexto.
O `knowledge.yml` exportado mantém a `provenance` que o modelo exige: `run_id` e os hashes do manifesto, do probe e do authz da rodada de origem. Não são segredo, não autenticam autoria e identificam só a origem; nenhum outro arquivo do pacote carrega o identificador da execução (teste em `tests/unit/evals/test_reuse.py`).
A preparação não transfere aprovação nem valida o contexto atual. O motor, contrato,
ambiente, contas e autorização precisam ser verificados de forma independente antes
de qualquer consumo. Um manifesto não autentica a origem nem é prova de atualidade.

O subcomando `export-reuse` devolve texto e saída 0 em sucesso, 2 em erro de uso;
`prepare` aceita `--reuse-from` e `--reuse-package` juntos. Os comandos existentes
sem essas opções preservam o comportamento anterior. Nenhuma opção concede permissão.
O detector cobre segredos conhecidos, formatos reconhecíveis e termos do caso; não
garante detecção universal de todos os segredos. As entradas também passam pelos
modelos fechados e limites acima. O perfil ativo deve ser gerado da carta vigente.

Origem do conhecimento (V1.9.1): o agente nunca ativava o conhecimento, então
`knowledge.yml` não existia no fim da rodada e o `export-reuse` recusava. As skills agora mandam
capturar com `hdast knowledge capture <produto> --run <run_id>`, que gera
`knowledge.captured.yml` sem ativar. O `export-reuse` lê `knowledge.yml` e, só se ele não existe,
`knowledge.captured.yml`; havendo os dois vale o ativo, e um ativo grande demais ou inválido
recusa sem cair na captura. A revalidação pelo modelo fechado, a varredura de segredos e termos
do gabarito e o rebaixamento a `review_required` são os mesmos nos dois casos, e o arquivo
exportado continua com o nome `knowledge.yml` (a proposta que o segundo contexto recebe). A
recusa nomeia o arquivo que falta ou excede o limite. Nada disso ativa conhecimento nem concede
permissão.

Alternativa: copiar o diretório de perfil inteiro. Rejeitada porque levaria estado,
possíveis credenciais e pistas, sem controle confiável do canal.
