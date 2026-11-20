# Relatório da V1.8 — base da personalização

Data: 2026-11-16. **Entrega parcial. Decisão independente: corrigir; não avançar.** A prova se restringe ao laboratório local; nenhum produto real foi testado. O plano é a [execução V1.8](../plans/2026-11-16-execucao-v1-8-personalizacao.md) e seus critérios vêm do [plano de referência](../plans/2026-11-16-personalization-and-scan-performance.md).

Os limites que impedem o aceite são: revogação por concessão do proxy não implementada/comprovada; prova real da captura pública e do vínculo LIVE ainda pendente; e regra 40026 pulada nas varreduras, uma lacuna de cobertura. A revalidação de aprovação, janela, prazo e parada nos pontos de polling e envio do scan foi testada, mas não comprova o intervalo entre eles. O perfil anterior e a estratégia neutra com `choices: []` continuam utilizáveis.

## Passos do briefing

| Passo | Situação | Evidência e limite |
| --- | --- | --- |
| 1. Inventário e ADRs | Feito | [Inventário](../plans/2026-11-16-v1-8-inventario-contratos.md) conferido contra modelos e fingerprint; ADRs [0070](../../decisoes/0070-envelope-autorizado.md), [0071](../../decisoes/0071-estrategia-versionada.md), [0072](../../decisoes/0072-compilacao-sem-trafego.md), [0073](../../decisoes/0073-aprovacao-estrategia.md), [0074](../../decisoes/0074-migracao-estrategia.md) propostos. |
| 2. Domínio | Feito em código e testes | Modelos, recusas, vínculos tipados e captura atual implementados e testados; teste LIVE real pendente. |
| 3. Aplicação e CLI | Feito em parte | Consultas, diff, migração, captura pública e verificação LIVE implementados; prévia simbólica não é execução nem cobre integralmente corpo ou catálogo ZAP. |
| 4. Execução pelo plano | Feito em parte | Caminho neutro e comparação T1; vínculo LIVE testado com falsos, sem prova de revogação em cada concessão do proxy. Skips impedem afirmar cobertura executada completa. |
| 5. Migração | Feito em código e testes | Cópia explícita neutra, comparação estrutural e aprovação preservada; não ativa estratégia automaticamente nem cria permissão. |
| 6. Skills e avaliação | Feito | Cadastro, [guia](../../usar/personalizacao.md) e referência atualizados; testes de contrato e vazamento na suíte. Carta, caso e régua não receberam permissões novas, pois nenhuma foi criada pela V1.8. Rodada cega dispensada pelo briefing. |
| 7. Prova | Feito em parte | T1 e T2/T4 executados com limites abaixo; teste T4 da Clínica falhou por defeito de asserção, corrigido sem repetir varredura completa. Reprodução independente bloqueada pela reserva V1.7. |
| 8. Validação | Feito em parte | [Validador novo Terra medium](2026-11-16-v1-8-validacao-final.md) decidiu `corrigir`; revisão encerrada, reprodução T2 bloqueada pela trava V1.7 por mais de três horas. |

## Contratos e autorização

Arquivos e testes que sustentam os passos:

| Passos | Implementação | Testes |
| --- | --- | --- |
| 2 | [envelope.py](../../../src/harness_dast/domain/envelope.py), [strategy.py](../../../src/harness_dast/domain/strategy.py), [strategy_basis.py](../../../src/harness_dast/domain/strategy_basis.py) | [envelope](../../../tests/unit/domain/test_envelope.py), [estratégia](../../../tests/unit/domain/test_strategy.py), [vínculos](../../../tests/unit/domain/test_strategy_basis.py) |
| 3 | [casos de uso](../../../src/harness_dast/application/strategy.py), [captura](../../../src/harness_dast/application/strategy_capture.py), [comandos](../../../src/harness_dast/cli/commands/strategy.py), [prévia](../../../src/harness_dast/domain/strategy_preview.py) | [contrato CLI](../../../tests/contract/test_cli_strategy.py), [captura pública](../../../tests/contract/test_cli_strategy_capture.py), [controle](../../../tests/contract/test_cli_strategy_capture_control.py), [LIVE com falsos](../../../tests/unit/application/test_strategy_live_acceptance.py) |
| 4 | [snapshot](../../../src/harness_dast/domain/strategy_plan.py), [scan](../../../src/harness_dast/application/scan.py), [portão](../../../src/harness_dast/application/run_support.py) | [aceitação independente](../../../tests/unit/application/test_strategy_acceptance.py), [plano concreto](../../../tests/unit/domain/test_strategy_plan.py) |
| 5 | [armazenamento e migração](../../../src/harness_dast/adapters/storage/strategy_repository.py) | [repositório](../../../tests/unit/adapters/storage/test_strategy_repository.py) e contrato CLI |
| 6 | [cadastro](../../../plugin/skills/onboard-product/SKILL.md), [referência](../../referencia/strategy.md) | [skills](../../../tests/contract/test_strategy_skills.py), [vazamento](../../../tests/unit/evals/test_strategy_leakage.py) |
| 7 | [prova integrada](../../../tests/integration/test_lab_strategy.py), [suporte](../../../tests/integration/strategy_support.py) | Artefatos por execução e matrizes abaixo |
| 8 | [QA inicial](2026-11-16-v1-8-qa.md), [complemento](2026-11-16-v1-8-qa-complemento.md), [motor LIVE](2026-11-16-v1-8-qa-motor-live.md), [captura pública](2026-11-16-v1-8-qa-captura.md) | Revisão independente final e reprodução identificadas no fechamento |

A carta e o perfil aprovado delimitam o envelope; observação não concede permissão. `strategy.yml` versão 1 referencia `target.yml`, `data-rules.yml` e `flows.yml`. Não duplica segredos, tokens, cookies, respostas integrais, IDs efêmeros nem gabarito. Referências inseguras e dados inválidos são recusados. Uma escolha tipada `coverage/preserve` pode registrar origem, justificativa fechada, validade, estado e `basis` de hashes; a consulta seca não consulta o motor: escolha preenchida fica em revisão e a prévia seca falha fechada. Na execução ativa, a versão observada do ZAP e as fontes atuais são conferidas antes do primeiro pedido ao alvo; vínculo íntegro pode seguir e divergência ou indisponibilidade recusa. Cleanup sem provedor permanece conservador e bloqueia escolha preenchida. `choices: []` preserva o caminho neutro. Reutilização e invalidação seletiva operacionais são V1.9, não demonstradas aqui.

A referência completa está em [strategy.md](../../referencia/strategy.md). Os comandos locais aceitam `--products-dir`:

```text
hdast --json strategy validate <produto>
hdast --json strategy diff <produto>
hdast --json plan <produto> --dry-run
hdast --json strategy migrate <produto> [--output strategy.<nome>.yml]
hdast --json strategy capture <produto> [--output strategy.<nome>.yml]
```

Consulta, diff e prévia não enviam tráfego nem exigem aprovação para inspeção. O diff é estrutural em relação ao legado, não comparação de cobertura executada. A prévia informa `executed: false`, operação, conta, dependências e entradas previstas; `body_entries_complete: false`, `scope_check: template_only` e `pending_probe_and_zap` registram seus limites. `validate` de escolha não vazia devolve `strategy_state: review_required`, `basis_status: engine_unavailable` e `basis_context.engine: null`.

O envelope JSON existente continua com `schema_version: 1`, `ok` e `data` em sucesso, saída 0; entrada inválida, escolha não compilável ou destino recusado usam `CONFIG_ERROR`, saída 2. Falta de aprovação ou violação de escopo usa saída 3; falha de ferramenta externa usa saída 5; pilha ocupada usa `STACK_BUSY`, saída 8. A migração não sobrescreve origem nem ativa automaticamente a cópia `strategy.migrated.yml`; o sucesso apresenta `changes: ["strategy_added"]`, `classification: "automatic"` e `approval_changed: false`. Só pessoa aprova o perfil. Aprovação anterior não concede permissão nova.

A captura pública `strategy capture` exige perfil formal aprovado e vigente, pilha gerenciada ativa do mesmo produto, estado/run/endpoint coerentes e ausência de `KILL`. Sob `stack.lock`, usa endpoint e chave publicados, ignora override de URL, restringe controle a loopback e à porta distinta do alvo local; consulta somente a versão do controle ZAP, sem TargetClient, e revalida perfil, aprovação e documentos depois. Aceita estratégia ausente ou `choices: []`; escolha preenchida anterior é recusada. Gera cópia exclusiva `strategy.captured.yml`, com `coverage/preserve`, origem `observation`, prazo da autorização e base atual. Não ativa nem sobrescreve estratégia, não usa run antigo e não altera aprovação. O sucesso devolve `changes: ["strategy_bound"]`, `classification: "automatic"`, `approval_changed: false` e `activated: false`. Só após revisão e ativação explícita a execução LIVE verifica novamente as fontes e o motor. A captura não exige nova aprovação se o fingerprint aprovado não mudou e não concede poder novo.

A consulta de versão e o scanner usam endpoint configurado, sem prova de identidade criptográfica do processo, nem contra reinício, proxy reverso ou troca após consulta. Os testes independentes com falsos comprovaram vínculo íntegro e zero pedidos ao alvo nos casos negativos, além de 25 testes focados da captura; não substituem a prova T2 pública real ainda pendente. A verificação por concessão do proxy continua pendente.

Exemplo do envelope de migração, com nome ilustrativo:

```json
{"schema_version":1,"ok":true,"data":{"product":"produto","copy":"strategy.migrated.yml","changes":["strategy_added"],"classification":"automatic","approval_changed":false}}
```

## Provas e fontes

O [plano de prova](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/proof-plan.json) foi registrado antes da coleta, com refinamento da escrita CSRF registrado. A matriz completa por trabalho, regras e fontes está em [T4](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/t4-work-matrix.json), [T2](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/t2-selected-sources.json), [regras T2](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/t2-rule-matrix.json) e [recuperação T2](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/t2-recovery-index.json). Estas fontes apontam também para artefatos redigidos fora do repositório. Ausência de prova não conta como sucesso.

| Prova | Resultado observado |
| --- | --- |
| T1 | Testes comparam trabalho previsto e concreto item a item com e sem estratégia neutra, incluindo operações, contas, regras, força, entradas e pré-condições. Hash isolado não é prova de equivalência. |
| T2 inicial | Três passaram e um falhou em 800,35 s. Clínica vulnerável `2026-11-16T04-24-44Z-clinica-piloto-b30e`; VAmPI vulnerável `2026-11-16T04-29-18Z-vampi-a1b1`; Clínica segura `2026-11-16T04-31-11Z-clinica-piloto-e94e`; VAmPI seguro inicial `2026-11-16T04-35-50Z-vampi-4d32` falhou. |
| T2 VAmPI seguro repetido | Um passou em 109,70 s, `2026-11-16T04-40-28Z-vampi-7d00`. Três achados `authz` de acesso anônimo ocorreram também no controle legado sem estratégia; a ausência de rotas públicas declaradas limita interpretação. Comparação em [baseline](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/v18-t2-vampi-secure-anonymous-baseline.json). Não apagar a falha inicial. |
| T2 detecção | SQL positivo nas duas APIs vulneráveis. Zero achados altos nos modos seguros observados não demonstra ausência de falsos positivos baixos ou informativos. Clínica: nove valores negativos rejeitados; VAmPI: zero elegíveis, que não é sucesso de teste negativo. |
| T4 Clínica vulnerável | `2026-11-16T04-42-50Z-clinica-piloto-234e`: 28 operações concluídas; tempo total do `hdast run` de 690,6 s; 1.204 registros de regra concluídos e 28 skips da 40026. Autenticação verificada em 17.954/17.954 mensagens antes da asserção que falhou; verificação CSRF posterior não rodou. |
| T4 VAmPI vulnerável | `2026-11-16T04-55-27Z-vampi-fa08`: 10 operações concluídas; tempo total do `hdast run` de 135,5 s; 430 registros de regra concluídos e 10 skips da 40026. Identidade 4.272/4.272, sem segredos ou Replacer nas verificações; [qualidade](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/v18-t4-vampi-quality.json). |
| Suíte T4 | Um passou e um falhou em 949,87 s. O teste da Clínica consultou `Facts.notifications`, que `collect_facts` não preenche; correção usa endpoints efetivamente coletados. As varreduras completas não foram repetidas após essa correção. Os resultados obtidos antes da falha continuam evidência parcial, não um T4 verde. |
| T4 cerca | Zero pedidos permitidos fora de `allow`, zero `DELETE` permitido; picos de 37 e 30 por segundo, abaixo do limite de 50 nas respectivas execuções. Isso não prova revogação em cada concessão. |

A reprodução independente T2 foi refinada para incluir POST e conferir o par CSRF, preservando as leituras iniciais; a fatia final usa o comando público `strategy capture`, sem montar a base por helper privado. Ela não foi executada: a V1.7 adquiriu a trava às 05:01:48 UTC e a mantinha às 08:02:30 UTC (180,69 minutos). A espera foi encerrada sem alterar a trava, conforme o briefing; [registro](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/lab-wait.json). Não houve T3 A/B, pois a versão não altera ritmo, nem rodada cega, dispensada pelo briefing. T4 ocorreu apenas nos modos vulneráveis e antes da fatia LIVE/captura.

Somente medições revisadas foram versionadas. Logs, estado temporário e credenciais efêmeras do suporte permanecem fora do repositório, em `C:\harness-dast-artefatos\v1-8\`; essa pasta inteira não é um pacote sanitizado para publicação. A pilha da coordenação foi derrubada e `docker compose ls -a` estava vazio antes de liberar sua própria trava; a reserva posterior da V1.7 permaneceu intacta.

## Qualidade por API e modo

As seis dimensões da seção 3 são eliminatórias. A tabela informa apenas o que as provas locais acima sustentam; “parcial” não equivale a aceite.

| Dimensão | Clínica vulnerável | Clínica segura | VAmPI vulnerável | VAmPI seguro |
| --- | --- | --- | --- | --- |
| Autorização | Parcial: cerca T4 sem tráfego fora do allow; concessão/revogação pendente | Parcial: T2 local; concessão pendente | Parcial: cerca T4 sem tráfego fora do allow; concessão pendente | Parcial: T2 local; concessão pendente |
| Cobertura planejada | T1 neutro item a item; não demonstra execução | T1 neutro; T2 direcionado | T1 neutro item a item; não demonstra execução | T1 neutro; T2 direcionado |
| Cobertura executada | 28 concluídas, 40026 pulada; teste T4 falhou depois do scan | Duas entradas T2; sem T4 seguro | 10 concluídas, 40026 pulada | Duas entradas T2 repetidas; sem T4 seguro |
| Detecção | Controle SQL positivo | Nove valores negativos rejeitados; não cobre todas as classes | Controle SQL positivo | Zero casos negativos elegíveis; sem prova positiva desse controle |
| Falsos positivos | Não aplicável como prova de modo seguro | Zero altos observados; baixos/informativos não excluídos | Não aplicável como prova de modo seguro | Zero altos observados; três anônimos também no legado; baixos/informativos não excluídos |
| Estado e identidade | 17.954/17.954 mensagens autenticadas antes da falha; CSRF posterior pendente | T2; reprodução de escrita CSRF pendente | 4.272/4.272, sem segredos/Replacer na verificação | T2 direcionado; não substitui T4 de identidade |

## Integração, gates e decisões

A suíte ampla após a última mudança de código registrou **9.579 passados, 4 pulados e 181 desmarcados em 261,58 s**, ignorando somente `tests/contract/test_docs_links.py` enquanto este relatório não existia. Os pulos foram três testes sem permissão de link simbólico e um de modo POSIX. Ruff, mypy Windows e Linux, import-linter e Vulture também passaram. Os oito gates finais, incluindo pytest sem exclusão adicional e gitleaks, têm comandos, saídas, tempos e SHA da fonte no [manifesto de fechamento](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/gates.json); os logs e JUnit estão em `C:\harness-dast-artefatos\v1-8\gates\`. O manifesto é a referência para o resultado final. A configuração de gitleaks não foi afrouxada.

A branch de integração é `feat/v1-8-personalizacao`; código estabilizado em `16764d1`, com documentação e pré-registro complementados em `1845e4a`, e parecer integrado em `c5f435b`. Após `git fetch origin`, às 08:02 UTC, `origin/develop` continuava em `5f4b321`, sem a V1.7. O rebase sobre a V1.7 não foi feito e continua pendente para a coordenação geral após sua entrada. Não houve merge. O PR é entregue em rascunho; o CI remoto é conferido na entrega, sem presumir resultado a partir dos gates locais.

Decisões conservadoras: preservar perfil sem estratégia; não mudar cobertura ou ritmo; recusar escolha com motor desconhecido ou divergente; criar cópias de migração e captura sem ativação; não alegar que prévia ou hash provam cobertura. A assinatura de aprovação vigente permanece separada da base de estratégia. A regra 40026 pulada e a falha original do teste são lacunas, não êxitos. A prova foi feita apenas no laboratório, sem produto real.

A coordenação ficou nesta sessão Codex. Domínio (`/root/domain`), aplicação (`/root/app`), documentação (`/root/docs`) e QA independente (`/root/qa`) usaram GPT 6.1 Terra high, cada qual em sua worktree. A validação (`/root/validator`) usou GPT 6.1 Terra medium novo, sem implementação. Os commits foram integrados por cherry-pick; as cinco worktrees e branches auxiliares foram removidas após verificar limpeza e equivalência dos commits. Revisão por agente não substitui a revisão humana exigida em áreas críticas.

**Decisão pendente para o dono:** após a integração da V1.7, autorizar a implementação do hook de revogação por concessão no proxy e refazer os testes necessários, ou manter o PR explicitamente parcial sem declarar aceite? Recomenda-se implementar e provar o hook e reproduzir T2 quando o laboratório estiver disponível antes de considerar a V1.8 concluída. A necessidade dessa decisão vem da seção 1 do briefing, que reserva `adapters/scope_proxy/` à V1.7; o arquivo não foi alterado nesta execução.
