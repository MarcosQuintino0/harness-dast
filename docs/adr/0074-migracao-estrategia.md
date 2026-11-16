# 0074. Migração explícita e compatibilidade

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

Perfis sem estratégia devem permanecer equivalentes, sem adquirir novos poderes.

## Decisão

Vamos manter perfis antigos operacionais sem estratégia. A migração é explícita, produz cópia separada e diff, nunca sobrescreve origem nem altera autorização ou registro de aprovação; não cria parâmetros protegidos novos. Saída usa envelope v1; erro de entrada ou destino inseguro usa `CONFIG_ERROR`, saída 2, e não deixa escrita parcial. O comando proposto é `hdast strategy migrate <produto> [--output strategy.migrated.yml]`, com `--products-dir` opcional. No sucesso, `data` contém `product`, `copy`, `changes: ["strategy_added"]`, `classification: "automatic"` e `approval_changed: false`.

## Alternativas consideradas

Migrar implicitamente confundiria origem e poderia atribuir à aprovação antiga um novo significado.

## Consequências

Testes demonstram equivalência item por item, ausência de alterações na origem e recusa de alargamento ou aprovação transferida.
