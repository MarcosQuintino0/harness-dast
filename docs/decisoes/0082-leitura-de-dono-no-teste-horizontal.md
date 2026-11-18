# 0082. Leitura de dono no teste horizontal

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

O roteamento que maximiza o alcance do probe pode usar um papel compartilhado e
impedir a comparação entre donos. A ausência de GET de item no probe também deixava
a operação invisível. Orientação nas skills não corrige essa dependência.

## Decisão

O domínio planeja leituras de dono para GETs com identificador de caminho sem leitura
provada por conta de papel não compartilhado com par. Escolhe as duas primeiras
contas do primeiro papel elegível, na ordem do perfil. `public_operations` representa
as operações públicas (não existe configuração de papel público); elas são excluídas,
assim como papéis em `shared_roles`. Não se infere hierarquia nem propriedade pelo nome.
Um marcador final único e escalar é suportado; caminhos aninhados e outros parâmetros
obrigatórios ficam explicitamente sem teste. O perfil não muda.

Fontes, nesta ordem: coleção GET irmã declarada como array de objetos, sem parâmetros
obrigatórios adicionais; IDs em alvos de GET bem-sucedidos da própria conta; campo
exato do parâmetro no JSON sanitizado de POST bem-sucedido da própria conta para a
coleção irmã. Respostas do probe não são persistidas e não serão acrescentadas ao
registro. A terceira fonte já existe em `ExchangeRecord.body`; não muda sua redação,
não recupera campos omitidos e não aceita campos classificados como segredo. Nenhum
valor novo é gravado: o identificador extraído do corpo enviado já consta, redigido,
em `exchanges.json`, e a leitura só o usa em memória para montar o GET; o `authz.json`
não guarda corpos nem identificadores, só a operação e o motivo, e o diário de
pedidos registra o alvo como em qualquer pedido do `authz`.
Coleções são consultadas nas duas contas: interseção de IDs, valor vazio, tipo errado,
chaves duplicadas, colisão de nomes normalizados ou identidades contraditórias recusam
a prova. Coleção existente porém vazia/inacessível não é contornada com outra fonte.
Inventários mostram visibilidade, não provam propriedade global.

Cada operação/par examina no máximo **dois objetos**, em ordem determinística, sem
criar recurso. A conta A precisa obter 2xx e o mesmo identificador no corpo do item;
depois B repete o GET. A comparação existente de corpos, ignorando campos voláteis,
é preservada: 2xx com identidade e corpo equivalentes gera `authz_horizontal`, alta,
com os fingerprints existentes. Somente 401/403/404 comprovam proteção. Corpo
diferente, identidade divergente, outros códigos ou falta de resposta são inconclusivos.
Resultados e contagens usam `CheckSummary` e `not_tested` existentes, sem nova versão
de schema, envelope, campo de perfil ou código de saída. A simulação não envia pedidos.

Novos motivos: `owner_read_unsupported`, `owner_collection_missing`,
`owner_collection_empty` e `owner_collection_unavailable`.
Reutiliza `ambiguous_identifier`, `no_peer_account`, `public_operation`,
`baseline_failed`, `scope_denied`, `account_unavailable`, `inconclusive` e
`budget_exhausted`. Cada lacuna identifica operação e ação sugerida; relatórios e painel
a exibem, inclusive quando excede o limite geral de linhas da apresentação.

O painel ganha `authorization.html` e a sétima aba, Autorização; `data.files` do
`hdast panel` inclui essa página (adição compatível, schema 1 preservado). O modelo
interno `PanelView.authz` leva o resultado sanitizado para a mesma apresentação HTML
usada pelo relatório, mesmo sem scan. Metadados do prepare e medições ganham `pacing`
aditivo; sem metadado em rodada histórica ele é desconhecido (`null`), nunca inferido.

Aplicação só envia pelo `ReplaySender`/`OperationDispatcher`/`GuardedSender` existentes:
escopo, deny_paths, métodos, aprovação, pilha atual, limites, janela, prazo, stop,
auditoria e diário continuam vigentes. Usar outra conta já declarada para GET já
autorizado não amplia permissões; o roteamento não é uma restrição de autorização.
Nenhuma escrita nova; escritas existentes continuam atrás de `authz.allow_writes`.

## Alternativas e limites

Não adivinhar IDs, usar IDs de outra conta como propriedade, guardar resposta ou
criar recursos para obter IDs. Sem evidência suficiente, registrar lacuna. A leitura
de dono não substitui testes de escrita, não cobre identificadores no corpo de GET,
coleções paginadas em envelopes nem prova propriedade só pelo sucesso HTTP. A prova
fica restrita ao laboratório, sem varredura completa nem rodada cega nesta entrega.
