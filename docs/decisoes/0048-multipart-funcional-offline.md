# ADR 0048 — Multipart sintético offline

Estado: Proposto

## Contexto

Uma operação pode declarar multipart entre várias mídias, mesmo quando JSON é a preferida. O resumo deve sinalizar esse contrato sem confundir a capacidade de construir um exemplo com autorização ou suporte ao envio pelo probe.

## Decisão

Para cada operação de `spec inspect`, o campo `multipart_offline` aparece quando a inspeção detecta `multipart/form-data`: o booleano representa o resultado de montar e interpretar em memória um corpo sintético mínimo. A inspeção normaliza caixa, espaços e parâmetros em até 100 chaves de mídia de requisição, com até 100 caracteres cada, na ordem do documento; não carrega esquemas ou exemplos extras. Se houver mais chaves, alguma delas ultrapassar 100 caracteres ou não for texto, o resumo dessa operação inclui `multipart_inspection_incomplete: true`. Sem esse aviso, a ausência de `multipart_offline` indica que multipart não foi detectado; com ele, a ausência é inconclusiva. Se multipart for detectado e a inspeção for incompleta, ambos os campos aparecem. O aviso é omitido quando não há truncamento. O orçamento do resumo continua valendo; operações omitidas não aparecem.

A prova usa um campo e um arquivo sintético fixos, pequenos, sem dados do OpenAPI, destino, acesso a arquivo ou rede. Nomes são ASCII seguros, distintos e limitados a 64 caracteres; a boundary determinística tem 248 bits de hash e até 70 caracteres e é verificada contra os conteúdos. Uma prova por resumo basta, pois o conteúdo é independente da operação. O parser MIME da biblioteca padrão verifica as partes, nomes e conteúdos em memória. O resumo não expõe corpo, boundary ou cabeçalhos. `false` indica falha nessa prova e não esconde a declaração multipart.

A lista de mídias e a escolha preferida continuam limitadas às primeiras 20 entradas representadas, sem alteração no despacho. O probe continua recusando corpos multipart e binários, conforme ADR 0018. A prova não valida o esquema de upload, não comprova compatibilidade com servidor e não habilita requisições, varredura ou acesso a um alvo.

## Consequências

O novo campo é aditivo no JSON do resumo. O resultado é uma prova limitada do formato sintético, não evidência de que uma operação concreta pode ser executada. O parser e o codificador usam apenas a biblioteca padrão; não há dependência nova.
