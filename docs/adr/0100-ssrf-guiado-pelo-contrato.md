# 0100. SSRF guiado pelo contrato

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** F3 da V1.12 ([plano](../plans/2026-11-17-v1-12-mais-achados.md)); [ADR 0095](0095-retorno-oast-isolado.md); [ADR 0099](0099-oast-na-varredura.md); desafio de SSRF do crAPI

## Contexto

A imagem do ZAP não tem regra de SSRF (ADR 0099), e uma varredura genérica não sabe quais campos recebem uma URL. O contrato (OpenAPI) sabe: `format: uri`, ou nomes como `partner_api`, `callback`, `webhook`. O desafio de SSRF do alvo de treino crAPI (um campo de texto que nomeia a API de um terceiro) é o caso de prova no laboratório.

## Decisão

Vamos acrescentar ao `scan`, **só com `scan.oast: true`**, uma etapa de SSRF guiado pelo contrato, depois de configurar a política e antes das varreduras do ZAP.

- **Escolha dos campos (domínio, `domain/oast_ssrf.py`).** Partindo dos pedidos que o `probe` provou (`exchanges.json`), vale o campo de consulta ou de primeiro nível do corpo JSON, de texto, que não tenha nome de segredo e: (a) tenha `format` `uri`, `url`, `uri-reference` ou `iri`; ou (b) tenha o nome, partido em palavras (`partner_api`, `webhookTarget`), terminando em `url`, `uri`, `api`, `endpoint` ou `href`, ou contendo `callback` ou `webhook`. A regra é genérica; nada é específico de produto. A **descrição** do OpenAPI não entra: o carregador não a guarda (limite conhecido).
- **Pedido.** Um campo por pedido, com a URL `http://oast-gateway:8090/<token>`. O token (`hd` mais 16 hexadecimais) deriva da semente da execução, da operação, do local e do nome do campo; é único por campo e por operação e imprevisível para o alvo.
- **Teto rígido (domínio).** No máximo **10 pedidos** por execução (`SSRF_MAX_REQUESTS`) e 3 por operação, com rodízio entre operações; o excedente vira `budget_exceeded` em `scan.json`. `DELETE` nunca.
- **Escopo, método e limites.** Cada pedido é um pedido da própria CLI pelo mesmo caminho do `negative` (`NegativeSender` sobre `OperationDispatcher` e `GuardedSender`): `ScopeGuard`, `deny_paths`, métodos, taxa, janela, prazo, trava de emergência, auditoria (prefixo `oast:`) e diário de mutações valem. O planejamento recusa antes o método que o escopo aprovado não permite (`method_not_allowed`); `POST` não exige `negative.allow_writes` porque a permissão é a do escopo da carta e do `scan.oast`. A conta é a que fez o pedido no `probe`.
- **Correlação.** Depois dos pedidos, a CLI consulta o histórico do ZAP (mensagens do tipo OAST, a partir de um ponto marcado antes do primeiro pedido) por até 10 s. Um evento cujo caminho é exatamente o token de um pedido enviado é um retorno correlacionado (o primeiro por token). Evento desconhecido é ignorado. Se o ZAP não responde ao ponto de partida, nada é enviado.
- **Achado.** Cada retorno correlacionado vira um alerta no formato do ZAP (`pluginId` `hdast-oast-ssrf`, CWE 918, severidade e confiança propostas `High`/`High`) anexado a `alerts.raw.json` pela mesma redação dos demais e, daí, um achado comum na operação de origem, com a prova no campo de evidência: identificador do evento, horário (do ZAP), método e caminho do acesso, a ponte pela qual veio (o IP de origem não sobrevive à ponte) e o `User-Agent`. Nenhum valor de campo original nem corpo de resposta é gravado. `scan.json` ganha `ssrf` (planejados, enviados, retornos, eventos vistos, pulos) com padrão nulo.
- **Severidade.** Proposta pela regra; nada a muda depois (a triagem continua sem alterá-la).

## Alternativas consideradas

- **Novo estágio e novo arquivo (`ssrf.json`).** Descartado: exigiria mexer no relatório, no painel e no `run` inteiros; o alerta anexado reaproveita agrupamento, impressão digital, triagem e verificação.
- **Pedir ao ZAP que ataque os campos com a URL.** Descartado: o ZAP não conhece o contrato nem a URL de retorno, e sem a regra de SSRF na imagem não haveria quem a use.
- **Ler as descrições do OpenAPI.** Fica para depois: exige guardar o texto não confiável no modelo.

## Consequências

- O desafio de SSRF do crAPI passa a ser detectável com a carta ligando `attack.oast` e o escopo incluindo a operação com o método dela; o gabarito de `crapi-foco` continua `detectable: false` até uma nota de versão do caso mudar (a rodada cega decide).
- A etapa envia até 10 pedidos a mais por varredura, com URL apontando para um host interno do laboratório; fora do laboratório a ponte não existe e nada volta (sem achado, sem falso positivo).
- O retorno observado prova que o alvo faz a requisição, não o alcance (rede interna, metadados): a severidade proposta é a da classe, e o dono confirma.
- Só leitura do histórico do ZAP e pedidos pelo escopo: nenhum bypass da cerca e nenhuma rota nova.
- Prova no laboratório (2026-11-17, `tests/integration/test_lab_oast_scan.py`, crAPI, escopo mínimo): com a chave, 1 pedido do SSRF guiado, 1 retorno correlacionado e 1 achado de alta severidade proposta no campo de URL da operação de contato com o mecânico (execuções `2026-11-17T15-32-14Z-crapi-7b43` e `2026-11-17T15-45-19Z-crapi-11fa`, `scan` em cerca de 92 s); sem a chave, zero interações no Callback, zero mensagens OAST no ZAP, nenhum achado de OAST (`2026-11-17T15-50-44Z-crapi-0efe`, `scan` em 134 s); nos dois, rota externa recusada (`ENETUNREACH`). As regras do ZAP (Log4Shell, SSTI cega) rodaram sem alerta.
