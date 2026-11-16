# ADR 0079: canal de conhecimento para estudo de reutilização

Status: **Proposto**. Data: 2026-11-16.

O estudo exige duas rodadas com contextos independentes. A segunda só pode receber
informação explicitamente entregue na carta, sem levar execução, aprovação ou gabarito.

O coordenador exporta exclusivamente `knowledge.yml` do perfil coletado, junto a um
manifesto com versão, produto e SHA-256. O runner exige caso e segredos lacrados e
coleta, valida o modelo fechado e recusa segredo conhecido, termos do gabarito, links,
arquivos adicionais e alterações do pacote. Recalcula os vínculos da origem a partir
do perfil e dos documentos coletados, exceto motor, que não está disponível offline.
Ele compara novamente com a coleta ao
preparar a segunda rodada. A cópia recebe apenas o conhecimento, com todos os itens
marcados `review_required`, entregue como complemento da carta em `inputs/reuse/`.
A preparação não transfere aprovação nem valida o contexto atual. O motor, contrato,
ambiente, contas e autorização precisam ser verificados de forma independente antes
de qualquer consumo. Um manifesto não autentica a origem nem é prova de atualidade.

O subcomando `export-reuse` devolve texto e saída 0 em sucesso, 2 em erro de uso;
`prepare` aceita `--reuse-from` e `--reuse-package` juntos. Os comandos existentes
sem essas opções preservam o comportamento anterior. Nenhuma opção concede permissão.
O detector cobre segredos conhecidos e termos do caso; não garante detecção universal
de todos os segredos. As entradas permanecem sujeitas ao modelo fechado.

Alternativa: copiar o diretório de perfil inteiro. Rejeitada porque levaria estado,
possíveis credenciais e pistas, sem controle confiável do canal.
