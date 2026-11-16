# 0074. Migra??o expl?cita e compatibilidade

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

Perfis sem estrat?gia devem permanecer equivalentes, sem adquirir novos poderes.

## Decis?o

Vamos manter perfis antigos operacionais sem estrat?gia. A migra??o ? expl?cita, produz c?pia separada e diff, nunca sobrescreve origem nem altera autoriza??o ou registro de aprova??o; n?o cria par?metros protegidos novos. Sa?da usa envelope v1; erro de entrada ou destino inseguro usa `CONFIG_ERROR`, sa?da 2, e n?o deixa escrita parcial. O comando e campos espec?ficos de resultado ser?o fixados com a aplica??o.

## Alternativas consideradas

Migrar implicitamente confundiria origem e poderia atribuir ? aprova??o antiga um novo significado.

## Consequ?ncias

Testes demonstram equival?ncia item por item, aus?ncia de altera??es na origem e recusa de alargamento ou aprova??o transferida.
