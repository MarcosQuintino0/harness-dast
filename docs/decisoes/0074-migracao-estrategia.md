# 0074. Migração explícita e compatibilidade

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

Perfis sem estratégia devem permanecer equivalentes, sem adquirir novos poderes.

## Decisão

Vamos manter perfis antigos operacionais sem estratégia. A migração é explícita, produz cópia separada e diff, nunca sobrescreve origem nem altera autorização ou registro de aprovação; não cria parâmetros protegidos novos. Saída usa envelope v1; erro de entrada ou destino inseguro usa `CONFIG_ERROR`, saída 2, e tenta remover arquivo parcial em falha de escrita; se a remoção também falhar, informa erro e pode restar arquivo incompleto. O comando implementado é `hdast strategy migrate <produto> [--output strategy.migrated.yml]`, com `--products-dir` opcional. No sucesso, `data` contém `product`, `copy`, `changes: ["strategy_added"]`, `classification: "automatic"` e `approval_changed: false`. A cópia não é ativada automaticamente; deve ser revisada e ativada explicitamente como `strategy.yml`. Uma estratégia existente impede a migração. O nome deve seguir `strategy.<nome>.yml`, usando letras minúsculas, dígitos ou hífen; arquivo existente não é sobrescrito.

## Complemento: captura explícita do vínculo atual

Proposto em 2026-11-16 antes do código complementar e implementado no código da V1.8: `hdast strategy capture <produto> [--output strategy.captured.yml]` consulta somente a versão do ZAP da pilha local gerenciada e ativa do produto, sem enviar pedido ao alvo. Usa apenas o endpoint e a chave publicados pelo gerenciador, sem override de URL, e recusa controle remoto ou colisão com a porta do alvo local. A captura toma a trava interna da pilha durante conferência, consulta e escrita; pilha ocupada usa `STACK_BUSY`, saída 8. É uma ação explícita distinta das consultas secas e da migração neutra, que continuam sem rede.

O comando exige perfil formal aprovado e vigente, pilha ativa do mesmo produto, sem `KILL`, e estado, execução e endpoint correspondentes; valida documentos e planejamento locais e aceita somente estratégia ausente ou neutra. Depois da consulta, revalida perfil, aprovação e documentos. Produz cópia exclusiva com referências fixas e uma escolha `coverage/preserve`, origem `observation`, razão `preserve_baseline`, validade limitada à autorização e vínculo atual calculado independentemente. O estado validado descreve essas invariantes neutras; a observação não concede permissão. Não lê execução anterior, não altera perfil/aprovação/estratégia ativa e não ativa a cópia.

Sucesso usa envelope v1 com `product`, `copy`, `changes: ["strategy_bound"]`, `classification: "automatic"`, `approval_changed: false` e `activated: false`, saída 0. Entrada/destino/documento/motor inválido não deixa cópia e usa `CONFIG_ERROR`, saída 2; falta de aprovação/vigência usa saída 3; indisponibilidade do ZAP usa o erro externo vigente. O destino segue `strategy.<nome>.yml`, confinado ao produto e sem sobrescrita. A execução posterior revalida todas as dependências, incluindo a versão observada do motor, e não confia no conteúdo capturado como autoridade.

O mesmo endpoint configurado não prova identidade criptográfica, do processo, nem protege contra reinício ou proxy reverso. A captura pública e o vínculo LIVE tiveram prova real da coordenação; a reprodução independente também passou em cinco testes, conforme o [parecer de fechamento](../arquivo/reviews/2026-11-16-v1-8-validacao-fechamento.md). Essa captura de metadados atuais não implementa reutilização de contas, dados, recursos, fluxos executados ou conhecimento de execuções passadas da V1.9. A revalidação por concessão do proxy está implementada e teve prova real de revogação pela coordenação; ela não resolve a corrida de identidade do motor após a consulta. As raízes montadas devem permanecer estáveis e pedidos já concedidos não são cancelados.

## Alternativas consideradas

Migrar implicitamente confundiria origem e poderia atribuir à aprovação antiga um novo significado.

## Consequências

Testes demonstram equivalência item por item, ausência de alterações na origem e recusa de alargamento ou aprovação transferida.
