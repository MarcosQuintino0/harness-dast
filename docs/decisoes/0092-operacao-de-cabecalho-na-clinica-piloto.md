# 0092. Operação de cabeçalho na Clínica Piloto

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** L3 da V1.12 (`docs/plans/2026-11-17-v1-12-mais-achados.md`)

## Contexto

A trilha F da V1.12 vai acrescentar a injeção em cabeçalhos HTTP (`attack.inject_headers`). Hoje nenhum alvo de laboratório tem uma falha desse tipo para provar a mudança: a Clínica Piloto injeta por consulta, caminho e corpo, mas nunca por cabeçalho. O crAPI não cobre esse caso. As dez falhas históricas (H1 a H10) e o comportamento do modo seguro não podem mudar, para que as rodadas já registradas continuem comparáveis.

## Decisão

Vamos acrescentar à Clínica Piloto uma operação nova, `buscarMedicoPorCabecalho` (`GET /api/medicos/por-cabecalho`), com o cabeçalho obrigatório `X-CRM` documentado no OpenAPI. A falha **H11** concatena o valor do cabeçalho ao SQL só no modo vulnerável; no modo seguro a consulta é parametrizada e a mesma entrada devolve lista vazia. H11 é uma extensão da V1.12 e fica fora dos dez itens históricos.

- O interruptor é o mesmo das demais falhas (o modo `PILOT_VULNERABLE` do alvo).
- Os dois OpenAPI (`lab/pilot/openapi.json` e `lab/pilot/product-profile/openapi.json`) são regenerados pelo próprio alvo, pelo estágio `openapi-out` do `Dockerfile`, nunca à mão.
- H11 entra no gabarito da Clínica (pasta de gabaritos em `evals`) e no `case.yml` do caso `clinica-piloto` com `detectable: false`: não conta na nota. Só a V1.12 (passo F6) poderá detectá-la; nesse momento um ADR ou nota de versão do caso muda o valor. Os casos `clinica-piloto-estrito` e o histórico não mudam.
- O OpenAPI entregue ao agente cego passa a listar a operação nova. A diferença é conhecida e registrada aqui: uma rodada cega nova tem uma operação a mais, sem falha detectável por desenho.

## Alternativas consideradas

- **Alterar uma operação existente** misturaria o controle novo com os resultados históricos e mudaria o que H1 a H10 significam.
- **Simular a resposta sem executar a consulta** reduziria o valor como controle de injeção de SQL.
- **Congelar o OpenAPI entregue ao caso cego** manteria o contrato antigo, mas a imagem do alvo já traria a operação e o contrato entregue ficaria diferente do serviço; foi descartado.

## Consequências

- O alvo de laboratório ganha uma operação e o contrato do OpenAPI cresce de uma operação.
- A regressão dirigida (L5) passa a conferir que H1 a H10 continuam achadas; H11 não entra nesse roteiro enquanto não for detectável.
- A detecção pelo harness e o custo em pedidos dependem da trilha F e de prova dirigida; nada disso é presumido aqui.
- Provada só no laboratório (Clínica Piloto), nunca contra produto real.
