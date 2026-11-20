# 0086. Registro de confirmação humana de achados

- **Status:** Proposto
- **Data:** 2026-11-16
- **Origem:** fase B da V1.11

## Contexto

A triagem é consultiva e não registra que uma pessoa viu a falha. Confirmar não pode alterar achados, severidade ou status. O painel apresenta separadamente a declaração humana.

## Decisão

Vamos registrar declarações aditivas em `human-confirmations.json`, ao lado de `findings.json`, com schema v1: `schema_version`, `product`, `run_id` e `entries`; cada entrada contém `fingerprint`, `person`, `confirmed_at` UTC e `observation`. O leitor valida o envelope e seu contexto; ausência significa nenhum registro, corrupção é erro. O escritor valida o relatório e o fingerprint atual, preserva entradas anteriores, usa trava exclusiva e substituição atômica. A observação passa pela redação existente, que é uma proteção por padrões e não garante remover segredos desconhecidos.

`hdast finding acknowledge PRODUTO FINGERPRINT --run RUN_ID` recusa `--json` e falta de TTY em stdin, stdout ou stderr; solicita quem, o que viu e a digitação do fingerprint para confirmar. Não há opção ou ambiente para substituir a digitação. O bloqueio em settings é uma camada adicional, não uma garantia. Um agente arbitrário pode simular TTY e entrada; identidade e presença humana não são autenticadas. Leitores usam `FileHumanConfirmationStore.read(product, run_id)` e `contains(fingerprint)` para alimentar `confidence_step(..., confirmed_by_person=...)`.

## Alternativas consideradas

- Gravar em `triage.json`: mistura opinião de agente com declaração humana.
- Modificar `findings.json`: viola o caráter aditivo e pode perder a declaração ao regerar o relatório.
- Aceitar flag de confirmação: permite operação automatizada sem a interação prevista.

## Consequências e aceites

O registro não prova identidade nem a veracidade da declaração. Registros múltiplos para o mesmo achado são preservados. Uma trava órfã exige intervenção humana após verificar que não há escritor ativo. O teste deve cobrir recusa de TTY e JSON, cancelamento, entradas inválidas, referência inexistente, mistura de contexto, persistência aditiva e redação.
