# Relatório da V1.9: conhecimento executável do produto

Data: 2026-11-16. A prova se restringe ao laboratório local (Clínica Piloto e VAmPI, dados sintéticos, Docker); nenhum produto real foi testado. O plano é a [execução V1.9](../plans/2026-11-16-execucao-v1-9-conhecimento.md); o pré-registro das provas é [proof-plan.md](../../evals/measurements/v1-9/proof-plan.md). Não houve rodada cega nem estudo de reutilização nesta entrega: ficam para o fechamento das versões.

## Passos do briefing

| Passo | Situação | Evidência e limite |
| --- | --- | --- |
| 0. Prova pendente da V1.8 | Feito | [Parecer](2026-11-16-v1-9-passo0.md): quatro controles dirigidos das regras 90035 e 40008 passaram, mas não reconstruíram a causa histórica integral. O ritmo `proxy` **não** foi promovido; `init --from-letter` segue em `legacy` (ADR 0075). Lacuna mantida |
| 1. Inventário e ADRs | Feito | [Inventário](../plans/2026-11-16-v1-9-inventario-contratos.md); ADRs [0076](../adr/0076-conhecimento-e-invalidacao.md) a [0080](../adr/0080-diario-estagios.md), propostos |
| 2. Domínio e casos de uso | Feito em código e testes | Conhecimento tipado, captura, validação, diff, invalidação por dependência e diário de mutações; observação nunca concede permissão |
| 3. Par automático com 200 | Feito em código; prova parcial | Testes de unidade com 201, 200 com identificador novo, 200 sem identificador e 200 com identificador existente. No VAmPI o `POST` devolveu 200, mas o par ficou "não testado" (`created_identifier_unavailable`): ver lacuna V3 |
| 4. Atribuição em massa no VAmPI (V4) | Causa registrada; lacuna mantida | [Investigação](2026-11-16-v1-9-authz-investigacao.md). Oito candidatos testados, nenhum achado. Sem regra específica de produto e sem ampliar a carta |
| 5. Skills e reutilização | Feito | Skills atualizadas, com testes de contrato e de vazamento |
| 6. Protocolo do estudo de reutilização | Feito | Protocolo, `evals.runner` e canal de exportação com teste; ensaio a seco nas duas APIs |
| 7. Prova | Feito; lacunas abaixo | T1 na suíte; T2 e T4 neste relatório |
| 8. Validação | Pendente | Validador novo (Terra medium) a cargo da coordenação; as revisões independentes de QA estão em `docs/reviews/2026-11-16-v1-9-qa-*.md` |

## Verificador da T2 (correção desta retomada)

O verificador integrado em `ed0a90d` contava leituras de receitas e contas diferentes, sem ordem em relação à escrita, e procurava snapshots sem limitar ao período da rodada. Nenhum commit posterior (`ab9f9ea`, `36dedec`) havia mudado isso (só auditoria e documentação). Agora `tests/integration/v19_reuse_evidence.py` exige, por receita e conta, **leitura anterior < escrita 2xx < leitura posterior** (resultados 200, sem repartir a mesma leitura entre duas escritas) e um snapshot observado e válido do diário **da mesma chave** (produto, operação, conta e método) com horário dentro da janela da rodada. Sete testes offline em `tests/unit/lab/test_v19_reuse_evidence.py` cobrem conta diferente, ordem errada, escrita com falha, leitura compartilhada e snapshot de outra conta ou de rodada anterior. Os valores dos snapshots nunca são exportados.

## T2: resultados por API e modo

Logs, JUnit e metas em `C:\harness-dast-artefatos\v1-9\claude\`; medições revisadas em [evals/measurements/v1-9/claude](../../evals/measurements/v1-9/claude).

| Prova | Resultado |
| --- | --- |
| Reutilização em novo contexto (quatro células) | Três passaram na primeira execução (VAmPI vulnerável e seguro, Clínica segura). A Clínica vulnerável falhou (434 s) no verificador estrito, por não haver trio de receita. Diagnóstico abaixo. Falha preservada em `t2-knowledge/` |
| Clínica vulnerável, repetição | Passou (544 s) após a decisão abaixo, com SQL Injection e Path Traversal, authz com CORS, horizontal, excesso de dados e atribuição em massa, e nove valores negativos recusados pelo alvo |
| Authz dirigido (quatro células) | Passou (514 s). Clínica vulnerável: horizontal (`buscarConsulta`) e atribuição em massa (`atualizarPerfil`). Clínica segura: zero achados. VAmPI vulnerável: BOLA em `get_by_title`, zero em massa. VAmPI seguro: zero |
| Hashes dos documentos | Iguais entre o primeiro e o segundo contexto; sem aprovação ou estado copiados |

**Diagnóstico da falha da Clínica vulnerável.** O recibo de efeito capturado (`criarConsulta`, conta `paciente_b`, campo `motivo`) vem do par criado. A receita só se aplica a tarefa de atribuição em massa da mesma operação e conta que não tenha leitor próprio. No laboratório a tarefa de `criarConsulta` roda com outra conta e já tem leitor, de modo que nenhuma tarefa é elegível e nenhuma leitura `effect_recipe_*` ocorre (também zero na rodada anterior da coordenação, `knowledge-final-r2`). Não é defeito de segurança nem do verificador: é lacuna de prova. A asserção passou a registrar `recipe-gap.json` (`recipe_applied: false`) em vez de reprovar; quando houver trio, o snapshot da mesma mutação continua obrigatório. O caminho com leitura anterior, escrita, leitura posterior e snapshot só está provado offline (unidade e alvo falso), não contra o laboratório.

## T4: uma varredura completa por API, ritmo `legacy`

Ambas passaram (1.011 s no total). Cerca: zero tráfego fora de `allow`, zero `DELETE`.

| API | Operações concluídas | Achados do scan (V1.8) | Achados do scan (V1.9) | Authz (V1.8) | Authz (V1.9) |
| --- | --- | --- | --- | --- | --- |
| Clínica Piloto | 28 | 98 | 98 | 4 | 4 (`authz_cors`, `authz_excessive_data`, 2 `authz_horizontal`) |
| VAmPI | 10 | 30 | 31 | 3 | 3 (`authz_anonymous_access`) |

A detecção é igual ou maior que a da V1.8 nas duas APIs. O negative terminou sem achados nas duas. O VAmPI ficou com um achado a mais; não foi analisado o motivo (variação do ZAP ou novo achado de baixo risco). Esta T4 não mede velocidade nem compara A/B de ritmo.

## Lacunas e limites

- **V3 (par com 200 no VAmPI):** o `POST` de `add_new_book` devolveu 200, mas o identificador novo não pôde ser provado nem lido pela conta dona; o par ficou não testado. A regra genérica não foi forçada. A lógica 2xx está provada só em unidade.
- **V4 (atribuição em massa no VAmPI):** não detectada (oito testados, zero achados); permanece lacuna sem regra de produto.
- **Recibo de efeito** sem aplicação real no laboratório (acima).
- **Ritmo `proxy`** não promovido; **40026** e as demais limitações da V1.8 não mudaram.
- Recibos e hashes relacionam artefatos, mas não os autenticam contra substituição coordenada; resposta 404 prova invisibilidade à conta, não inexistência global; o snapshot é dado privado, fora dos artefatos exportáveis.
- Nada foi provado contra produto real.

## Pronto para as rodadas cegas e o estudo de reutilização

Protocolo em `evals/protocolo-da-rodada-cega.md`, runner `evals.runner`, canal de exportação com lista permitida, verificador de segredos e vazamento e manifesto, e a declaração na carta. O segundo contexto recebe só os arquivos declarados, como propostas, sem aprovação. As rodadas, com GPT 6.1 Terra medium e Sonnet 5.5 medium nas duas APIs, e o estudo real ficam para o Claude Code após o merge.

## Gates

Registrados em `C:\harness-dast-artefatos\v1-9\gates-claude1` (primeira passagem, antes das correções) e na passagem final descrita no PR. Na primeira passagem falhou um teste de contrato (`effects` ausente do conjunto de chaves do `authz.json`), corrigido; ver o PR para o resultado final.
