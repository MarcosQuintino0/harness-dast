# ADR 0046 — Cobertura de operações com HTTP 404

- Estado: Proposto
- Data: 2026-11-14

## Contexto

Uma operação pode ter HTTP 404 registrado no probe e não ter entrada de varredura. A mensagem genérica do plano não mostra o status observado e, sem registro de pulo, não informa que o motivo da ausência é desconhecido.

## Decisão

Para operações sem entrada no scan e com status 404 salvo no probe, a mensagem de cobertura informa o status observado separadamente do motivo de ausência. Preserva o código e a mensagem de pulo do scan quando existem. Sem registro de pulo, usa o código `scan_sem_registro` e informa que o motivo não foi registrado. O corpo da resposta não é usado. Os caminhos existentes produzem JSON, Markdown e HTML.

## Consequências

404 é uma observação, não prova de que o recurso inexiste nem explicação da ausência de varredura. Status 410 não é 404. Operações com entrada no scan não entram na lista; resultados antigos sem status mantêm o tratamento anterior. A decisão não modifica o plano ou a execução da varredura.
