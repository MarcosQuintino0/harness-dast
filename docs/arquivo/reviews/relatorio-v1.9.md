# Relatório da V1.9: conhecimento executável do produto

Data: 2026-11-16. A prova se restringe ao laboratório local (Clínica Piloto e VAmPI, dados sintéticos, Docker); nenhum produto real foi testado. O plano é a [execução V1.9](../plans/2026-11-16-execucao-v1-9-conhecimento.md); o pré-registro das provas é [proof-plan.md](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-9/proof-plan.md). Não houve rodada cega nem estudo de reutilização nesta entrega: ficam para o fechamento das versões.

## Passos do briefing

| Passo | Situação | Evidência e limite |
| --- | --- | --- |
| 0. Prova pendente da V1.8 | Feito | [Parecer](2026-11-16-v1-9-passo0.md): quatro controles dirigidos das regras 90035 e 40008 passaram, mas não reconstruíram a causa histórica integral. O ritmo `proxy` **não** foi promovido; `init --from-letter` segue em `legacy` (ADR 0075). Lacuna mantida |
| 1. Inventário e ADRs | Feito | [Inventário](../plans/2026-11-16-v1-9-inventario-contratos.md); ADRs [0076](../../decisoes/0076-conhecimento-e-invalidacao.md) a [0080](../../decisoes/0080-diario-estagios.md), propostos |
| 2. Domínio e casos de uso | Feito em código e testes | Conhecimento tipado, captura, validação, diff, invalidação por dependência e diário de mutações; observação nunca concede permissão |
| 3. Par automático com 200 | Feito em código; prova parcial | Testes de unidade com 201, 200 com identificador novo, 200 sem identificador e 200 com identificador existente. No VAmPI o `POST` devolveu 200, mas o par ficou "não testado" (`created_identifier_unavailable`): ver lacuna V3 |
| 4. Atribuição em massa no VAmPI (V4) | Causa registrada; lacuna mantida | [Investigação](2026-11-16-v1-9-authz-investigacao.md). Oito candidatos testados, nenhum achado. Sem regra específica de produto e sem ampliar a carta |
| 5. Skills e reutilização | Feito | Skills atualizadas, com testes de contrato e de vazamento |
| 6. Protocolo do estudo de reutilização | Feito | Protocolo, `evals.runner` e canal de exportação com teste; ensaio a seco nas duas APIs |
| 7. Prova | Feito; lacunas abaixo | T1 na suíte; T2 e T4 neste relatório |
| 8. Validação | Pendente | Validador novo (Terra medium) a cargo da coordenação; as revisões independentes de QA estão em `docs/arquivo/reviews/2026-11-16-v1-9-qa-*.md` |

## Verificador da T2 (correção desta retomada)

O verificador integrado em `ed0a90d` contava leituras de receitas e contas diferentes, sem ordem em relação à escrita, e procurava snapshots sem limitar ao período da rodada. Nenhum commit posterior (`ab9f9ea`, `36dedec`) havia mudado isso (só auditoria e documentação). Agora `tests/integration/reuse_evidence_support.py` exige, por receita e conta, **leitura anterior < escrita 2xx < leitura posterior** (resultados 200, sem repartir a mesma leitura entre duas escritas) e um snapshot observado e válido do diário **da mesma chave** (produto, operação, conta e método) com horário dentro da janela da rodada. Sete testes offline em `tests/unit/lab/test_reuse_evidence.py` cobrem conta diferente, ordem errada, escrita com falha, leitura compartilhada e snapshot de outra conta ou de rodada anterior. Os valores dos snapshots nunca são exportados.

## T2: resultados por API e modo

Logs, JUnit e metas em `C:\harness-dast-artefatos\v1-9\claude\`; medições revisadas em [evals/measurements/v1-9/claude](https://github.com/MarcosQuintino0/harness-dast/tree/fd611a9/evals/measurements/v1-9/claude).

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

## Correções da validação

O validador independente decidiu `corrigir`. Para cada defeito escrevi antes o teste que o reproduz e confirmei a falha; medições em [evals/measurements/v1-9/claude/fix](https://github.com/MarcosQuintino0/harness-dast/tree/fd611a9/evals/measurements/v1-9/claude/fix).

| # | Achado | Correção e teste |
| --- | --- | --- |
| 1 | Pendência sem envio: a recusa do portão (`WindowClosed`/`DeadlineReached`) depois do `begin` do diário deixava a reserva para sempre no `authz` e no `negative` | Com uma única tentativa, a recusa vem antes de qualquer byte da mutação; a reserva é fechada como `failed` e o erro segue. Erro durante ou depois do envio continua desconhecido e bloqueia. Mensagens separadas no diário: "Já existe mutação com resultado desconhecido para esta operação e conta" (com o caminho e a ação humana) e erro de E/S. Testes: `test_journal_refusal.py` (falharam antes) e `test_knowledge_journal.py`. Reconciliação em [knowledge.md](../../referencia/knowledge.md) e [problemas-comuns.md](../../usar/problemas-comuns.md) |
| 2 | `KnowledgeProfiles.load` exigia o motor sem necessidade | `cleanup` ignora o conhecimento (`checked_profiles(..., with_knowledge=False)`); nos `--dry-run`, só entrada `validated` consumível exige o motor, e a só proposta é ignorada. `reusable` passou a exigir ao menos uma entrada validada. Testes em `test_knowledge.py` |
| 3 | `recipe-gap.json` aceitava qualquer ausência de trio | A lacuna só vale com zero linhas de auditoria `authz:effect_recipe_*`; qualquer leitura de receita sem trio reprova (`recipe_absence`). Testes offline dos dois casos |
| 4 | Snapshot com folga de 5 s casava com a restauração | Exige `escrita <= instante do snapshot <= leitura posterior`, sem folga. O instante é o `mtime` do arquivo arquivado, gravado depois da resposta da escrita e antes da leitura posterior; não foi preciso gravar o `begin` no diário. Testes com snapshot da restauração depois da leitura posterior e snapshot anterior à escrita |
| 5 | Recibo codificava vulnerabilidade | A atribuição em massa com efeito comprovado (`PUT` e `POST`) deixa de gerar recibo; só o marcador do par criado gera. ADR 0078 e testes ajustados (`result.effects == ()`). **Consequência para a receita:** os recibos reais passam a vir só do par criado, e a receita só se aplica a tarefa de atribuição em massa da mesma operação e conta sem leitor, o que quase nunca ocorre. O mecanismo segue provado só offline (receita fornecida por carregador); no laboratório a lacuna `never_attempted` continua. Mantive a regra conservadora |
| 6 | Proveniência no pacote exportado contradizia o protocolo | O modelo exige `provenance`; protocolo e ADR 0079 agora dizem que o pacote leva `run_id` e hashes do manifesto, do probe e do authz, que não são segredo, e nenhum outro arquivo leva o identificador. Teste em `tests/unit/evals/test_reuse.py` fixa o conteúdo |
| 7 | Captura sem `--run` emitia `source: owner` e `validated` | Sem origem real, todas as entradas saem `proposed` com origem `contract`. Teste em `test_knowledge.py` |
| 8 | Documentação | `knowledge.md` atualizado (a repetição da T2 passou); `authz_created_pair.py` (479 linhas) ganhou justificativa no docstring do módulo em vez de divisão |
| 9 | Acentuação corrompida em documentos da develop | Corrigida só a codificação em `evals/protocolo-da-rodada-cega.md`, `evals/README.md`, ADR 0062 e `relatorio-v1.7.md` (commit `docs: corrige acentuação corrompida`). `qa-v1.5.5.md` intocado. Os demais `?` encontrados nos `.md` são URLs e consultas. Dados históricos em `evals/results` (JSON e transcrições) não foram tocados |

### Prova depois das correções

- **Gates** (`run-gates.ps1`, `gates-claude3`): ruff, format, mypy Windows e Linux, lint-imports, vulture, pytest com pisos de cobertura, diff-cover e gitleaks verdes.
- **T2 de authz**, quatro células, 533 s: passou, com os mesmos achados (Clínica vulnerável: horizontal e atribuição em massa; VAmPI vulnerável: horizontal; modos seguros: zero).
- **T2 de reutilização, Clínica vulnerável**, com o verificador novo, 546 s: passou, com `recipe-gap.json` = `never_attempted`. O trio e o snapshot só estão provados offline.
- A T4 não foi repetida. O Compose ficou vazio e a trava foi removida.
