# 0073. Aprovação e classificação das alterações

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto

Aprovação antiga não pode virar autoridade sobre parâmetros novos.

## Decisão

Vamos distinguir automática (neutra e dentro do envelope), proposta pendente (interpretação, contrato ou cobertura) e decisão humana (permissão, escopo, teto, janela ou política protegida). V1.8 aplica apenas escolhas neutras sem mudar cobertura ou ritmo; recusa novas permissões. A aprovação continua sendo ato de pessoa pelo fluxo existente; validar ou compilar não aprova. Mudança protegida invalida aprovação conforme o fingerprint vigente.

Na pilha gerenciada, o proxy vincula os hashes SHA-256 da aprovação e do perfil, além de autorização e janela, e os revalida a cada concessão junto de prazo e parada. Os diretórios são montados somente para leitura e suas raízes devem permanecer estáveis; substituir a própria raiz montada pode não ser observado. Mudança ou falha das fontes produz recusa auditável `approval_changed`. Uma concessão já enviada não é cancelada. Alterar ou renovar qualquer arquivo vinculado exige recriar a pilha; não exige nova aprovação se o fingerprint permanecer válido. `stack up` reconstrói obrigatoriamente a imagem principal, que precisa conhecer esse vínculo.

A [prova da coordenação](../../evals/measurements/v1-8/closure/coordinator/revocation-passed.json) observou concessão seguida de recusa após remoção da aprovação temporária, sem concessão posterior. A reprodução independente permanece pendente; essa prova não elimina as limitações acima.

## Alternativas consideradas

Tratar toda mudança como automática permitiria redução oculta de qualidade; exigir aprovação para prévia impediria inspeção segura.

## Consequências

Diff identifica classe sem divulgar valores livres; proposta pendente não se torna executável automaticamente. Testar mudança, revogação e corrida antes da concessão.
