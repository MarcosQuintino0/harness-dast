# Fechamento da V1.8: personalização e revalidação por concessão

Data: 2026-11-16. Este documento complementa o [relatório inicial](relatorio-v1.8.md) e os pareceres anteriores, que permanecem imutáveis. O dono autorizou a V1.8 a assumir a revalidação no proxy após a V1.7. O [validador novo Terra medium](2026-11-16-v1-8-validacao-fechamento.md) decidiu **continuar**, condicionado aos gates finais e a este relatório. A base da versão está concluída; a promoção de `proxy` no `init --from-letter` foi recusada pelos resultados do experimento. Nenhum produto real foi testado.

## Passos do briefing

| Passo | Estado | Arquivos, testes e prova |
| --- | --- | --- |
| 1. Inventário e ADRs | Feito | [Inventário](../plans/2026-11-16-v1-8-inventario-contratos.md), ADRs 0070–0074 e [0075](../../decisoes/0075-ritmo-proxy-em-perfis-novos.md); contratos propostos antes de código/promoção. A decisão posterior sobre 40026 está no [plano de fechamento](../plans/2026-11-16-v1-8-fechamento.md). |
| 2. Domínio | Feito | `domain/envelope.py`, `strategy*.py` e modelos congelados; testes de validação, proveniência, dependências, confinamento e recusa de alargamento. |
| 3. Aplicação e CLI | Feito nos contratos declarados | `application/strategy*.py`, `cli/commands/strategy.py` e `plan.py`; consultas, diff, migração, captura pública e prévia local. A prévia é simbólica e declara corpo/catálogo incompletos; não é prova de cobertura executada. |
| 4. Execução pelo plano | Feito | `application/scan.py`, snapshot e `adapters/scope_proxy/{gate,approval_watch,grant_queue,generate}.py`; T1 compara trabalho, testes cobrem publicação/revogação/fila/janela/prazo/stop e a corrida real foi reproduzida duas vezes. |
| 5. Migração e compatibilidade | Feito | `strategy_repository.py`, contratos CLI e teste independente de aprovação antiga. Cópia explícita, sem ativação ou nova permissão. Modelo e geração por carta continuam `legacy`; perfis existentes não são migrados. |
| 6. Skills e avaliação | Feito | Cadastro `onboard-product`, guia e referências atualizados; testes de contrato e cópia cega. Não houve nova permissão de ataque na carta. Rodada cega dispensada pelo briefing. |
| 7. Provas | Feito com limites registrados | Novas T4 B nas duas APIs, T2 seguros B e controles adicionais; [matrizes](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/closure/t4-summary.md). DOM XSS permanece fora da cobertura, igual à referência; sem perda comparativa atribuída a essa regra. |
| 8. Validação independente | Feito | Agente Terra medium novo: 34 testes offline e cinco provas reais passaram; decisão `continuar`. [Parecer](2026-11-16-v1-8-validacao-fechamento.md) e [proveniência](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/closure/validator2/provenance.json). |

## Contratos e aprovação

`strategy.yml` versão 1 referencia os documentos existentes e aceita escolhas tipadas de preservação, vinculadas a ambiente, autorização, contas, planejamento, OpenAPI, dados, fluxos e motor. Perfil ausente de estratégia e `choices: []` preservam o caminho legado. Observação não concede permissão. Tokens, cookies, respostas e recursos efêmeros não são persistidos na estratégia; reutilização executável permanece na V1.9.

Os comandos são `strategy validate`, `strategy diff`, `strategy migrate`, `strategy capture` e `plan --dry-run`, com `--products-dir`. Usam o envelope JSON v1 (`schema_version`, `ok`, `data` ou erro estruturado): sucesso 0, configuração 2, aprovação/escopo 3, ferramenta externa 5 e pilha ocupada 8. Migração e captura criam cópias exclusivas, não ativam nem modificam perfil/aprovação. A captura exige perfil aprovado e pilha gerenciada vigente; consulta somente o controle local. Seus quatro envelopes reais independentes estão em [validator2](https://github.com/MarcosQuintino0/harness-dast/tree/fd611a9/evals/measurements/v1-8/closure/validator2).

`validate`/`diff` secos não consultam motor e podem indicar `engine_unavailable`; a prévia de escolha preenchida falha fechada. Na execução ativa a versão observada e as fontes são verificadas antes do primeiro pedido ao alvo. A versão não autentica a instância, e o vínculo não elimina uma troca posterior do processo. O diff é estrutural, não uma comparação de cobertura. [Contrato completo](../../referencia/strategy.md).

O proxy gerenciado vincula aprovação e `target.yml` por hashes e assinaturas estáveis e os reconfere localmente por concessão, sem consulta de rede. Verifica também autorização, janela, prazo e stop; mudança, ausência ou erro fecha e trava a saída. A política interna recebe `binding` e a auditoria registra `approval_changed` (HTTP 403). O comando consumidor conserva o contrato da etapa interrompida: na corrida durante login, o `probe` terminou com saída 4. Não foi executado comando humano de aprovação; as aprovações das provas são fixtures sintéticas descartáveis do suporte de integração.

Diretórios são montados somente para leitura, com raízes estáveis durante a pilha; substituições de arquivos dentro deles são observáveis. Substituir administrativamente a raiz do próprio mount pode não ser observado. Concessões já encaminhadas não são canceladas. Mudança dos arquivos exige recriar a pilha; nova aprovação só é necessária se o fingerprint protegido mudou. A imagem principal é reconstruída na subida para impedir uso de proxy antigo. No Windows, a assinatura ignora a divergência de `ctime` entre `stat` e `fstat`, mantendo hash, identidade, tamanho e `mtime`; o teste também recusa mutação de bytes com tamanho e `mtime` preservados.

## Previsão congelada e resultado A/B

A previsão foi commitada em `09ee231` às 09:07 UTC, antes das novas T4 B. O [arquivo congelado](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/closure/forecast-frozen.json) contém fontes, hashes e run IDs. Fórmula prospectiva da V1.8: `T4_A × mediana(T3_B) / mediana(T3_A)`. É um estimador agregado novo; não reabilita a previsão histórica da V1.7 e registra conhecimento dos resultados B anteriores. O critério foi erro absoluto do ganho de no máximo **10 pontos percentuais por API**, além de qualidade independente.

| API | T4 A V1.7 | T4 B prevista | T4 B observada | Ganho previsto | Ganho observado | Erro |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Clínica Piloto | 619,491791 s | 340,181947 s | 436,801836 s | 45,086932% | 29,490295% | 15,596637 p.p. |
| VAmPI | 133,769327 s | 52,223020 s | 82,231248 s | 60,960393% | 38,527576% | 22,432817 p.p. |

São durações entre `scan.started_at` e `scan.finished_at`, não tempo total da suíte. As duas T4 B passaram em 713,89 s de suíte. Clínica B: `2026-11-16T09-24-45Z-clinica-piloto-4c57`; VAmPI B: `2026-11-16T09-34-19Z-vampi-388a`. A referência A está identificada por hash e run em cada matriz.

As duas previsões falharam; portanto **não promover** o ritmo. `init --from-letter` e o padrão do modelo continuam `legacy`. Perfis existentes, inclusive os explicitamente `proxy`, e suas aprovações não são alterados. Trocar um perfil existente para `proxy` continua exigindo aprovação humana do perfil.

Nas duas comparações, operações, desfechos, pulos e contagens de pedidos/alertas por regra não DOM coincidem: 28 operações/1.204 pares operação-regra na Clínica e 10/430 no VAmPI. Os achados disponíveis e fingerprints também coincidem: Clínica 98 ZAP, 4 authz, 0 negative; VAmPI 30 ZAP, 3 authz, 0 negative. [Matriz Clínica](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/closure/t4-comparison-clinica-piloto.json), [matriz VAmPI](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/closure/t4-comparison-vampi.json) e [achados detalhados](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/closure/findings-comparison-detailed.json). Campos ausentes não foram transformados em prova de igualdade; valores/pontos de injeção completos e identidade de toda evidência não são alegados.

A regra 40026 requer navegador e já aparecia `skipped/other` com zero pedidos na referência histórica. Sua exclusão comparativa foi decidida pelo dono; não constitui perda nova e não foi ligada. Continua sem prova DOM XSS. Nenhuma outra lacuna foi dispensada automaticamente.

## Provas, falhas e qualidade

A coordenação provou revogação real no VAmPI: concessão seguida de remoção da aprovação temporária e recusa `approval_changed`, sem concessão posterior. O validador repetiu e observou o mesmo, em 1,047 s; esse intervalo inclui a espera da taxa/poll e não é uma garantia de latência. Também reproduziu captura pública com estratégia preenchida e T2 nos quatro pares API/modo: **5/5 em 880,93 s** incluindo revogação. Uma primeira seleção independente marcou cinco testes como desmarcados; não conta como prova.

| Critério | Clínica vulnerável | Clínica segura | VAmPI vulnerável | VAmPI seguro |
| --- | --- | --- | --- | --- |
| Autorização | T4 sem concessão fora do allow; revogação/fila/janela/prazo/stop testados | T2 B sem tráfego permitido fora do allow | T4 e revogação real, sem concessão posterior | T2 B sem tráfego permitido fora do allow |
| Cobertura planejada | T1 item a item; 28 operações T4 iguais à A | Quatro operações T2, incluindo escrita e travessia | T1 item a item; 10 operações T4 iguais à A | Duas operações T2; controles CORS separados |
| Cobertura executada | 1.204 pares não DOM concluídos como A | T2 concluído e controles adicionais passaram | 430 pares não DOM concluídos como A | T2 concluído e CORS passou |
| Detecção | SQL/travessia e quatro técnicas authz observadas | Nove negativos de leitura rejeitados; escrita comparada à A | SQL/XSS na T4; SQL no T2 | Zero negativos de leitura elegíveis: não conta como sucesso |
| Falsos positivos | Não usado para concluir modo seguro | Zero altos ZAP; nove baixos de negative escrita já existiam em A | Não usado para concluir modo seguro | Zero altos ZAP; três anônimos também ocorreram no legado |
| Estado e identidade | 17.954/17.954 mensagens com Authorization; 5.036 escritas com par CSRF na T4 | 2.665/2.665 e 662 escritas com par CSRF no T2 independente | 4.272/4.272 com Authorization na T4 | 960/960 no T2 independente; presença não atesta identidade efetiva |

Presença de Authorization não comprova validade ou identidade em cada pedido. Aliases/desfechos do probe coincidem, e diferenças de frequência de login/CSRF foram preservadas, sem inferir troca de conta nem causa. As provas de autorização entre contas e a atribuição no plano são evidências adicionais, não uma atestação criptográfica da identidade por pedido.

Os controles B adicionais cobrem CORS nas duas APIs, autorização com matriz e escrita, e negative com escrita/restauração. A rodada negative manteve 59 pedidos, 12 operações, 5 criações, 4 restaurações e nove achados baixos iguais à A. CORS seguro teve zero achados nas duas referências e nas duas B. [Comparação](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/closure/other-controls-comparison.json) e [proveniência das execuções selecionadas](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/closure/other-controls/provenance.json). Os resumos A desses controles não trazem run_id; essa limitação é explícita.

Falhas preservadas: a primeira corrida de revogação não executava o preflight para semear o VAmPI; corrigida e repetida. Os controles extras tiveram um setup500 do VAmPI, uma contagem antiga de oito em vez de nove checks e uma recusa operacional 429 confundida com escopo. O teste passou a aceitar somente recuo estritamente correlacionado à tentativa 429 auditada; outras recusas continuam falhando. As execuções selecionadas passaram após correção/repetição, sem substituir as falhas originais. O T4 inicial da entrega anterior continua registrado como falho por asserção sobre contador não preenchido; as novas T4 B são provas distintas.

## Integração e entrega

Foi feito fetch e rebase sobre `origin/develop` com a V1.7 mergeada em `a267ae2` (PR #25). Os conflitos em versão/lock, `application/scan.py`, `cli/scan_composition.py` e blocos documentais foram resolvidos preservando o process sampler/ritmo/métricas da V1.7 e a estratégia/compilação da V1.8. Não houve junção de PR.

Os oito gates finais e o total final de testes são registrados no [manifesto](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/closure/gates-final.json), com SHA de fonte, comandos, saídas e tempos. Incluem Ruff check/format, mypy Windows/Linux, import-linter, Vulture, pytest completo e gitleaks sem afrouxamento. Logs/JUnit e estado descartável estão em `C:\harness-dast-artefatos\v1-8\closure\`; apenas medições revisadas foram versionadas, não a pasta inteira. A [proveniência independente](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/measurements/v1-8/closure/validator2/provenance.json) identifica as fontes. A conferência do CI remoto e o último commit publicado constam na entrega e no [PR #24](https://github.com/MarcosQuintino0/harness-dast/pull/24).

A coordenação permaneceu nesta sessão Codex. Programação de proxy e análise/suporte de desempenho usaram `/root/proxy` e `/root/perf`, GPT 6.1 Terra high; QA independente `/root/qa2` e documentação `/root/docs2`, também Terra high. O novo `/root/validator2` usou Terra medium e não implementou. Cada agente trabalhou em worktree própria; os commits foram integrados e as cinco worktrees/branches auxiliares removidas após verificar limpeza e equivalência. As pilhas foram desmontadas, o Docker estava vazio e as travas próprias foram removidas ao encerrar cada reserva. O checkout `C:\harness-dast` não foi alterado.

Não há decisão adicional solicitada ao dono. O experimento recusou a promoção B, conforme a condição delegada; a revisão humana das áreas críticas permanece para o PR. O PR só é retirado de rascunho depois do parecer `continuar` e dos gates finais aprovados, e não é juntado.
