# Regras de dados: `data-rules.yml` (schema v1)

Esta página descreve o schema v1 **como implementado** em `src/harness_dast/domain/datagen.py` (modelo e precedência), `datagen_catalog.py` (catálogo e argumentos) e `request_builder.py` (montagem da requisição). Os geradores estão em `src/harness_dast/adapters/datagen/`. Decisões: [ADR 0006](../decisoes/0006-regras-de-dados-declarativas.md) e [ADR 0016](../decisoes/0016-leitor-de-openapi-proprio-e-esquema-de-unicidade.md).

> **O que existe e o que não existe.** Existem o modelo validado (`DataRules.from_data(dados)`), o catálogo de geradores, o leitor de OpenAPI e a montagem da requisição. `hdast probe` e `hdast scan` leem este arquivo: a fiação (casos de uso e CLI) vem depois. Hoje a validação é exercida pelos testes; um deles valida o `products/_template/data-rules.yml`.

## Para que serve

O ZAP, sozinho, envia valores genéricos que a API rejeita (400) ou que colidem com registros existentes (409). O harness monta **uma requisição válida por operação** a partir do esquema do OpenAPI, e estas regras dizem como gerar os campos que o esquema sozinho não resolve: documento com dígito verificador, código numérico, e-mail em domínio de teste, valores que não podem repetir.

Todos os dados gerados são **sintéticos**. Nunca use dados de pessoas reais.

## Estrutura

```yaml
schema_version: 1          # obrigatório; somente 1
rules:                     # lista (até 500 regras); pode ser vazia
  - match:
      field: cpf           # obrigatório
      operation: criar     # opcional
      location: body       # opcional
    generator: br.cpf      # obrigatório: nome do catálogo
    args: { formatted: false }   # opcional
    unique: true           # opcional; padrão false
```

Todo bloco rejeita **campo desconhecido**. Erros saem em `CONFIG_ERROR` (código de saída 2): `Arquivo data-rules.yml inválido (N problema(s)):` e uma linha `- rules[2].generator: explicação` por problema. A mensagem cita o caminho do campo, nunca o valor recebido.

### `match`

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `field` | texto, obrigatório | Nome do campo (`cpf`) ou caminho com pontos (`endereco.cpf`, até 10 segmentos). Compara com o **final** do caminho do campo na requisição, sem índices de lista: `cpf` casa `cpf`, `socio.cpf` e `itens[].cpf`. Diferencia maiúsculas |
| `operation` | texto, opcional | `operationId` do OpenAPI. Limita a regra a uma operação |
| `location` | opcional | `path`, `query`, `header`, `cookie` ou `body`. Parâmetros usam o nome do parâmetro como `field`. Parâmetro `header` de roteamento (`Host`, `Content-Length`, `Transfer-Encoding`, `Connection`, `Upgrade`, `TE`, `Expect`, `Proxy-*`, `X-Forwarded-*`...) nunca é enviado, com ou sem regra: aparece como pulado, com o motivo ([ADR 0025](../decisoes/0025-limpeza-confirmacao-so-em-terminal-e-correcoes-do-qa-m2-m5.md)) |

### Precedência

Entre as regras que casam com um campo, vale a **mais específica**, comparando nesta ordem:

1. tem `operation`;
2. `field` com mais segmentos (`endereco.cpf` vence `cpf`);
3. tem `location`.

Duas regras com o **mesmo `match` completo** são ambíguas e o arquivo é recusado (`regras 1 e 3 têm o mesmo match`). Não existe empate silencioso.

Para um campo sem regra, o harness usa, nesta ordem: o valor encadeado de `flows.yml`; o primeiro valor do `enum`; um valor implícito pelo tipo e formato (`uuid`, `email`, `date`, `date-time`, `uri`, inteiro e número dentro dos limites, texto alfanumérico respeitando `minLength`/`maxLength`, `pattern` simples). `example` e `default` do OpenAPI **não** são usados (repetem valores e causam 409). `oneOf`/`anyOf` usam a primeira alternativa que não seja `null`; listas têm `max(minItems, 1)` itens; campos opcionais são enviados quando se sabe gerá-los; campos `readOnly` nunca são enviados.

### `unique`

`unique: true` pede um valor novo a cada uso, **dentro da execução** e de forma rastreável. O valor embute a etiqueta da execução (sufixo hexadecimal do `RunId`) e um contador, onde as restrições do campo permitem:

| Gerador | Onde a etiqueta e o contador entram |
| --- | --- |
| `alphanumeric`, `email`, `uri` | Texto `etiqueta` + contador de 4 dígitos hex (`7f3a0012`); campo curto corta a etiqueta pela direita, nunca o contador. Capacidade: 65 536 por execução |
| `numeric`, `br.cpf`, `br.cnpj` (raiz), `br.cns`, `br.phone`, `br.cep`, `br.crm` (número) | Contador nos últimos `c` dígitos (a largura inteira se for até 4; senão metade, mínimo 4) e, no restante, `int(etiqueta, 16) mod 10^p`. Capacidade: `10^c` (10 000 para CPF e CNPJ) |
| `uuid` | Os 12 primeiros dígitos hex são a etiqueta (8, completada com zeros) e o contador (4) |
| `integer` | Único na execução, mas **não** rastreável pela etiqueta |
| `sequence` | Cresce a cada uso; **repete entre execuções** (use `numeric` se houver risco de 409 entre execuções) |

O contador é um só por execução e avança a cada valor único pedido, em qualquer regra. O domínio ainda confere, por regra, que nenhum valor único se repete. A limpeza SQL do produto (escrita por uma pessoa) pode procurar a etiqueta no que foi criado. `unique: true` num gerador que não o aceita (`number`, `boolean`, `date`, `datetime`, `choice`, `constant`, `synthetic_file`) é recusado.

## Catálogo de geradores

Catálogo **fechado**: só estes nomes valem. Argumentos desconhecidos, de tipo errado (`true` não é `1`) ou fora do intervalo são recusados.

| Gerador | Argumentos (padrão) | Valor |
| --- | --- | --- |
| `numeric` | `digits` (obrigatório, 1 a 30) | Texto de N dígitos decimais (zeros à esquerda possíveis). Em campo inteiro vira número |
| `integer` | `min`, `max` (padrão: limites do esquema) | Inteiro no intervalo |
| `number` | `min`, `max`, `decimals` (2, de 0 a 6) | Número decimal |
| `boolean` | nenhum | `true` ou `false` |
| `alphanumeric` | `length` (1 a 256; padrão pelo esquema, 10), `prefix` (vazio) | Letras minúsculas e dígitos |
| `uuid` | nenhum | UUID versão 4 |
| `email` | `domain` (`example.test`), `prefix` (`hd`) | `prefix` + texto, `@domain`. O domínio padrão é reservado a testes (RFC 2606) |
| `uri` | `base` (`https://example.test`) | `base/r/...` |
| `date` | `min_offset_days`, `max_offset_days` (-365, 365) | `AAAA-MM-DD` a N dias de hoje (UTC, do relógio injetado) |
| `datetime` | `min_offset_days`, `max_offset_days` (-365, 365) | RFC 3339 em UTC (`...Z`) |
| `choice` | `values` (lista de escalares, obrigatório, até 200) | Um valor sorteado |
| `constant` | `value` (escalar, obrigatório) | Sempre o mesmo valor |
| `sequence` | `start` (1), `step` (1 a 1000), `prefix` (vazio) | `start + step * posição` |
| `synthetic_file` | `kind` (`text`, `csv`, `json` ou `png`; padrão `text`), `name` (nome do arquivo; padrão `synthetic.<ext>`) | Arquivo sintético de um campo `multipart/form-data` (ADR 0052); devolve o texto `tipo:nome`. Não aceita `unique` |
| `br.cpf` | `formatted` (`false`) | CPF com dígitos verificadores válidos; nunca todos os dígitos iguais. Máscara `000.000.000-00` |
| `br.cnpj` | `formatted` (`false`) | CNPJ **numérico** válido, filial `0001`. Máscara `00.000.000/0000-00`. O CNPJ alfanumérico não é gerado |
| `br.cns` | `kind` (`definitive` ou `provisional`) | CNS de 15 dígitos válido (definitivo começa em 1 ou 2; provisório em 7, 8 ou 9) |
| `br.phone` | `mobile` (`true`), `ddd` (sorteado entre os DDDs em uso), `formatted`, `country_code` | Celular (9 + 8 dígitos) ou fixo (2 a 5 + 7 dígitos). Pode coincidir com número real |
| `br.cep` | `formatted` (`false`) | 8 dígitos, nunca `00000000`. Máscara `00000-000` |
| `br.crm` | `digits` (7, de 4 a 8), `uf` (`SP`, uma das 27 siglas) | CRM sintético `NNNNNNN-UF`. Com `unique: true` os dígitos seguem a regra dos numéricos únicos; use 7 dígitos ou mais para o número não repetir entre execuções seguidas (com 5 só sobra 1 dígito para a etiqueta e a chance de colisão é de 10%) |

Os algoritmos de CPF, CNPJ e CNS estão descritos, com a fonte, em `adapters/datagen/checkdigits.py`.

### Aleatoriedade e relógio

Os geradores não leem o relógio nem o sorteador global: a **semente** e o **instante de referência** entram por parâmetro (`GeneratorCatalogue(seed, now)`). Mesma semente, mesmo instante e mesma sequência de pedidos produzem exatamente as mesmas requisições.

## `pattern` do OpenAPI

O `pattern` vem de documento não confiável e **não é executado com `re`**. O harness entende só um subconjunto sem grupos nem alternância: caracteres literais, `.`, classes `[a-z0-9]`/`[^...]`, `\d \D \w \W \s \S`, escapes de pontuação, âncoras `^`/`$` nas pontas e quantificadores `? * + {n} {n,} {n,m}` (n, m até 256). Dentro dele, o valor é gerado e conferido. Fora dele (grupos, `|`, `\b`...), o harness **não adivinha**: se o campo for obrigatório e não tiver regra, a montagem falha com `CONFIG_ERROR` pedindo uma regra para o campo; se for opcional, o campo é omitido e listado em `skipped_fields`. Numa regra, o valor gerado não é conferido contra um `pattern` fora do subconjunto: a responsabilidade é de quem escreveu a regra.

## Garantias da montagem

Todo valor, venha de regra, de `enum` ou do esquema, é conferido contra o esquema (tipo, `enum`, limites, tamanho, formato e `pattern` suportado) antes de entrar na requisição. Valor de **regra** que viola o esquema é `CONFIG_ERROR` citando o número da regra (a partir de 1) e os problemas, sem repetir o valor. Texto numérico vira inteiro em campo inteiro, e inteiro vira texto em campo de texto; qualquer outra diferença de tipo é erro.

## Exemplo

```yaml
schema_version: 1
rules:
  - match: { field: cpf }
    generator: br.cpf
    unique: true
  - match: { operation: criarConvenio, field: codigo }
    generator: numeric
    args: { digits: 8 }
    unique: true
  - match: { field: email }
    generator: email
    args: { domain: "teste.exemplo.com.br" }
    unique: true
```

## Limites conhecidos

- `uniqueItems`, `additionalProperties`, `not`, `discriminator`, `prefixItems`, `multipleOf` e `minProperties` do esquema não são considerados.
- Em `allOf`, formatos ou `pattern` diferentes, tipos incompatíveis ou limites contraditórios dão `CONFIG_ERROR`.
- Corpos que não são JSON (formulário, XML) são montados como valor JSON com o tipo de mídia informado; quem envia codifica.
- **Envio de arquivo (`multipart/form-data`, ADR 0052).** O `probe` alcança a operação com um arquivo **sintético** de lista fechada: `text` (`synthetic.txt`, 15 bytes), `csv`, `json` ou `png` (1x1, 67 bytes), nunca mais de 1 KiB, nunca executável, conteúdo constante. É arquivo a propriedade `type: string` com `format: binary` (ou a lista de itens `binary`, que vira um arquivo só); `format: byte` é texto em base64, não arquivo. As demais propriedades escalares seguem as regras de sempre. O tipo vem, do menos para o mais específico, de: padrão `text`; `encoding.<campo>.contentType` do OpenAPI (`image/png`, `text/csv`, `application/json`; qualquer outro tipo, como `image/jpeg`, volta a `text`); regra `synthetic_file` no campo. Quando o alvo recusa o tipo padrão (`validation_error`), escreva a regra:

```yaml
  - match: {field: arquivo, operation: enviarDocumento, location: body}
    generator: synthetic_file
    args: {kind: png, name: foto.png}
```

  `name` usa de 1 a 64 caracteres ASCII (letras, dígitos, `_`, `.`, `-`), sem barra, sem `..` e sem aspas, e a extensão precisa ser a do tipo. O corpo todo não passa de 16 KiB nem de 20 partes. Campo aninhado, objeto vazio, nome de campo fora da regra e OpenAPI 3.1 (`contentMediaType`, não modelado) viram `build_error` com a dica do que fazer. O `exchanges.json` guarda só nome, tipo e tamanho das partes (nunca o arquivo, os valores nem a fronteira); o teste de autorização não repete esse pedido (`unsupported_body`).
- Listas com mais de 20 itens obrigatórios, ou campos obrigatórios aninhados além de 12 níveis, exigem regra.
