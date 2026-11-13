# 0016. Leitor de OpenAPI próprio, subconjunto seguro de `pattern` e esquema de unicidade

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** Marco M3; detalha o [ADR 0006](0006-regras-de-dados-declarativas.md) e o [ADR 0007](0007-zap-alimentado-por-requisicoes-validas.md); pendência P-12

## Contexto

O M3 monta uma requisição válida por operação a partir do OpenAPI e das regras de dados. Três decisões precisam de registro: como ler o OpenAPI (documento **não confiável**), como tratar `pattern` (expressão regular **não confiável**) e como garantir valores únicos que a limpeza consiga achar depois. Também precisa ficar escrito o que "um nível" de encadeamento proíbe.

## Decisão

### 1. Nenhuma dependência nova: `json` + `yaml.safe_load` + resolvedor próprio

O leitor (`adapters/openapi/`) usa a biblioteca padrão (`json`) e o PyYAML que já é dependência (ADR 0012), mais um resolvedor de `$ref` próprio e limitado. Só aceita referências locais (`#/...`); URL e arquivo externo são `ConfigError`. Limites: arquivo de até 5 MiB, 500 mil nós e 128 níveis de aninhamento no documento (contados sem recursão, o que barra bomba de aliases e estruturas que apontam para si mesmas), 200 mil esquemas expandidos, 24 níveis de esquema (além disso o nó é marcado `truncated`) e 16 saltos de `$ref` encadeada. Referência recursiva corta o ciclo e marca o nó. Swagger 2.0 é detectado e recusado com dica de conversão (a conversão está fora do escopo da V1).

### 2. `pattern` só no subconjunto seguro

`domain/pattern_subset.py` aceita uma gramática sem grupos nem alternância (átomos, classes, `.`, `\d \w \s`, quantificadores `? * + {n,m}` até 256). O casamento é feito por programação dinâmica própria, em tempo polinomial, sem `re`. Fora do subconjunto, o harness **não adivinha**: para campo sem regra levanta erro pedindo uma regra em `data-rules.yml`; com regra, o valor gerado é aceito sem conferir o `pattern`.

### 3. Esquema de unicidade e etiqueta da execução

- A **etiqueta** é o sufixo hexadecimal do `RunId` (4 a 8 dígitos). O **contador** é um só por execução, avançado a cada valor `unique` pedido, em qualquer regra.
- Texto: `etiqueta + contador em 4 hex` (capacidade de 65 536 por execução); campo curto corta a etiqueta pela direita, nunca o contador.
- Dígitos: contador nos últimos `c` dígitos (`c` = largura inteira até 4; senão metade, mínimo 4) e o resto vem de `int(etiqueta, 16) mod 10^p`. CPF e CNPJ comportam 10 000 valores por execução.
- Inteiro único é único mas não rastreável pela etiqueta. `sequence` repete entre execuções (use `numeric` quando houver risco de 409 entre execuções).
- O domínio ainda confere, por regra, que nenhum valor único se repete; repetição é `ConfigError`.
- A limpeza SQL do produto (autoria humana) pode localizar o que foi criado procurando a etiqueta (ou o prefixo numérico recalculável a partir dela).

### 4. "Um nível" de encadeamento

Uma operação pode ser **produtora ou consumidora, nunca as duas**. Proíbe `A -> B -> C`, qualquer ciclo e `A -> A`. Permite um produtor para vários consumidores e um consumidor com vários produtores, desde que cada destino (`B.param` ou `B.field`) tenha uma só fonte. Ciclo e profundidade têm mensagens distintas.

## Alternativas consideradas

- **`openapi-spec-validator`, `prance` ou `openapi-core`.** Validam mais do que o harness usa, puxam `jsonschema`/`referencing` e (os dois primeiros) resolvem referências remotas, o que é superfície de ataque para um documento não confiável. Descartadas.
- **Executar o `pattern` com `re`.** Backtracking catastrófico (ReDoS) com expressão do documento. Descartada.
- **Gerar o `pattern` com biblioteca (`rstr`, `exrex`, Faker).** Dependência nova para um caso que a regra declarativa resolve. Descartada.
- **Unicidade só por sorteio aleatório.** Colide e não deixa rastro para a limpeza. Descartada.
- **Encadeamento de profundidade livre.** Contraria P-12; fica para uma versão futura com ADR novo.

## Consequências

- Nenhuma dependência de runtime nova; o contrato do import-linter do `domain` continua valendo (PyYAML já estava proibido ali).
- Documentos que usam construções fora do subconjunto exigem regra explícita para o campo.
- Limites do leitor podem recusar especificações enormes; o erro diz qual limite e o que fazer.
- O CNPJ alfanumérico (julho de 2026) não é gerado; só o numérico.
- Telefone e CEP têm formato válido e podem coincidir com números reais; usar só em ambiente de teste.
