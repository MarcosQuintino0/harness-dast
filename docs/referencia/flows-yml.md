# Encadeamento: `flows.yml` (schema v1)

Esta página descreve o schema v1 **como implementado** em `src/harness_dast/domain/flow.py`. Decisões: [ADR 0006](../decisoes/0006-regras-de-dados-declarativas.md) e [ADR 0016](../decisoes/0016-leitor-de-openapi-proprio-e-esquema-de-unicidade.md); vários níveis (grafo sem ciclos) desde o [ADR 0021](../decisoes/0021-esquema-aditivo-do-perfil-para-o-alvo-piloto.md).

> **O que existe e o que não existe.** Existem o modelo validado (`FlowSpec.from_data(dados)`), a conferência contra o OpenAPI, a ordenação e a extração de valores de respostas. `hdast probe` lê este arquivo nem que execute as chamadas: a fiação vem depois. Um teste valida o `products/_template/flows.yml`.

## Para que serve

Muitas operações precisam de um identificador devolvido por outra (criar paciente, depois buscar paciente). Sem isso, o ZAP usaria ids inventados e só veria 404. Cada *binding* diz qual operação **produz** um valor (um campo da resposta) e quais operações o **consomem** (um parâmetro ou um campo do corpo).

## Estrutura

```yaml
schema_version: 1            # obrigatório; somente 1
bindings:                    # até 200; pode ser vazia
  - produces:
      operation: criarPaciente   # operationId
      field: id                  # caminho do campo na resposta de sucesso (ex.: id, data.id, items.0.id)
    consumed_by:                 # de 1 a 50 destinos
      - { operation: buscarPaciente, param: pacienteId }   # parâmetro (path, query, header ou cookie)
      - { operation: criarConsulta, field: pacienteId }    # campo do corpo (aceita caminho com pontos)
```

Em cada destino, informe **exatamente um** entre `param` e `field`. Caminhos de campo têm até 10 segmentos separados por ponto; um segmento numérico indexa uma lista. Todo bloco rejeita campo desconhecido. Erros saem em `CONFIG_ERROR` (código de saída 2): `Arquivo flows.yml inválido (N problema(s)):`, uma linha por problema, sem repetir valores recebidos.

## Vários níveis: o que é aceito e o que é recusado

O encadeamento é um **grafo dirigido sem ciclos**: uma operação pode consumir de uma e produzir para outra. A Clínica Piloto precisa de `convênio -> paciente -> consulta -> receita`.

| Situação | Resultado |
| --- | --- |
| `A -> B` (A produz, B consome) | Aceita |
| `A -> B` e `A -> C` (um produtor, vários consumidores) | Aceita |
| `A1 -> B` e `A2 -> B` (um consumidor, vários produtores) | Aceita, desde que cada destino tenha uma só fonte |
| `A -> B -> C` (B consome de A e produz para C) | Aceita (antes do ADR 0021 era recusada) |
| `A -> B -> A`, `A -> A` ou qualquer ciclo | Recusada com a mensagem de ciclo e o caminho (`'a' -> 'b' -> 'a'`) |
| Cadeia com mais de `MAX_FLOW_DEPTH` (6) operações | Recusada: `cadeia de N operações; o máximo é 6` |
| Dois bindings alimentando o mesmo `B.param` (ou `B.field`) | Recusada: o destino recebe valor de mais de uma fonte |

O ciclo é verificado antes da profundidade, então cada problema tem sua mensagem. A profundidade conta **operações** no maior caminho (`A -> B -> C` tem 3); o teto é a constante `MAX_FLOW_DEPTH` em `domain/flow.py`.

No `probe`, uma falha no meio da cadeia propaga: se `criarPaciente` não tem sucesso, `criarConsulta` e `criarReceita` saem como `skipped_dependency` (a mensagem diz que o produtor não teve sucesso). `--only criarReceita` traz junto, em qualquer nível, todos os produtores de que ela depende.

## Conferência contra o OpenAPI

`FlowSpec.validate_against(api)` levanta `ConfigError` se uma operação não existe, se o `param` não é parâmetro da operação consumidora, se o `field` do destino não existe no esquema do corpo, ou se o `field` produzido não existe no esquema da resposta de sucesso. Se a operação produtora **não declara** esquema de resposta, o campo não pode ser conferido e é aceito.

## Ordenação e execução

- `execution_order(operation_ids)` devolve todas as operações com cada produtor antes de seus consumidores; sem dependência, vale a ordem recebida (determinístico).
- `resolve_bindings(operation_id, respostas)` extrai, do corpo JSON de cada produtor, os valores que a operação consome (`ResolvedBindings`: `params` e `fields`). Só texto e inteiro podem ser encadeados. Resposta ausente, campo ausente ou valor de outro tipo é `TargetError` (código de saída 6), e a mensagem cita o caminho do campo, nunca o conteúdo da resposta.
- O `RequestBuilder` usa esses valores no lugar da geração e os confere contra o esquema do destino.
