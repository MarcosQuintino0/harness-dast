# Validação independente de fechamento da V1.8

Data: 2026-11-16. **Decisão: continuar**, condicionada aos gates finais da coordenação e ao relatório complementar de fechamento. Esta é uma revisão técnica independente; não substitui a revisão humana prevista em CONTRIBUTING. A promoção do ritmo proxy foi recusada pelo experimento, conforme ADR 0075, e não é condição para entregar a base da V1.8.

## Revisão e escopo

A reprodução funcional usou `2746d006ac8f90ec4ee665f83cac6e42179bb742`, após rebase sobre a V1.7 em `a267ae2`. A revisão documental incorporou `d0c2b91` (inclui `8528f86` e `535851c`); os commits intermediários adicionam documentação e dados de comparação, sem mudança funcional. Foram examinados contrato, plano de referência, ADRs 0070–0075, QA e pareceres anteriores, T1, implementação da fila e portão, montagem e build da imagem, T4 e controles seguros. As revisões anteriores permanecem imutáveis. As referências correntes foram corrigidas para refletir a revalidação por concessão; o relatório complementar e os resultados dos gates serão produzidos pela coordenação após este parecer.

A pilha gerenciada vincula aprovação e perfil por hash e assinatura, verifica as fontes, autorização, janela, prazo e parada na concessão, e falha fechada. Os diretórios são montados em leitura e a imagem principal é reconstruída na subida. Trocar administrativamente a raiz do mount pode não ser observado; concessões já encaminhadas não são canceladas. A versão do motor observada não autentica sua instância nem elimina troca após a consulta. A prévia seca é simbólica, não prova alcance ou cobertura executada.

## Prova independente

Com trava exclusiva `v1.8-validador2` e laboratório local, executei `uv run pytest -m integration tests/integration/test_strategy_proxy_controls.py tests/integration/test_scope_revocation.py` com destinos isolados. **5/5 passaram em 880,93 s**: captura pública e estratégia preenchida, seguida de controles T2, nas duas APIs e nos dois modos; e revogação real no VAmPI. Nesta última, a auditoria registrou `allow` seguido de `deny/approval_changed` 1,047 s após a remoção da aprovação temporária, sem `allow` posterior; o processo terminou com saída 4. As provas usam fixtures sintéticas e o suporte existente; não foi executado comando humano de aprovação nem manipulação de segredos.

As evidências sanitizadas estão em `C:\harness-dast-artefatos\v1-8\closure\validator2-measurements`, com JUnit `validator2-junit-run.xml` e log `validator2-pytest-run.log` na pasta `closure`. Uma primeira invocação sem `-m integration` selecionou zero testes (5 deselected, saída 5); não conta como prova e foi preservada em `validator2-pytest.log` e `validator2-junit.xml`. Após a execução, o suporte desmontou as pilhas, `docker compose ls -a` estava vazio e somente a minha trava foi removida.

Também passaram **34/34 testes offline** de concessão, compatibilidade de aprovação, estratégia e plano, registrados em `closure/validator2-offline.xml`. O QA anterior documenta os casos controlados de alteração, fila, janela, prazo e parada; não se deve inferir que todos foram reproduzidos com Docker nesta rodada. Os controles seguros adicionais da coordenação e suas falhas anteriores estão preservados em `closure/other-controls` e no manifesto de proveniência correspondente.

## Previsão e qualidade

A previsão foi congelada em `09ee231` antes das novas T4 B, usando T3 e T4 A da V1.7. Os erros de ganho foram **15,596637 pontos percentuais na Clínica** e **22,432817 no VAmPI**, ambos superiores ao teto de 10. Portanto `init --from-letter` permanece `legacy`; o modelo e perfis existentes não são migrados, inclusive perfis explicitamente `proxy`. É resultado negativo do experimento de promoção, não defeito da entrega base.

As matrizes registram operações, regras não DOM, pedidos, alertas e achados disponíveis equivalentes nas duas comparações. A regra 40026 permaneceu pulada como na referência, exclusão pré-existente; não se ligou navegador nem se demonstrou cobertura DOM XSS. Pontos de injeção e valores não estão integralmente disponíveis. Presença de `Authorization` não prova validade ou identidade efetiva por pedido, e diferenças de frequência de login não comprovam troca de identidade. A comparação de achados sanitizados tampouco prova identidade integral de evidência ou causa. Não extrapolar as provas para produto real.

Nenhum defeito funcional aberto foi demonstrado nesta revisão. A decisão de continuar não declara os gates completos verdes: a coordenação deve executá-los sobre o HEAD integrado, registrar resultados em `closure/gates-final.json`, produzir o relatório complementar e resolver qualquer falha antes de retirar o PR de rascunho.
