# Relatório da versão 1.5.5

Data: 2026-11-16; execução iniciada em 2026-11-15. Branch: `feat/v1-5-5-achar-mais`. [Plano](../plans/2026-11-15-plano-v1-5-5-achar-mais.md). ADRs [0061](../../decisoes/0061-espera-de-execucao.md), [0062](../../decisoes/0062-leitura-atribuicao-massa-conta-escritora.md), [0063](../../decisoes/0063-verificacao-cors.md), [0064](../../decisoes/0064-par-automatico-entre-contas.md) e [0065](../../decisoes/0065-triagem-de-todas-as-origens.md): **Propostos**.

Implementação entregue com QA independente, gates verdes e oito cenários aprovados nas duas APIs locais. **Aceites B, D e F parciais no VAmPI; crAPI não executado.** Nenhuma prova contra produto real. PR destinado à `develop`, sem merge pelo Codex. Os caminhos de domínio e aplicação abaixo pertencem a `src/harness_dast/`.

## Entrega e aceite

| Item | Situação e arquivos principais | Testes e prova |
| --- | --- | --- |
| A. Esperar | **Feito.** `application/wait.py`, `domain/wait.py`, `adapters/reporting/wait_*.py`, `cli/commands/wait.py`, integração ao `run` e skills `run-scan`/`test-product`. | Contrato `test_cli_wait.py`: terminada, em andamento, parada, ausente e dados inválidos; QA de término concorrente e identidade da trava. Não toca API. Economia de tokens ainda não medida. |
| B. Massa | **Feito em parte.** `domain/authz_plan_mass.py` permite repetir com a escritora um GET provado por outra conta, do mesmo modelo e alvo concreto, inclusive no POST. | Dois contratos sintéticos; Clínica com GET e PUT provados por contas diferentes: um achado no vulnerável, nenhum no seguro. VAmPI executou oito candidatos por modo sem achado: **V4 não comprovada**, sem leitura compatível para essa conferência. |
| C. CORS | **Feito.** `domain/cors.py`, `application/cors_check.py`, cabeçalhos no cliente HTTP, `AuthzConfig` e integração ao `authz`. | Classes sintéticas, duplicados, credenciais, dedupe e teto físico de pedidos. Laboratório: um GET por cenário; um alto na Clínica vulnerável, zero na segura e nos dois modos do VAmPI. |
| D. Par novo | **Feito em parte.** `authz_created_pair.py`, `authz_plan_created_pair.py`, `authz_flow_bindings.py`, contador do `RequestBuilder` e `exchanges.json`. | Dois contratos e QA com contas/papel genéricos, vínculo e inteiro único 1..100. Clínica: POST 201 pela dona, GET dona 200, GET par 200 no vulnerável e 403 no seguro; médicos pulados. VAmPI: POST 200 é `create_unconfirmed`, sem comparação desse recurso. Sua BOLA observada veio do GET já provado pelo probe. |
| E. Triagem | **Feito.** Skills `triage-findings`/`test-product` conferem todos os altos; `domain/report_build.py` reconhece todas as origens ao calcular `triage_orphans`. | Contratos das skills e três testes de origem, preservando órfãos reais e severidades. Sem agente cego nesta entrega. Notas adicionais continuam em `triage.json`, sem apresentação junto a cada achado dessas seções. |
| F. Avaliação | **Feito em parte.** Casos Clínica/VAmPI, histórico `vampi-estrito`, `runner/metrics_stages.py` e `test_eval_case_permissions_and_grading.py`. | H3 reconhece CORS; V3 tem match de BOLA comprovada; V4 continua `detectable: false`. Prepare sem vazamento e approve fiel à carta conferidos. crAPI mantém caso e permissões anteriores: faltam pilha externa, semeadura e prova para alterar sua régua. |

## Contratos e limites

`hdast wait --product PRODUTO --timeout 600` captura a tomada ativa da trava; a retomada usa `--lock <lock_id>`. `--run ID` atende uma execução conhecida. A consulta não toca o alvo: saída 0 significa observação, inclusive timeout; o código do run está em `data.exit_code`. `finished` exige `run.json`; `running`, `stopped` e `unknown` não inventam resultado final. Se o processo termina antes da primeira captura, sua saída continua sendo a fonte de resultado. As skills usam esperas de minutos, sem polling de arquivo de progresso.

CORS fica no `authz`: padrão de cinco GETs, `cors_max_requests` entre 0 e 10 e uma tentativa por operação. Reflexão com credenciais é alta; curinga sem credenciais é baixa. CWE-942, API8:2023, uma ocorrência por classe de política/produto. Não cobre preflight, outras origens ou todas as operações; não comprova sessão de navegador nem sensibilidade do conteúdo.

O par exige escrita da carta, duas contas do mesmo papel não compartilhado, POST e GET irmão provados, referências válidas para quem cria, HTTP 201, sucesso lógico e identificador devolvido não conhecido. Não adivinha identificador. `flows.yml` conserva somente os campos consumidores declarados; os demais são gerados. `next_unique_counter`, opcional e estrito em `exchanges.json`, continua o contador do probe e avança antes de enviar. Logs antigos sem ele não habilitam criação automática. Massa e par compartilham 400 escritas, uma tentativa por escrita e reserva para restauração; 401/429 na massa ficam inconclusivos.

Motivos novos: `new_data_unavailable`, `flow_binding_unavailable`, `create_failed`, `create_unconfirmed`, `created_target_preexisting`, `created_identifier_unavailable`, `created_owner_read_failed` e `created_read_different`. Somam-se aos motivos existentes de autorização, papel compartilhado, escopo, conta e orçamento. Nenhum significa segurança. HTTP 200 de criação, falta de identificador, validações de negócio e referências de outra conta limitam cobertura. A novidade depende da semântica 201 do servidor.

Massa continua limitada a corpos JSON, campos e leitores observáveis; restauração é de melhor esforço. Nenhum DELETE é enviado. `created_resources` é o contador da CLI, não uma contagem independente do banco; POSTs aceitos podem deixar dados para reset/limpeza humana. A continuidade do contador preserva a etiqueta de limpeza da execução.

## Qualidade e evidências

[Medições e manifesto públicos](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/results/2026-11-15-v1-5-5-lab/README.md). Saídas externas: `C:\harness-dast-artefatos\v1.5.5\`. A suíte inteira foi repetida após a última alteração de código e testes, em `b8884c1`, sem filtro adicional. Na retomada após reinício da máquina foram conferidos os registros e repetidos somente os gates rápidos exigidos pela documentação final.

| Gate | Resultado |
| --- | --- |
| Ruff | Lint e formatação verdes; 1.046 arquivos |
| Mypy Windows e Linux | 852 arquivos, ambos verdes |
| Import-linter | 6 contratos mantidos |
| Vulture | Verde |
| Pytest completo com cobertura | **9.424 passaram, 4 pulados, 175 desmarcados; 507,97 s** |
| Cobertura de ramos | Domínio 98,4%; aplicação 96,8% |
| Cobertura do diff | 90% exibidos; 450 de 495 linhas cobertas, piso 90% aprovado |
| Segurança | Gitleaks preservado; auditoria das versões do lock sem vulnerabilidades conhecidas |
| Laboratório | 8 cenários aprovados em dois blocos; bloco final massa/par: 4 casos, 591,49 s |

As auditorias tiveram **422 requisições liberadas, zero fora dos caminhos/métodos das cartas e nenhum DELETE**; isso não mede taxa instantânea. As fixtures encerraram as pilhas e Compose retornou `[]`. Chaves do ZAP aleatórias no processo; só o suporte de integração gravou aprovações descartáveis. Não se executou `profile approve`, `secret set/delete` ou limpeza humana, nem se leu `.env`.

As tentativas estão preservadas: primeiro houve junção durante uso da CLI; depois, D revelou contador acima da capacidade e perda de referências, corrigidos; a terceira falha era referência de outro dono no perfil de teste, corrigida no perfil descartável sem alterar o alvo. A suíte inicial teve seis falhas: regressão do leitor da escrita horizontal, tradução de `wait` ausente e quatro expectativas/fixtures desatualizadas. Todas foram tratadas e a suíte completa passou depois. Os logs dessas tentativas estão separados das provas aprovadas.

## QA, revisão e próximas rodadas

QA independente: [inicial](qa-v1.5.5.md), [encadeamento](qa-v1.5.5-encadeamento.md) e [classificação da suíte](qa-v1.5.5-suite.md). Reproduziu leitor de objeto errado, objeto antigo tratado como novo e retentativas acima dos tetos de escrita/CORS; regressões passaram após correção. O QA complementar teve 22 testes dirigidos aprovados, com papel e aliases genéricos. Rodadas sobrepostas não foram somadas como testes únicos.

Cinco subagentes GPT 6.1 Terra usaram worktrees próprias: espera/triagem, autorização, CORS e QA independente em **high**; documentação em **medium**. O coordenador integrou serialmente e conduziu laboratório e gates. Não houve recusa por regra do modelo; os limites acima são técnicos e de prova. O checkout `C:\harness-dast` não foi utilizado.

O Claude Code deve revisar os cinco ADRs como Propostos, tetos por tentativa, continuidade do contador, vínculo declarativo do dono e aceites parciais B/D/F. Módulos críticos exigem a revisão humana de `CONTRIBUTING.md`; conferir os checks do PR antes de juntar. A orquestração mantém funções/arquivos legados maiores que os limites preferenciais; os fluxos novos foram separados em módulos próprios para preservar as fronteiras.

Sem varredura completa, rodada cega ou crAPI nesta entrega. O dono poderá pedir novas rodadas pelo [protocolo](../../../evals/protocolo-da-rodada-cega.md), em **Clínica Piloto e VAmPI**, com fonte limpa, versão/commit anotados, semente nova, cópias novas, transcript completo e só a aprovação prevista como intervenção. Usar os casos atuais; `vampi-estrito` preserva o histórico. Autonomia e economia de tokens ainda serão medidas.
