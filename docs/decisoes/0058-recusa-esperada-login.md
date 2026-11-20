# 0058. Recusa esperada na operação de login

- **Status:** Proposto
- **Data:** 2026-11-15

## Contexto

O login do contrato usa dados sintéticos gerados; a recusa HTTP 401 ou 403 não prova falha das contas conferidas no preflight. Classificá-la como falha de autenticação induz uma parada indevida.

## Decisão

Somente POST no caminho `auth.token_path` do perfil, ao receber 401 ou 403, é `auth_rejected_expected`; rejeição de CSRF continua `csrf_error`. Essa classe conta como alcançada, mas não como sucesso 2xx nem comprovação de autenticação. `summary.reached` soma `successes` e recusas esperadas; as duas razões de alcance usam essa soma. `by_outcome` mantém as classes separadas.

Login continua fora do scan, pois varreduras gerariam tentativas que podem bloquear contas; o negative também o exclui como infraestrutura e os pedidos anônimos não entram em `exchanges.json`. A injeção no login permanece não testada nesta versão. As demais travas e autorizações permanecem vigentes.

Relatório e painel distinguem a recusa esperada de falha de autenticação e a contam no alcance. O contrato de `findings.json` acrescenta `probe_reached` à cobertura e `probe_outcome` aos itens não testados, opcionais para arquivos históricos; a mensagem existente incorpora o motivo do último probe e a cobertura parcial registra lacunas elegíveis.

## Consequências

Há mudança no contrato de `probe.json` e nos números de alcance; leitores de arquivos antigos devem admitir os novos campos ausentes. Preflight ainda é a prova de uso das contas, e a operação de login continua sem prova de injeção.

Os compositores de relatório e painel já concentram modelos e seções acima de 300 linhas. Mantêm-se juntos para preservar as interfaces e os arquivos de referência; as novas decisões de lacuna ficam em funções puras nomeadas. `_not_tested` passa a 45 linhas para reunir motivo da varredura e resultado do probe sem duplicar a montagem dos três formatos.
