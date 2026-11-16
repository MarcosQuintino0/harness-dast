# 0074. Migração explícita e compatibilidade

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

Perfis sem estratégia devem permanecer equivalentes, sem adquirir novos poderes.

## Decisão

Vamos manter perfis antigos operacionais sem estratégia. A migração é explícita, produz cópia separada e diff, nunca sobrescreve origem nem altera autorização ou registro de aprovação; não cria parâmetros protegidos novos. Saída usa envelope v1; erro de entrada ou destino inseguro usa `CONFIG_ERROR`, saída 2, e tenta remover arquivo parcial em falha de escrita; se a remoção também falhar, informa erro e pode restar arquivo incompleto. O comando implementado é `hdast strategy migrate <produto> [--output strategy.migrated.yml]`, com `--products-dir` opcional. No sucesso, `data` contém `product`, `copy`, `changes: ["strategy_added"]`, `classification: "automatic"` e `approval_changed: false`. A cópia não é ativada automaticamente; deve ser revisada e ativada explicitamente como `strategy.yml`. Uma estratégia existente impede a migração. O nome deve seguir `strategy.<nome>.yml`, usando letras minúsculas, dígitos ou hífen; arquivo existente não é sobrescrito.

## Alternativas consideradas

Migrar implicitamente confundiria origem e poderia atribuir à aprovação antiga um novo significado.

## Consequências

Testes demonstram equivalência item por item, ausência de alterações na origem e recusa de alargamento ou aprovação transferida.
