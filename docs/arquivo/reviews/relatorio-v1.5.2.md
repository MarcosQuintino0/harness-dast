# Relatório da versão 1.5.2

Data: 2026-11-15. Branch: `feat/v1-5-2-avaliacao`. Plano: [V1.5.2](../plans/2026-11-15-plano-v1-5-2-avaliacao.md). Versão anterior: [1.5.1](relatorio-v1.5.1.md).

Entrega: implementação A a H, QA independente, provas de integração e gates completos. O PR é destinado à `develop`; o Codex não o junta.

## 1. Resumo

**Número:** 1.5.2. Atualiza a avaliação para as autorizações e fontes de achados existentes desde a V1.4/V1.5.1 e corrige paginação, agrupamento de sinais e orientação de configuração. Nenhuma técnica de ataque nova foi acrescentada. O trabalho e as provas usaram somente esta worktree e worktrees temporárias; o checkout `C:\harness-dast` não foi utilizado.

Os itens A a H estão implementados. O caso estrito anterior foi preservado, e novas rodadas lacram o caso. Rodadas antigas sem o lacre precisam receber o gabarito histórico explicitamente: deduzir a carta a partir do perfil alterava a nota e não era seguro.

**Mudanças de uso:** `score`, `classify`, `collect` e `approve` do executor aceitam `--case-file` para rodadas antigas sem `sealed/case.json`. O arquivo não pode substituir um caso já lacrado. Os fingerprints dos sinais (`S-`) passam à versão 2; os outros fingerprints permanecem como antes. `spec inspect` acrescenta `hints`, sem escrever o perfil.

## 2. Em linguagem simples e aceite por item

Os prefixos `domain/`, `application/` e `cli/` abaixo correspondem a `src/harness_dast/`.

| Item | Estado e mudança | Arquivos principais | Testes e prova |
| --- | --- | --- | --- |
| A. Carta e caso | **Feito.** A carta autoriza modo amplo, escrita entre contas, escrita de valores proibidos e `not_found`, inclui cinco contas e explica como obter nome de documento existente. O caso estrito fica separado para novas comparações. | `evals/cases/clinica-piloto/`, `evals/cases/clinica-piloto-estrito/`, `evals/runner/prepare.py`, ADR 0053 | `tests/unit/evals/test_approve.py` prepara o caso real, verifica 11 checks, aprova um perfil sintético com cinco contas e recusa upload não autorizado. `test_prepare.py` e o contrato de skills verificam a cópia sem termos que revelem falhas. Nenhum `hdast profile approve` foi executado. |
| B. Régua | **Feito.** Lê quatro fontes e casa categoria/técnica e operação, valida permissões da carta, lacra casos e permite gabarito histórico explícito. | `evals/runner/{models,checks_findings,checks_profile,cases,scoring,approve,collect,cli}.py`, `evals/cases/clinica-piloto-historico-terra-wide.yml`, ADR 0053 | `test_v152.py` e `test_evals_v152_qa.py`: achados sintéticos das quatro fontes, entradas malformadas, recusa sem carta, origem do gabarito e lacre. A nota Terra antiga foi recalculada pela CLI: **7,18**, com os seis scores de componente iguais aos arquivados. A checagem dos segredos antigos ficou indeterminada por falta do lacre no arquivo sanitizado. |
| C. Laboratório | **Feito.** Segunda conta médica `PILOT_MEDICO_B_*`, passagem de variáveis pela pilha, perfil e suporte descartável. Nenhuma falha plantada nova. | `lab/pilot/`, `application/lab_targets.py`, `tests/integration/{run_support,test_lab_authz,test_cleanup_oracle}.py`, `tests/unit/application/test_stack.py`, ADR 0054 | A integração comprovou `horizontal_write.tested = 1` nos dois modos e uma resposta real de `PUT`/`PATCH` entre médicos. O build executou os testes Java, incluindo compartilhamento permitido entre médicos nos dois modos. |
| D. Paginação | **Feito.** Página inicial 0/1 e tamanho pequeno válido, respeitando limites abertos/fechados; regras explícitas, enum e encadeamento mantêm precedência. | `domain/request_builder.py`, perfil de dados do laboratório, ADR 0054 | `test_request_builder.py`, `test_pilot_pagination.py` e `test_request_builder_v152_qa.py`. A integração comprovou lista com itens e ausência de `no_sample_data` especificamente em `listarPacientes`. Não se promete eliminar esse motivo de outras operações. |
| E. Sinais | **Feito.** Resolve pelo contrato completo, inclusive com `probe --only`, agrupa por operação/método/categoria e reúne o que não casa em um grupo por categoria. | `domain/{signal_findings,signal_operations,signal_result}.py`, `application/report.py`, `cli/scan_composition.py`, ADR 0055 | Unitários e QA cobrem identificadores alterados, rota literal, ambiguidade, privacidade, 507 operações, teto e omissões. A integração consolidou 139 respostas com sinal em quatro achados no vulnerável e zero no seguro, sem omissões. |
| F. Dicas | **Feito.** Hipóteses no JSON e no texto do `spec inspect`, sem mudar o perfil. Inclui lista de strings de documentos, campos de objeto e contas pares. | `domain/spec_hints.py`, `application/{inspect_spec,inspect_report}.py`, `cli/commands/spec.py`, skills `fix-reachability` e `onboard-product`, referência CLI, ADR 0056 | Testes do domínio, aplicação e contrato; QA reproduziu e retestou a rejeição de formatos incompatíveis. Conferem `listarDocumentos` → `baixarDocumento`, campo `0`, operações permitidas, sanitização e tetos. O efeito sobre um agente numa rodada cega nova não foi medido. |
| G. Docker e doctor | **Feito, com limite de prova registrado.** O prepare grava regras conservadoras `Bash(*docker*)` e `PowerShell(*docker*)`; falha da consulta de imagens orienta repetir `hdast doctor`. | `evals/runner/prepare.py`, `application/doctor.py`, ADR 0053 | Testes da configuração gerada e da mensagem. As regras usam sintaxe documentada, mas o bloqueio efetivo no Claude Code em execução não foi provado. Podem negar menções textuais inofensivas. A auditoria do transcript continua necessária. |
| H. Processo | **Feito.** Toda função condicionada à carta exige atualização do caso e da régua no mesmo PR. | `CONTRIBUTING.md`, `docs/arquivo/plans/2026-11-14-ciclo-v1-3-a-v1-8.md` | Regra expressa na Definition of Done e nos critérios comuns; links verificados pela suíte. |

## 3. Evidências

As saídas completas ficam em `C:\harness-dast-artefatos\v1.5.2\`. Os [resumos sanitizados do laboratório](../../../evals/results/2026-11-15-v1-5-2-lab/README.md) estão versionados, com origem e hashes no manifesto. Isto é uma prova de integração, não uma avaliação cega nova.

**Laboratório: 44 passaram, 2 pulados, 0 falhas em 1.183,09 s (19 min 43 s).** Os dois arquivos são `tests/integration/test_lab_authz.py` e `test_lab_error_signals.py`, com `-m "integration and lab_fast"`, modos vulnerável e seguro, imagens reconstruídas, credenciais e chave do ZAP aleatórias. Cada fixture terminou com `stack down`; `docker compose ls -a` confirmou lista vazia. Os pulos são as verificações que só se aplicam ao outro modo.

| Medida | Vulnerável | Seguro |
| --- | --- | --- |
| Pedidos do authz | 171 | 163 |
| Operações testadas por horizontal_write | 1 | 1 |
| Operações testadas por excessive_data | 17 | 16 |
| Achados de excessive_data | 1 | 0 |
| Recursos sintéticos criados | 10 | 10 |
| Pedidos do ZAP na prova de sinais | 657 | 1.233 |
| Respostas com sinal | 139 | 0 |
| Grupos de sinais / omitidos pelo teto | 4 / 0 | 0 / 0 |

Os quatro grupos vulneráveis são três operações identificadas e um grupo fora do contrato, que agrega 126 ocorrências sem inventar operação. O scan seguro também varreu a busca por nome, que no vulnerável deu erro e foi pulada; os volumes dos modos não são uma comparação de desempenho.

**Preparação offline final:** a CLI `evals.runner prepare` sobre a árvore final encontrou 36 exclusões e zero termos do gabarito na cópia. A aprovação da carta real e a recusa de upload não autorizado estão nas duas regressões de `test_approve.py`.

**Comparação histórica:** o teste recompõe o rastro público de `evals/results/2026-11-14-clinica-piloto-terra61-medium-wide/attempts/02-main`, restaura as extensões sanitizadas e usa o caso histórico reconstruído do patch arquivado. Parâmetros: 8.023.944 tokens e 1.777 segundos. Os seis componentes e a nota 7,18 coincidem. Isso comprova compatibilidade numérica com aquela entrada, não mede a qualidade da V1.5.2 numa rodada nova e não recupera o lacre de segredos ausente.

## 4. Qualidade e testes

Uma suíte com cobertura, antes de acrescentar as duas regressões do caso real, passou com **9.236 testes, 4 pulados e 159 desselecionados**. A suíte final sem filtro, após o fechamento dos arquivos, passou com **9.238 testes, 4 pulados e 159 desselecionados**, sem falhas. Logs em `gates/pre-final-cobertura/` e `gates/final/` na pasta externa de evidências.

| Gate | Resultado |
| --- | --- |
| `ruff check .` | Sem problemas |
| `ruff format --check .` | 976 arquivos |
| `mypy` e `mypy --platform linux` | 809 arquivos em cada plataforma |
| `lint-imports` | 6 contratos mantidos |
| `vulture` | Limpo |
| `pytest -q` final | 9.238 passaram, 4 pulados, 159 desselecionados |
| Cobertura de ramos | Domínio 98,5%; aplicação 97,2% |
| Cobertura do diff | 97%: 184 linhas alteradas, 4 sem cobertura; piso 90% |

**QA independente:** quatro arquivos novos `*_v152_qa.py`, com 17 casos executados no coordenador. As rodadas focadas do QA passaram: sinais/doctor 104, paginação 70, avaliação 80 e dicas 51 (essas contagens incluem testes existentes e não devem ser somadas como testes novos). O QA não programou a implementação, não operou Docker e não tocou o alvo.

## 5. Problemas e decisões

- A revisão de paginação encontrou mínimo de tamanho maior que 10 voltando ao sorteio. O gerador agora escolhe um tamanho válido próximo de 10, inclusive com limites exclusivos.
- A fidelidade do perfil não tratava blocos de ataque nulos e aceitava flags de tipos inválidos quando a carta permitia a função. Agora falha fechado, com testes de recusa e sem gravar aprovação.
- O QA demonstrou que aplicar o caso estrito silenciosamente à rodada ampla antiga mudava 7,18 para 3,0. A solução exige gabarito histórico explícito e registra caminho e hash; não infere autorização a partir do perfil.
- O QA encontrou dica de encadeamento entre `uuid` e `date` quando os campos tinham o mesmo nome. Formatos declarados incompatíveis agora impedem a dica.
- A suíte integrada pegou a contagem antiga de credenciais geradas (7, agora 9). O teste passou a verificar os nomes esperados e a preservação de credencial fornecida pela pessoa.
- A primeira tentativa de laboratório terminou com **46 erros de preparação**, por falha do build Maven. O teste de limpeza Java esperava quatro usuários semeados; a semente agora tem cinco. A asserção e a preservação do segundo médico foram corrigidas, sem alterar o SQL de limpeza. A repetição passou integralmente, com os testes Java habilitados no build padrão.
- Médicos compartilham pacientes por regra do laboratório. A leitura `buscarPaciente` e a escrita `atualizarPaciente` podem gerar indicações horizontais altas mesmo no modo seguro. A exceção do teste é restrita a essas duas combinações, preserva as demais asserções e não marca operação como pública. Esse resultado exige triagem humana.

## 6. Sugestões descartadas

Nenhum item A a H foi descartado. Não se adotou inferência automática da autorização histórica a partir do perfil: faltava informação confiável sobre a carta alterada daquela rodada.

## 7. Débitos e não provado

- Nenhum produto real, varredura completa `lab_full` ou rodada cega nova foi executado nesta versão; o plano delimitou o laboratório aos testes de integração dos itens C, D e E.
- Eficácia real das novas regras Docker em versões/modos do Claude Code e efeito das dicas sobre agentes continuam sem prova.
- O caso lacrado preserva o gabarito, não o código do avaliador. Reproduzir uma rodada antiga exige também versão do executor, rastro e parâmetros; segredos ausentes não são inventados.
- O relatório usa o OpenAPI atual quando ele ainda contém os modelos registrados no probe. Mudança numa operação ausente do probe não pode ser detectada sem snapshot completo do contrato; o fallback histórico está no ADR 0055.
- Paginação não acrescenta suporte a `multipleOf`, ausente do modelo de esquema existente. Dicas são hipóteses limitadas, não prova de compatibilidade de todos os valores.
- Permanecem fora desta prova HTTPS real, respostas `br`/`zstd`, custo da cerca em respostas grandes e execução contra Oracle. O laboratório é descartável; os recursos sintéticos criados são removidos ao derrubar a pilha.
- Nenhum pedido foi recusado ou limitado por regra do modelo. As limitações acima são de escopo de teste, disponibilidade de evidências ou comportamento ainda não medido.

## 8. Conclusão e revisão

A versão atende aos itens A a H, com os limites de prova descritos. O PR é aberto para `develop`, sem merge pelo Codex. ADRs 0053 a 0056 permanecem **Proposto**; sua aceitação é decisão do dono. A política de revisão do projeto para módulos críticos continua aplicável (`CONTRIBUTING.md`). As worktrees e branches temporárias dos subagentes são removidas no fechamento; só a branch da versão é publicada.

**Orquestração:** quatro subagentes distintos, todos **GPT 6.1 Terra, esforço high**. Três programadores: `evals` (A, B e prepare de G), `lab_data` (C, D e depois F) e `signals` (E e doctor de G); um QA independente. Máximo de três programadores simultâneos. O programador C/D reutilizado em F mudou para outra worktree baseada na versão integrada. Não foi necessário subagente exclusivo de documentação; o coordenador escreveu o fechamento.
