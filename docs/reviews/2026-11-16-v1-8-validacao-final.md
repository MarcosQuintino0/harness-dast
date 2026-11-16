# Validação independente da V1.8

Data: 2026-11-16. Validador independente GPT 6.1 Terra, esforço medium. Base revisada: `1845e4a` na branch integrada. Esta revisão não substitui a revisão humana exigida em `CONTRIBUTING.md`.

**Decisão: corrigir.** A entrega ainda não demonstra requisitos eliminatórios do plano: a aprovação não é revalidada a cada concessão do proxy e a cobertura executada contém lacunas registradas. A reprodução independente T2 não ocorreu. Não há aceite para avançar como se esses pontos estivessem provados.

## Avaliação por aceite

| Aceite | Avaliação e evidência |
| --- | --- |
| Inventário e contratos | O inventário de campos e camadas e os ADRs 0070 a 0074 propõem envelope, estratégia, compilação, aprovação e migração. O ADR 0072 explicita a limitação da concessão e a prévia simbólica. |
| Domínio, recusa e migração | Há modelos restritos, referências confinadas, recusas e migração para cópia sem alterar aprovação. QA registrou testes de entradas inválidas, alargamento e perfil legado. As escolhas dependem dos resumos de fontes; a divergência ou indisponibilidade do motor fecha a execução. Isso é evidência de teste, não prova de todas as corridas possíveis. |
| CLI e captura | `strategy validate`, `diff`, `migrate`, `capture` e `plan --dry-run` têm contratos e testes. A captura pública foi provada com falsos, conferindo fontes, aprovação e pilha gerenciada e produzindo cópia sem ativá-la. Sua reprodução com ZAP real e escolha preenchida não ocorreu. A prévia seca com escolha preenchida permanece fechada por não consultar o motor. |
| T1 e execução pelo plano | Os testes com falsos comparam itens do plano concreto e política, inclusive conta e operação. A prévia é simbólica e não demonstra catálogo efetivo, pontos completos ou execução real; comparação consigo mesma ou hash não substitui essa evidência. Perfil legado e estratégia neutra têm testes de equivalência, sem extrapolar para cobertura real integral. |
| Revogação e identidade | Aprovação e perfil são conferidos antes de jobs e em polls; isso não prova a recusa de cada concessão do proxy após revogação. A versão observada do ZAP não autentica criptograficamente a instância nem elimina reinício ou troca depois da consulta. |
| Skills e vazamento | Existem testes de contrato e da cópia cega; QA registrou passagem. Não houve rodada cega nesta versão, conforme decisão específica do briefing. Reutilização executável e estudo de reuso pertencem à V1.9, não estão demonstrados aqui. |
| T2 da coordenação | Evidências selecionadas registram SQL Injection nas duas APIs vulneráveis, zero alertas ZAP de alta severidade nos modos seguros e três achados anônimos no VAmPI seguro iguais ao legado. A ausência de novos falsos positivos de outras severidades não foi demonstrada. A matriz registra duas regras 40026 puladas por combinação API/modo. O índice preserva a falha inicial do VAmPI seguro e a repetição selecionada separadamente. Os controles não provam todas as classes nem o negative de escrita do VAmPI. |
| T4 da coordenação | As execuções registram 28 operações concluídas na Clínica e 10 no VAmPI. A matriz registra respectivamente 1.204 e 430 regras concluídas, mais 28 e 10 pulos da regra 40026: cobertura parcial, não sucesso integral. O JUnit registra VAmPI aprovado e Clínica com falha de asserção sobre `notifications=None`; a falha fica preservada e não equivale a suíte aprovada. Não repeti varreduras completas. |

Fontes principais: [plano de execução](../plans/2026-11-16-execucao-v1-8-personalizacao.md), [plano de referência](../plans/2026-11-16-personalization-and-scan-performance.md), [QA inicial](2026-11-16-v1-8-qa.md), [QA de vínculos](2026-11-16-v1-8-qa-complemento.md), [QA do motor](2026-11-16-v1-8-qa-motor-live.md), [QA da captura](2026-11-16-v1-8-qa-captura.md) e medições em `evals/measurements/v1-8/`. A auditoria agregada T4 registra zero concessões fora da lista permitida e zero DELETE ou notificações permitidos; isso não demonstra revalidação da aprovação por concessão.

## Reprodução independente e gates

Escolhi os quatro casos T2 de Clínica e VAmPI nos modos vulnerável e seguro, com métricas separadas. A tentativa de aquisição exclusiva de `C:\harness-dast-artefatos\lab.lock` falhou: a trava pertencia à V1.7 desde 05:01:48 UTC. Em 08:02 UTC continuava presente e havia ultrapassado três horas. Conforme o briefing, encerrei a espera sem alterá-la, iniciar Docker ou executar T2. Assim, não há reprodução independente da captura pública ou dos controles sobre o laboratório.

A coordenação informou Ruff, mypy Windows e Linux, import-linter e Vulture verdes; a suíte ampla teve 9.579 testes aprovados, 4 pulados e 181 desmarcados, em 261,58 s, com `tests/contract/test_docs_links.py` ignorado enquanto o relatório final não existia. Informou ainda 103 testes focados LIVE/captura aprovados. Estes resultados são da coordenação, não uma execução independente minha; o gate final completo sem essa exclusão ainda será executado e associado ao manifesto.

A integração e o rebase sobre a V1.7 continuam pendentes. Para reavaliar o avanço, é necessário corrigir ou demonstrar a garantia de revogação por concessão, resolver ou justificar formalmente as lacunas de cobertura segundo os critérios do plano, reproduzir os controles independentes e concluir os gates e a integração. Prova ausente não conta como sucesso.
