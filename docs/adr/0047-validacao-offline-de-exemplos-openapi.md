# ADR 0047 — Validação offline de exemplos OpenAPI

Estado: Proposto

## Contexto

Exemplos já declarados podem contrariar os esquemas e induzir o leitor do contrato a erro. Seus valores são dados não confiáveis e podem conter informação sensível.

## Decisão

`spec inspect` verifica exemplos JSON locais preservados em esquemas, parâmetros e tipos de mídia de requisição e resposta de sucesso. Informa códigos de tipo, obrigatoriedade, faixa, enum e comprimento em `issues`, sem exibir valores. O resultado e a travessia têm limites; o marcador `EXAMPLE_TRUNCATED` informa corte da inspeção. A verificação é offline e não cria dados nem envia requisições. Exemplos externos não são obtidos.

Valida-se cada nó representado, incluindo propriedades, itens e `allOf`. A verificação não avalia `oneOf`, `anyOf`, formatos, padrões, propriedades adicionais nem esquemas truncados. Respostas seguem o subconjunto já representado pelo carregador: respostas 2xx e mídia preferida. Exemplos não JSON, excessivamente profundos ou grandes são descartados pelo carregador e não são validados. Componentes não referenciados não integram o modelo inspecionado. Isso não constitui validação completa do OpenAPI.

## Consequências

O formato existente de `issues` continua utilizável, com códigos novos. Os valores de exemplo não são serializados no novo campo do modelo. Os limites evitam relatórios ilimitados, mas uma inspeção sem problema relatado não garante que todo exemplo do documento tenha sido verificado.
