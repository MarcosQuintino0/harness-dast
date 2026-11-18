# QA independente da V1.5.5

Data: 2026-11-15. Bases examinadas: `1056db5`, `12e6186` e correções em `1e687fa`. Sem Docker ou acesso a produto real.

## Achados comunicados para correção

1. **Leitura de objeto errado.** Na base `1056db5`, o planejador preferia um GET da conta escritora para outro identificador a um GET de outra conta para o identificador exato. O teste independente reproduziu a seleção incorreta. A correção integrada em `12e6186` passou nesse mesmo teste e exige alvo concreto igual.
2. **Objeto antigo no par criado.** Na base `12e6186`, um POST idempotente retornou o ID de um objeto já lido no probe, sem criar nada; a comparação gerou um achado e contou criação. O teste independente reproduziu a falha; os testes de regressão passaram em `1e687fa`. A regra exige HTTP 201 e rejeita alvo já lido: depende da semântica do servidor e não prova novidade absoluta. HTTP 200 fica inconclusivo e pode ter deixado recurso no ambiente.
3. **Retentativa ultrapassa o teto de escrita.** Na base `12e6186`, teto 1 e resposta 401 produziram 2 POSTs. A correção limita cada escrita e restauração a uma tentativa; a regressão passou em `1e687fa`. Respostas 401 e 429 na atribuição em massa ficam inconclusivas.
4. **Rótulo de CORS:** o literal `Pol?tica` foi corrigido em `1e687fa`.
5. **Retentativa ultrapassa o teto CORS.** Com `cors_max_requests: 1` e resposta 401, a base `12e6186` enviou dois GETs. A regressão passou em `1e687fa`, que limita o envio a uma tentativa.

## Verificações dirigidas

- 53 testes passaram para espera, criação de par, planejamento de leitura, CORS e os cenários independentes de alvo exato e teto CORS zero.
- Mais dois testes independentes de espera passaram: releitura após o término concorrente e isolamento de uma tomada antiga da trava.
- Na base `1e687fa`, 16 testes independentes e de regressão passaram, incluindo os dois cenários de criação e teto, teto CORS, cerca `deny_paths`, espera concorrente e isolamento da trava. A correção de leitura para alvo exato também passou.
- Uma execução ampliada mostrou 56 testes em 100%, mas o processo não encerrou e foi interrompido; não é contada como gate aprovado. A execução dirigida de 16 testes terminou com saída 0.
- O cenário de teste novo de atribuição com nomes específicos de uma API foi substituído por contratos sintéticos genéricos na base examinada. As provas em laboratório e casos de avaliação podem identificar os alvos.

Não houve prova de laboratório, suíte completa ou gates de integração nesta revisão; esses resultados pertencem à execução do coordenador. A revisão não comprova ausência de defeitos e não substitui as provas nas duas APIs.
