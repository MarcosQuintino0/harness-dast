# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). O versionamento seguirá [Versionamento Semântico](https://semver.org/lang/pt-BR/); mudança incompatível no envelope JSON ou no schema do perfil sobe a versão maior. A versão 1.1.0 é a primeira numerada (a 1.0.0 nunca foi publicada).

## [Unreleased]

## [1.12.1] - 2026-11-17

- Parte 2: `stack up crapi` monta a ponte OAST interna e liga o workshop a ela somente com perfil aprovado e `scan.oast: true`; `stack down` remove ambos. Sem a chave, a montagem segue sem ponte OAST; produto comum não ganha ponte. O domínio registra a falta de retorno verificável em `scan.json.oast_verification`, no relatório e no painel, sem interpretar zero observações como verificação limpa. [ADR 0105](docs/adr/0105-ponte-oast-na-pilha-e-verificabilidade.md), proposto, substitui parcialmente o 0099.
- Pendência de mutação pula somente a operação e conta afetadas em `probe`, `authz`, `negative`, `extra_checks`, SSRF guiado/OAST existente e `scan` sobre semente histórica. `mutation_pending` aparece na cobertura, relatório e painel, sem contar alcance ou sucesso e sem reenviar o pedido. Corrupção e falhas do diário continuam interrompendo a execução.
- `hdast mutation list` apresenta contexto não sensível, inclusive registros antigos sem metadados; `hdast mutation release <id>` exige pessoa em terminal interativo, confirmação após conferir o alvo e a trava exclusiva de execução. Arquiva com `human_release` e evento de auditoria `mutation_human_release`. O agente não pode liberar. [ADR 0104](docs/adr/0104-bloqueio-local-e-liberacao-humana-de-mutacoes.md), proposto.
- `hdast mutation list` mostra as pendências válidas e aponta entradas corrompidas só por id (`data.invalid`), e `release` valida apenas o id pedido; entrada inválida segue bloqueando o envio. Relatório e painel reconhecem `mutation_pending` por nota exata da CLI, não por trecho de texto do alvo. ADR 0104 registra a mudança da chave das tentativas de rejeição do 0101 e a restauração `unrestored` do PUT/PATCH após 5xx no `negative`.
- Caso `crapi-foco` v3 informa o `mechanic_api` local do workshop, código do mecânico e inteiro de repetição, preservando caminhos, métodos, limites e detectabilidade da v2. A régua do caso ganhou critérios de reconhecimento: C11 e C15 eram detectáveis sem `match` e nunca contavam como achadas, o que zerou o item (c) da primeira rodada cega da V1.12. Um teste novo exige critério em toda falha detectável de todo caso. Referência do envelope e skill `run-scan` esclarecem que `options.include_outcomes: true` usa a lista do perfil, inclusive quando vazia; contrato preservado.
- Pacote e `uv.lock` em 1.12.1, sem dependência nova. Na parte 1, prova crAPI aprovada (run de 47,703 s, sem reenvio dos POSTs pendentes), regressão dirigida verde em 750,99 s e seis gates locais verdes (11.128 testes aprovados). Provas e limites de cada parte no [relatório da V1.12.1](docs/reviews/relatorio-v1.12.1.md).

## [1.12.0] - 2026-11-17

Versão do pacote e do `uv.lock` em 1.12.0. Provada só no laboratório (Clínica Piloto, VAmPI e crAPI), sem produto real; rodada cega e validação independente pendentes. Relatório em `docs/reviews/relatorio-v1.12.md`. A tabela do que usamos do ZAP foi revisada para o estado final (`docs/reference/uso-do-zap.md`), com a correção da afirmação do ADR 0099 sobre a regra de SSRF.

### Caso cego `crapi-foco`, versão 2

- A carta do caso liga `attack.pacing: proxy` e as cinco capacidades (`inject_headers`, `oast`, `allow_rate_tests`, `experimental_rules`, `inventory`), cada uma com frase de autorização; o POST da verificação de OTP da v2 entra no escopo (a v3 e a recuperação de senha seguem negadas). O gabarito marca `detectable: true` em C3, C11 e C15 e `false` em C1, C6, C10 e C12. O caso da Clínica Piloto não muda: a H11 segue `detectable: false` porque a carta da Clínica não autoriza cabeçalhos.

### Trilha F: capacidades

- F1 (ADR 0096, proposto): a seção `attack` da carta ganha `pacing`, `inject_headers`, `oast`, `allow_rate_tests`, `experimental_rules` e `inventory`, todas desligadas quando ausentes. O `init --from-letter` gera `scan.pacing`, `scan.inject_headers`, `scan.oast` e o bloco `extra_checks`; só a carta liga (booleanos com `source: carta` e frase). A impressão digital da aprovação só muda quando uma chave é ligada; perfis existentes mantêm a aprovação. As capacidades que consomem as chaves vêm nos passos F2 a F8.
- F2 (ADR 0099, proposto): `scan.oast` configura o Callback do OAST do ZAP para a ponte do laboratório (ADR 0095) e liga as regras da imagem que dependem do retorno (Log4Shell 40043, XXE 90023, SSTI cega 90036; a `zap-stable` pura não tem regra de SSRF nem de comando cego; a imagem derivada do F7 traz o SSRF 40046, ver ADR 0103). Desligado, nenhuma chamada `oast/*` e política idêntica à de antes.
- F3 (ADR 0100, proposto): com `scan.oast`, o `scan` manda a URL de retorno nos campos de URL do contrato (`format: uri`, nomes como `*_url`, `*_api`, `callback`, `webhook`), pela cerca, com teto rígido de 10 pedidos; o retorno correlacionado por token vira achado de SSRF (CWE 918) com a prova do evento. Prova do desafio de SSRF do crAPI no laboratório em `tests/integration/test_lab_oast_scan.py`.
- F4 (ADR 0098, proposto): o `tampered_token` do `authz` passa a quebrar OFFLINE a chave HMAC de um JWT com uma lista fixa e versionada de chaves fracas e, achada, envia até 2 pedidos de prova com o token re-assinado (reivindicação inofensiva e `exp` vencido), com teto de 10 operações por execução. Sem chave nova na carta; severidade alta, CWE-347; chave e tokens nunca são gravados. Prova no lab: o crAPI aceitou `alg_none` e `altered_claims` no `authz` (C15 parcial: `kid`/`jku` não avaliados) e a Clínica segura ficou sem achado; a quebra da chave HMAC fraca só foi exercitada em teste de unidade, nunca contra um alvo no laboratório.
- F5 (ADR 0101, proposto): com `extra_checks.allow_rate_tests`, o `scan` faz, depois do ZAP e pela cerca, (a) dois pedidos de tamanho de página (normal e 10 000, ou `maximum` + 1000) nos `GET` com parâmetro inteiro `limit`/`page_size`/`size`... e (b) até 20 tentativas com valor errado e sintético, com o identificador da conta de teste, em `POST` de autenticação ou verificação (`otp`, `password`, `code`...), parando no primeiro `429`, `Retry-After`, bloqueio ou mudança de resposta. Teto de 66 pedidos; achados `Medium` (CWE 770 e 307) com a contagem; `scan.json` ganha `rate_checks`.
- F6 (ADR 0097, proposto): `scan.inject_headers` liga os bits de cabeçalho e cookie da máscara (63) e `ScanHeadersAllRequests` no ZAP; desligado, nada muda. Prova no laboratório: H11 achada só com a chave; 519 pedidos sem e 1089 com a chave na operação; modo seguro com a chave sem achado (ver `tests/integration/test_lab_header_injection.py`).
- F7 (ADR 0103, proposto): a imagem do ZAP passa a ser `hdast/zap` (`docker/zap/Dockerfile`), derivada da `zap-stable` 2.17.0 já fixada por digest, com `ascanrulesBeta` 64 e `ascanrulesAlpha` 54 baixados no build e conferidos por SHA-256 (nada é baixado em execução). As 26 regras novas ficam sempre desligadas na política; `extra_checks.experimental_rules` (só a carta) liga NoSQL MongoDB (40033 e 90039) e, junto com `scan.oast`, o SSRF 40046. Achados dessas regras saem com `experimental: true` no `findings.json` (campo aditivo, padrão `false`) e a marca `[experimental]` no relatório, no painel e na verificação. Desligado, a política efetiva é a de antes.
- F8 (ADR 0102, proposto): com `extra_checks.inventory`, o `scan` faz até 40 `GET` pela cerca: versões irmãs não documentadas (`/v2/x` quando o contrato tem `/v3/x`, com controle `v999` contra resposta curinga) e 16 caminhos fixos de documentação exposta. O que a cerca nega vira `not_verifiable_by_fence`, nunca é forçado. Achados baixos ou informativos; `scan.json` ganha `inventory`.

### Trilha L: laboratório

- crAPI na pilha gerenciada, com cadastro sintético via API/MailHog, projeto próprio, recusa de modo seguro e descida com volumes descartáveis (ADR 0094, proposto). O chatbot de 1,5 GB deixou de ser necessário; o nginx usa um upstream já presente.
- Sufixo opcional e validado `HDAST_STACK_PROJECT_SUFFIX` para isolar projetos e rede; integrações desta trilha usam `-codex`.
- Opções incompatíveis são recusadas antes de derrubar a pilha anterior. Erros do Compose omitem saída arbitrária do subprocesso para preservar também credenciais herdadas ou transformadas.
- Ponte interna para Callback do ZAP, overlay do workshop e provas dirigidas de evento/topologia, ainda sem execução real nesta trilha (ADR 0095, proposto). Nenhuma regra de varredura é ligada.
- O suporte OAST reconcilia recursos por identidade e etiqueta da prova, tenta etapas independentes após falhas e registra a limpeza separadamente do evento. O cadastro do crAPI obtém as rotas do OpenAPI validado do perfil, preservando a cópia cega.
- Inventário de imagens e roteiro de limpeza em simulação: valida IDs, captura inicial, referências protegidas e contêineres em uso antes de gerar comandos para revisão humana; não remove imagens automaticamente.
- Caso curto `crapi-foco` com carta estruturada, orçamento de 900 segundos e detectabilidade conservadora. O verificador da avaliação confere cada par caminho/método na mesma origem autorizada, com testes de recusa de combinações cruzadas.
- Prova inicial do crAPI: subida e descida passaram, mas o `preflight` parou com `STACK_STALE`. Nenhuma detecção nova da trilha F ou rodada cega foi executada. A frente L3/L5 foi recusada pelo provedor; alterações parciais foram preservadas fora da branch para retomada conforme o plano.
- V1.12 (L3, ADR 0092 proposto): operação `buscarMedicoPorCabecalho` (`GET /api/medicos/por-cabecalho`, cabeçalho `X-CRM`) na Clínica Piloto com a falha H11 (injeção de SQL em cabeçalho) só no modo vulnerável; OpenAPI regenerado pelo alvo; H11 no gabarito e no caso `clinica-piloto` como `detectable: false`.
- V1.12 (L5): marcador `regressao_dirigida` e roteiro de regressão dirigida (H1 a H10, controle seguro, V1 e V3) em `tests/integration/test_regressao_dirigida.py`.
- Retomada L1: ciclo crAPI descartável com subida, preflight das duas contas, probe de `get_products`, run curto LOW e descida passou em 229,63 s. Os preparadores preservam as operações de cadastro e isolam regras do contrato reduzido.
- Retomada L2: evento real do workshop chegou ao Callback pela ponte interna; contador de 0 para 1, redes internas e `ENETUNREACH` verificados, com limpeza concluída. O suporte interpreta a resposta plana da API de estatísticas do ZAP; isso não liga OAST na varredura.
- Diagnóstico sanitizado do primeiro travamento da vigia (ADR 0093, proposto), mantendo as recusas e o limite de 200 ms. Uma repetição verde não demonstra correção da intermitência de `STACK_STALE`.
- Inventário de imagens por todos os Compose versionados e contêineres, inclusive parados, em modo de ensaio; imagens sem tag ou digest permanecem sem atribuição. Nenhuma imagem é removida pelo roteiro.
- Retomada L5: regressão dirigida verde em 715,24 s (11min55s): H1–H10 na Clínica vulnerável, zero achado de autorização no modo seguro, V1 e V3 no VAmPI. Foram 14 testes aprovados e 26 combinações de cenário/falha inaplicáveis puladas.
- Retomada L4: `evals.runner` preparou o `crapi-foco` sem vazamentos e o ensaio sem agente concluiu em 294,265 s, incluindo subida e descida. O probe do run tentou nove operações; duas chegaram ao scan e houve exclusões em authz/negative. É prova de duração operacional, sem cobertura integral ou detecção das falhas da trilha F. O ensaio evita repetir o probe mutante antes do run e preserva o bloqueio de mutações com resultado desconhecido.
- Revisão e repetição finais: provas crAPI verificam projetos livres, identidades e ausência de recursos após a descida; recusam derrubar uma subida parcial sem inventário confiável. Ciclo curto verde em 254,098 s e foco em 310,344 s de ponta a ponta, com conclusão operacional separada de cobertura. Falhas previsíveis do emissor da vigia têm estado sanitizado e não interrompem a recusa. A causa do `STACK_STALE` anterior continua não estabelecida.

### Organização

- Navegação por intenção (`docs/README.md`, com "Onde colocar cada coisa"), índice de planos e estado centralizado no roadmap; histórico retirado das instruções.
- Pacote e lock alinhados à publicação 1.9.3; contrato impede versões divergentes e estado versionado no README/arquitetura.
- Limpeza: procedimento no guia, contrato na referência e política em operations; seis gates obrigatórios e projetos locais ignorados.
- Regras A/B canônicas em AGENTS, importação curta no Claude e cinco skills de desenvolvimento, separadas das cinco de uso.
- Cópia cega por lista de permissão, manifesto de arquivos e proteção de AGENTS (ADR 0083); contexto menor explicitado no protocolo.
- Sete arquivos de pesquisa consolidados em docs/research e política documental de retenção de evals, sem apagar resultados.
- Grupo panel: módulos e testes em subpacotes da mesma camada, imports atualizados e sem reexportações de compatibilidade.
- Grupo authz: módulos e testes em subpacotes da mesma camada, imports atualizados e sem reexportações de compatibilidade.
- Portas da aplicação divididas por consumidor em 12 módulos, com módulo comum para contratos compartilhados; 47 declarações, assinaturas e docstrings preservadas.
- Grupo report: módulos e testes em subpacotes da mesma camada, imports atualizados e sem reexportações de compatibilidade.
- ADR 0084 proposto compara apresentação no domínio e em adapters/reporting; recomenda migração futura, sem troca de camada nesta entrega.
- Mapas domain/application por assunto com inventário e destinos de código novo; plano V1.9.4 com aceites e limites.
- CI: job Windows de unitários/contratos, timeout em todos os jobs e integração manual com imagens explícitas, sem aceitar saída 5. Configuração ainda sem execução real no CI.

### Corrigido

- Cópia cega: `lab/pilot/target/` (saída de build da Clínica Piloto, ignorada pelo git) entrava no workspace com as classes compiladas, `application.yml` e o esquema SQL, que revelam o código do alvo. A lista antiga de exclusões e a nova lista de permissão deixavam a pasta passar quando ela existia na origem; agora ela é excluída, com teste. Rodadas antigas preparadas a partir de um checkout com o alvo compilado podem ter recebido esses arquivos.
- `hdast confirm`: a leitura de cabeçalhos registrados aceita `Vary`, `Set-Cookie` e outros nomes repetíveis; antes, qualquer nome repetido tornava a evidência "indisponível" (30 alertas de `X-Content-Type-Options` da Clínica Piloto). Com teste.
- `authz`: o envio da chave HMAC fraca de JWT respeita o teto de pedidos de prova (2 por chave achada, 10 por execução). Com teste.
- Limite de consumo: as tentativas de valor errado têm intenção própria no diário da cerca (`rejection-attempt:`), e lista vazia no teste de página enorme dá resultado inconclusivo, não limpo. Com teste.
- Limite de consumo, correções da validação independente (ADR 0101): (1) tentativas repetidas só viram achado com rejeição 4xx estável; `5xx` na primeira resposta é inconclusivo (`server_error_http_5xx`), e o valor errado respeita tipo, `pattern`, exemplo e tamanho do contrato (dígitos num código numérico); (2) a intenção `rejection-attempt:` do diário agora tem teste com o `NegativeSender` real: 5xx fica `observed` só com a intenção, `502`, `503` e `504` continuam pendentes e um 2xx fica `succeeded`; (3) operações que trocam ou cadastram credencial (`change`, `set`, `register`, `new_password`...) saem do teste e um 2xx registra `possible_state_change`; (7) página enorme sem `maximum` tem confiança baixa e diz que é heurística.
- SSRF guiado: falha do proxy do ZAP durante o envio vira nota de parada no resumo `ssrf`, sem abortar o `scan`. Com teste.
- Inventário: versão irmã que responde `5xx` é inconclusiva, não existente. Com teste.
- `authz`: só a chave HMAC fraca com 8 ou mais caracteres entra no cofre de mascaramento (palavras como `test` e `key` mascarariam qualquer saída); os tokens re-assinados continuam registrados. Com teste.
- `stack up`: com `--build`, o processo do Compose ganha 600 s além do prazo de saúde (o build da imagem `hdast/zap` baixa dois complementos e rodava dentro de 30 s de folga). Com teste.


## [1.11.0] - 2026-11-17

- Provas 0, D e F executadas só no laboratório (Clínica Piloto vulnerável e segura, VAmPI vulnerável e seguro), com aprovações descartáveis do suporte de integração em estado de teste, sem `profile approve` e sem estado real. Linha de base `44ef387`: Clínica vulnerável `80a9` (98 ZAP, 4 autorização, 29 sinais), segura `ab47` (63 ZAP, 1 autorização) e VAmPI vulnerável `1fd0` (30 ZAP, 3 autorização, 4 sinais). Calibração com `hdast confirm` em todos os achados de cinco execuções completas: só recibos de autorização chegaram a `reproduced` (3 falhas plantadas, 2 médicos que compartilham pacientes sem `shared_roles`, 6 respostas sem login do VAmPI); o único SQL elegível a receita ativa ficou `inconclusive`; nenhum `likely_false_positive` ocorreu. Matriz e limites em `docs/reference/verification-calibration.md`; relatório em `docs/reviews/relatorio-v1.11.md`.

Carimbo da candidata na branch, sem publicação e com aceites operacionais pendentes.

### Verificação

- Painel: nível e motivo de verificação junto da confiança em cada cartão, com ataque/controle redigidos e confirmação humana separada. Índice com nomes legíveis, gravidade em português e detalhes recolhidos por padrão; os relatórios preservam a apresentação anterior.
- Textos de confiança e reprodução de CORS e campos fora do esquema correspondem à técnica observada, sem atribuir comparação entre contas. O recibo CORS atual não guarda o valor de `Origin`; o painel explica por que não oferece um comando fiel.
- Motivo de recusa de regras sem receita tem precedência sobre o método da operação; preservados nível, severidade e bloqueio de escritas. Regressões unitárias e de contrato cobrem o polimento.
- Contrato aditivo `verification.json` v1, com nível e motivo definidos no domínio; classificação sem tráfego que preserva achados, severidade e status (ADR 0085, proposto).
- Leitores consultivos compartilham decodificação estrita: chaves duplicadas, constantes não finitas e conteúdo malformado falham com erro seguro.
- `hdast finding acknowledge`: declaração humana aditiva em terminal interativo, separada da verificação automática e da opinião em `triage.json`; bloqueio do comando para o agente (ADR 0086, proposto).
- `hdast confirm`: receitas fixas de leitura com controle, resultado aditivo e contagem separada de pedidos de receita e sessão; painel e relatórios apresentam verificação e confirmação humana (ADRs 0087 e 0088, propostos). Calibração medida só no laboratório, com amostras pequenas e sem produto real.
- Recibo aditivo da URL e conta efetivamente varridas; execuções antigas sem recibo não geram confirmação ativa. Prova parcial e causa de parada são preservadas, e sessão, CSRF e recuos consomem o teto por achado (ADR 0090, proposto).
- Observação guardada de cabeçalhos e técnicas de autorização sem tráfego novo, com limites por tipo e leitura posterior quando necessária; seção consultiva estruturada no HTML e testes por camada (ADR 0091, proposto).
- Skills de triagem orientam a reprodução pela CLI e a leitura da verificação. Régua privada de acerto da triagem preserva a nota histórica (ADR 0089, proposto).

## [1.9.3] - 2026-11-16

### Adicionado

- Teste de autorização sem depender do roteamento do perfil (ADR 0082, proposto): para cada `GET` de item com um identificador final escalar que nenhuma conta de papel não compartilhado com par alcançou, o `authz` monta sozinho a leitura de dono. Escolhe as duas primeiras contas do primeiro papel com par fora de `authz.shared_roles`, descobre o identificador pela coleção da própria conta, por alvos de `GET` de sucesso ou pelo campo do corpo já redigido de uma criação da conta, confirma a linha de base (2xx e mesmo identificador) e repete a leitura com a outra conta. Só `GET`, no máximo dois objetos por operação e par, pelo mesmo caminho de envio do `authz` (cerca, limites, janela, stop, diário). Nenhum identificador é adivinhado.
- Lacunas com motivo estável e ação sugerida (`owner_read_unsupported`, `owner_collection_missing`, `owner_collection_empty`, `owner_collection_unavailable`, mais os já existentes) em `authz.json`, `report.md`, `report.html` e na nova aba Autorização do painel (`authorization.html`; `data.files` do `hdast panel` ganha essa página). As lacunas horizontais não são cortadas pelo limite geral de linhas.

### Documentação

- ADR 0082, guia de autorização, referência de `authz`, protocolo da rodada cega, skills (uma frase) e [relatório da V1.9.3](docs/reviews/relatorio-v1.9.3.md). Provada só no laboratório (Clínica Piloto e VAmPI); nada contra produto real.

## [1.9.2] - 2026-11-16

### Corrigido

- `triage.json` gravado com BOM UTF-8 (marca que editores do Windows e alguns agentes acrescentam) fazia `hdast report` recusar o arquivo como corrompido e a régua da avaliação cair com `JSONDecodeError`. Os dois agora leem com `utf-8-sig`, como o perfil e a carta já faziam. Encontrado na rodada cega do GPT 6.1 Terra no VAmPI.
- Estudo de reutilização, `export-reuse` recusava dois casos legítimos das rodadas da V1.9.1. (1) Argumento textual de gerador: o `data-rules.yml` copiado do modelo oficial (`generator: email` com `domain: "teste.exemplo.com.br"`) era recusado, porque só valiam as opções e o padrão do catálogo. Agora também valem o mesmo valor que `products/_template/data-rules.yml` usa para o mesmo gerador e argumento (o arquivo é a fonte única; se faltar ou estiver malformado, a exportação falha fechada) e, para `email.domain`, um nome de host em domínio reservado para teste (`.test`, `.example`, `.invalid`, `.localhost`, `.local` (mDNS), `example.com`, `example.net`, `example.org` e subdomínios; rótulos `[a-z0-9-]` minúsculos, até 253 caracteres). Qualquer outro texto livre continua recusado. (2) Falso positivo de segredo: no VAmPI o valor fixo público do usuário admin é igual ao nome do papel declarado pela carta, então o `target.yml` "continha o segredo". A varredura agora ignora um valor de `secrets.fixed` igual (sem diferenciar maiúsculas) a um `role` de `expected.accounts`; valores gerados, fixos que não são papel e a senha continuam varridos. O conteúdo do OpenAPI não vai ao pacote. Sem mudança no contrato da CLI `hdast`.

## [1.9.1] - 2026-11-16

### Corrigido

- Pilha travada depois de editar o perfil: o proxy gerenciado prende o hash do `target.yml` e da aprovação no `stack up` e, mudando um deles, nega tudo com 403 `approval_changed`, sem a CLI dizer nada. Agora `preflight`, `probe`, `scan`, `authz`, `negative` e `run` falham **antes do primeiro pedido** com o código novo `STACK_STALE` (saída 4, sem valor de saída novo), que manda recriar a pilha (`stack down` e `stack up <produto>`). Um 403 `approval_changed` no meio da execução vira o mesmo erro, não achado nem recusa de escopo comum. `stack status` ganha `binding`, `stale_parts` e `stale_message`. O proxy continua falhando fechado com o hash completo ([ADR 0081](docs/adr/0081-pilha-desatualizada.md)).
- Skills `fix-reachability`, `run-scan`, `onboard-product` e `test-product`: depois de editar `target.yml` com a pilha de pé, recriar a pilha.
- Estudo de reutilização: `export-reuse` recusava porque o agente nunca ativava o conhecimento. As skills `run-scan` e `test-product` agora mandam `knowledge capture <produto> --run <run_id>` depois do `run`; o `export-reuse` aceita `knowledge.captured.yml` na falta do `knowledge.yml` (o ativo vence) e a recusa diz qual arquivo falta ou excede o limite ([ADR 0079](docs/adr/0079-exportacao-conhecimento-estudo.md)). A captura não ativa nada nem concede permissão.

### Documentação

- `evals/README.md`: o passo 1 deixa de usar `stack up --build` (exige aprovação) e passa a `docker compose build` com variáveis descartáveis só para a interpolação; o VAmPI é imagem por digest, sem build.
- Protocolo da rodada cega: origem do conhecimento do estudo de reutilização e a observação de que, no `claude -p` em workspace novo, o `permissions.allow` do `settings.json` é ignorado e as permissões vêm do `--allowedTools` (as negações valem).
- `docs/guides/problemas-comuns.md` e referências da CLI e dos códigos de saída: `STACK_STALE`.

### Documentação

- Protocolo da rodada cega completa (`evals/protocolo-da-rodada-cega.md`): o método exato das rodadas de 2026-11-15 (modelo, esforço, permissões, pedido, aprovação e retomada), o que anotar de cada rodada (tempo por etapa e por segmento, tokens, custo, comportamento, resultado, intervenções, falas e diário do agente), um script de ficha e onde arquivar.
- O protocolo da rodada cega vale para qualquer agente de código (Claude Code, Codex ou outro): separa o que é fixo em toda rodada do que é escolhido por estudo (ferramenta, modelo, esforço, permissões), lista os requisitos do agente (contexto limpo, retomada da conversa, horário por evento, conversão do transcript para o formato que o executor lê) e traz exemplos do Claude Code e do Codex.
- Na rodada cega, o agente que não é o Claude Code roda com acesso total (no Codex, `-s danger-full-access`). As violações são cobradas depois, pelo critério (a) da nota, que lê o transcript.

### Corrigido

- Login recusado pelo alvo: a mensagem passa a trazer o código HTTP e uma dica escolhida por ele. Num 415 (ou 400/422) ela aponta `auth.request_encoding` (formulário ou JSON), que é campo livre e não muda a aprovação. Uma rodada cega de 2026-11-15 parou no `preflight` porque o alvo só aceitava JSON e a mensagem dizia só "confira usuário e senha".
- Régua da avaliação cega: no modo seguro, sem nenhum `findings.json`, o critério de falsos alarmes deixa de valer nota cheia e fica fora da conta ("não se aplica").

## [1.9.0] - 2026-11-16

### Conhecimento executável conservador

- `knowledge capture`, `knowledge validate` e `knowledge diff`: referências tipadas a contas, dados, fluxos e autenticação, vinculadas às fontes e ao motor atual. Captura separada e ativação explícita; observação de efeito permanece proposta. Nenhuma observação concede permissão.
- Diário compartilhado de intenções antes das mutações de probe, authz e negative e dos lotes mutantes do ZAP. Resultado desconhecido bloqueia repetição entre comandos, com preservação de resultados parciais; resposta observada não declara sucesso de efeito.
- Par automático aceita 2xx mediante identificador novo nas leituras ou inventários anteriores das duas contas e leitura da dona com marcador novo. O marcador é gerado genericamente dentro do contrato; não exige alterar as regras de dados do laboratório. Sem as provas, o par fica não testado. Ausência visível não prova inexistência global em APIs com ocultação ou paginação oculta. Atribuição em massa sem leitura de efeito vinculada continua inconclusiva.
- Canal do estudo de reutilização com arquivos permitidos, receitas validadas, detecção de segredos/vazamento, manifesto, declaração na carta e chegada como propostas em contexto novo. O estudo e as rodadas cegas ficam para depois do merge, conforme o briefing.
- Provas T2 e T4 da V1.9 no laboratório: reutilização do conhecimento em novo contexto e authz dirigido nas duas APIs e modos; uma varredura completa por API com ritmo `legacy` (Clínica 98 achados do ZAP e 4 de authz; VAmPI 31 e 3). O verificador da T2 amarra leitura anterior, escrita, leitura posterior e snapshot à mesma receita, conta, mutação e período da rodada. Lacunas registradas no relatório: par com 200 no VAmPI e atribuição em massa V4.
- Quatro provas dirigidas das regras 90035/40008 passaram, sem nova T4 nesse diagnóstico. A causa histórica não foi integralmente demonstrada; `init --from-letter` e o padrão do modelo continuam `legacy`. Detalhes em [passo zero](docs/reviews/2026-11-16-v1-9-passo0.md).

## [1.8.0] - 2026-11-16

### Base conservadora da personalização

- Envelope derivado do perfil, estratégia versionada e plano concreto congelado, com os contratos propostos nos ADRs 0070 a 0074. A estratégia neutra preserva operações, política, limites e ritmo do executor serial.
- Consultas locais `strategy validate`, `strategy diff` e `plan --dry-run`; migração explícita com `strategy migrate`, cópia separada, comparação estrutural e preservação da autorização e da aprovação existentes. `strategy capture` cria cópia vinculada às fontes atuais e à versão do controle local da pilha gerenciada, sob trava e sem ativação automática.
- Vínculos das escolhas com ambiente, autorização, contas, planejamento, documentos e motor. A execução ativa confere fontes e versão observada antes do primeiro pedido ao alvo; indisponibilidade ou divergência recusa. Consultas secas e cleanup sem provedor recusam escolha preenchida; `choices: []` e perfis legados seguem operacionais. A versão não autentica a identidade da instância.
- Revalidação local da aprovação, perfil e stop por vigia com hash completo, retirando o I/O do caminho de concessão. Cada concessão recusa snapshot com idade superior a 200 ms desde o início da última verificação bem-sucedida; erro, encerramento ou mudança observada trava a saída. Autorização, janela e prazo continuam verificados por concessão. A imagem principal é reconstruída na subida para impedir reutilização de código antigo.
- O custo mediano de `_detect` no bind real caiu de 5,775922 para 0,026176 ms. As quatro T4 da rodada 3 passaram; A ficou mais rápida que a V1.7 nas duas APIs e B ficou dentro da nova previsão congelada. Não houve promoção no init: as contagens de SSTI na Clínica e Parameter Tampering no VAmPI divergiram sem explicação suficiente. Modelo, init e perfis existentes seguem `legacy` (ADR 0075).
- A regra DOM XSS 40026 permanece sem navegador e é exclusão pré-existente igual à linha de base nas comparações. Skills, referência e testes de cópia cega atualizados. O [relatório da rodada 3](docs/reviews/relatorio-v1.8-rodada3.md) complementa o [fechamento anterior](docs/reviews/relatorio-v1.8-fechamento.md) e o [registro inicial](docs/reviews/relatorio-v1.8.md), preservando as falhas e os limites das provas. Sem rodada cega nesta versão, conforme o briefing, e sem prova em produto real.

## [1.7.0] - 2026-11-16

### Ritmo serial e medição

- `scan.pacing: legacy | proxy` permite comparar o atraso fixo anterior com concessão no proxy. `legacy` continua padrão; `proxy` muda a aprovação e preserva força, regras, contas e limites.
- O proxy concede pela hora real, preserva fila limitada, reconfere travas após esperas e aplica recuo temporário de 429 sem repetir pedidos. Sua imagem precisa ser reconstruída.
- `metrics.json` recebe tempos de fila, identidade, concessão, resposta e recursos da CLI. Valores ausentes ficam nulos; tempos sobrepostos não são tempo de parede. O atraso efetivo do ZAP continua indisponível.
- A carta pode gerar uma declaração consultiva de tecnologias com origem e frase, protegida pela aprovação. Todas as regras continuam ativas, pois uma declaração errada pode não produzir sinal observável.
- `scan.json` e relatório expõem lacunas por regra; cobertura histórica desconhecida e recusas `rate_backoff` levam a cobertura parcial. Durante recuo 429, o proxy recusa imediatamente com o tempo remanescente em `Retry-After`, sem reter a conexão pelo recuo.
- As orientações distinguem cobertura desconhecida de execução interrompida e descrevem recusas do proxy sem atribuir o recuo temporário ao escopo. Gates locais finais: 9.604 testes aprovados; o [parecer independente](docs/reviews/validacao-v1.7.md) pede correção para o aceite integral. [Relatório da versão](docs/reviews/relatorio-v1.7.md).
- Os 12 controles T2 direcionados passaram. Em três pares T3 por API, reduções descritivas de mediana foram 45,0995% na Clínica e 60,9604% no VAmPI. DOM XSS 40026 `skipped` impede aceite e previsão completa; na T4 a B da Clínica ocorreu antes do congelamento, sem previsão prospectiva válida. [Protocolo e limites](docs/reference/scan-performance.md); sem rodada cega nem prova em produto real.

## [1.5.5] - 2026-11-15

### Achar mais e reduzir espera

- `hdast wait` acompanha uma execução em uma chamada bloqueante; sua saída 0 indica consulta bem-sucedida, inclusive no prazo, e o código da execução terminada fica em `data.exit_code`.
- `authz` amplia a conferência de atribuição em massa com leitura pela conta que escreveu, verifica CORS em uma amostra limitada de GETs e tenta formar pares horizontais com recursos criados durante a execução, somente com escrita autorizada pela carta.
- As skills pedem uma conferência final de anotações dos achados altos. A avaliação preserva o caso histórico `vampi-estrito`; a régua e os casos atuais devem refletir somente o que for comprovado.
- Gates e QA concluídos: 9.424 testes passaram e oito cenários de laboratório foram aprovados na Clínica Piloto e no VAmPI. Aceites B/D/F parciais: V3 comprovada; V4 do VAmPI não comprovada e POST 200 inconclusivo para o par novo. Sem rodada cega, varredura completa ou crAPI. Veja [provas e limites](docs/reviews/relatorio-v1.5.5.md).

## [1.5.4] - 2026-11-15

### Alcance confiável e varredura parcial

- O `probe` distingue a recusa esperada do login do perfil (`auth_rejected_expected`) de falhas de autenticação em operações protegidas. Alcance e sucesso 2xx são contados separadamente; a exclusão do login no `scan` e no `negative` permanece.
- Conflitos mostram campos candidatos pela resposta ou pelo contrato e pelas regras de dados; o resumo prioriza produtores pela quantidade de dependências bloqueadas, sem nomes específicos de produto.
- Falhas localizadas interrompem só a operação. Depois das tentativas de alcance, as skills seguem para a varredura parcial e registram operações e motivos que ficaram fora; relatório e painel mostram essas lacunas.
- Sem `findings.json`, quatro verificações de triagem dependentes de achados ficam `n/a` e saem da média. Reavaliações históricas e limites no [relatório da versão](docs/reviews/relatorio-v1.5.4.md).

## [1.5.3] - 2026-11-15

### Papéis que compartilham recursos (ADR 0057)

- A carta pode declarar `attack.authz_shared_roles` com a frase do dono; o perfil gerado recebe `authz.shared_roles`. A lista preenchida muda a aprovação; a lista vazia preserva a impressão digital anterior.
- `horizontal` e `horizontal_write` deixam de comparar contas do mesmo papel listado e registram `shared_role` em `not_tested`. As demais verificações não mudam. As skills orientam obter pares úteis de papéis não compartilhados sem inferir a regra do produto.
- Caso da avaliação, régua, dicas e skills atualizados no mesmo PR. Integração nos dois modos: sem alarme horizontal entre médicos, BOLA entre pacientes preservado no vulnerável e zero achado de autorização no seguro. Gates, evidências e limites no [relatório da versão](docs/reviews/relatorio-v1.5.3.md).

## [1.5.2] - 2026-11-15

Atualiza a avaliação e corrige os defeitos observados na rodada cega, sem acrescentar técnica de ataque. Evidências e limites no [relatório da versão](docs/reviews/relatorio-v1.5.2.md).

### Avaliação e autorização (ADR 0053)

- A carta da Clínica Piloto passa a autorizar explicitamente modo amplo, escrita entre contas, escrita de valores proibidos e varredura de `not_found`; inclui uma segunda conta médica e orienta como obter nomes existentes de documentos. O caso anterior permanece em `clinica-piloto-estrito`.
- A régua reconhece ZAP, `authz`, `proxy_signals` e `negative`, com categoria/técnica e operação. A fidelidade e o aprovador recusam permissões ausentes da carta e entradas malformadas.
- Novas rodadas lacram o caso completo. Rodadas antigas sem esse lacre exigem `--case-file` com o gabarito histórico; a nota registra a origem e o SHA-256. O caso histórico Terra amplo reproduz 7,18; a verificação dos segredos antigos não é reproduzível sem o lacre não arquivado.

### Alcance, sinais e orientação (ADRs 0054 a 0056)

- Paginação reconhecível de consulta usa a primeira página e um tamanho pequeno válido. Regras explícitas e valores encadeados continuam com precedência.
- O laboratório inclui `medico_b`, com referências `PILOT_MEDICO_B_*`, para exercitar `horizontal_write`. Compartilhamento legítimo de pacientes entre médicos continua sujeito à triagem dos alertas entre pares.
- Sinais de erro usam o contrato completo para resolver a operação, agrupam por operação/método/categoria e reúnem caminhos sem correspondência em um grupo por categoria. Fingerprints dos sinais passam à versão 2; os dos outros achados não mudam.
- `spec inspect` entrega hipóteses de encadeamento lista→detalhe e distribuição de leituras entre contas pares, no JSON e no texto. Não altera o perfil. Skills de cadastro e alcance passam a usar essas dicas.
- A cópia cega nega menções a Docker em qualquer posição do comando com regras conservadoras. A consulta de imagens que falha no `doctor` orienta repetir o próprio `doctor`. Eficácia das permissões no Claude Code em execução permanece sem prova nesta versão.
- A Definition of Done e o plano do ciclo exigem atualizar caso e régua da avaliação no mesmo PR que condiciona uma função à carta.

## [1.5.1] - 2026-11-15

Completa a V1.5 ("achar mais: entrada e erros") com as quatro partes ativas que a 1.5.0 deixou de fora. Provado por testes unitários, de contrato, QA independente e, com Docker, na Clínica Piloto nos modos vulnerável e seguro. **Nada foi provado contra produto real.**

### Mudança de uso

- `--include-outcome` do `scan` passa a **só escolher dentro do perfil** (`scan.include_outcomes`), como toda flag: antes ela alargava o que era atacado. Quem a usava sozinha precisa da lista no perfil, que vem da carta.

### Sinais de erro interno vistos pela cerca (ADR 0049)

- A cerca lê até 64 KiB de cada resposta do alvo (gzip e deflate com saída limitada; `br` e `zstd` não são lidos) e conta sinais de um catálogo fixo no domínio: erro de banco, rastreamento de pilha (Java, Python, .NET, Node, PHP) e página de depuração. Só observa: nunca nega por causa de um sinal e nunca grava corpo, trecho nem código de erro (a auditoria ganha só `signals` e `signal_skip`).
- Cada categoria vira achado com técnica `proxy_error_signal` (ids `S-`), em `error-signals.json` e numa seção do relatório; não se soma aos sinais passivos do ADR 0045. **Exige `hdast stack up --build`** para a imagem nova da cerca.
- Laboratório: no modo vulnerável, uma resposta 500 com rastreamento de pilha Java virou achado; no seguro, zero sinais. Cerca de 15 a 70 ms por resposta, medidos com a leitura incluída.

### Varrer as operações que deram "não encontrado" (ADR 0050)

- Campo novo `scan.include_outcomes` no perfil, vindo da carta (`attack.include_outcomes`, origem `carta` ou `pessoa`, com o aviso `OUTCOMES_ATTACK_EXTENDED`). `run --include-outcomes/--no-include-outcomes` e `scan --no-include-outcomes`.
- Achados e relatório marcam a semente (`seed_outcome`, fora do fingerprint) e listam as operações varridas a partir de um resultado que não era sucesso (`coverage.seeded_scans`). Operação com 404 sem varredura diz que a carta precisa autorizar.
- Laboratório: com `not_found`, uma operação que deu 404 no `probe` entrou no `scan` (cerca de 500 pedidos, nenhum `DELETE`).

### Valores que o esquema proíbe (ADR 0051)

- Comando novo `hdast negative PRODUTO --run ID` e sexto estágio do `run` (depois do `authz`, antes do `report`), ligado por padrão e **só lendo** (`--no-negative` desliga). Manda, um campo por pedido, valores que o OpenAPI proíbe (abaixo do mínimo, acima do máximo, tipo errado, obrigatório ausente, fora do enum, longo e curto demais), conferidos pela validação do ADR 0047. Aceitar (2xx) indica falta de validação; 5xx indica erro sem tratamento.
- Escrita só com `negative.allow_writes`, que vem da carta (`attack.allow_invalid_input_writes`, com `source: carta` e a frase). `DELETE` nunca. `PUT`/`PATCH` aceito é restaurado; `POST` aceito conta em `created_resources`. O valor enviado nunca é gravado.
- Saídas: `negative.json`, seção `negative` e `summary.negative_by_severity` em `findings.json`, seção do relatório, etapa no painel e em `metrics.json`. Orçamento por operação e total, que conta toda tentativa (inclusive repetição de 429).
- Laboratório (só leitura): 9 pedidos, todos recusados com 400. Com escrita na cópia descartável: 59 pedidos, 9 achados baixos de tipo errado aceito (número em campo de texto), restaurações registradas, nenhum valor nos artefatos.

### Envio de arquivo (`multipart`) (ADR 0052)

- O `probe` alcança operações `multipart/form-data` com arquivos sintéticos de lista fechada (texto, CSV, JSON, PNG de 1x1; no máximo 1 KiB, nunca executáveis) e a regra `synthetic_file` no `data-rules.yml`. `exchanges.json` guarda só nome, tipo e tamanho das partes.
- O `scan` de upload fica atrás de `attack.allow_upload_scan` (carta com a frase) e, por ora, é sempre pulado com `multipart_not_scannable`: medido no ZAP 2.17 real, a API de varredura recusa o pedido `multipart` (`url_not_found`).
- A Clínica Piloto ganhou `POST /api/documentos/enviar` (sem falha plantada, guarda em memória) para a prova.

### Correções (QA independente)

- O orçamento do `negative` era furado pelas repetições de 429; uma escrita cuja linha de base perdeu um campo obrigatório dava falsa segurança (agora `omitted_required_field`); o `negative` repetia os caminhos de saúde e de preparação; o plano do `scan` não normalizava o método; e-mail e CPF passavam inteiros no caminho dos sinais; orçamento negativo na função de plano; o painel ao vivo levantava erro sem estágios.

Relatório: [docs/reviews/relatorio-v1.5.1.md](docs/reviews/relatorio-v1.5.1.md).

## [1.5.0] - 2026-11-14

### Relatório e cobertura

- Sinais passivos de erro interno em JSON, Markdown e HTML, a partir das evidências já redigidas. Contagens fixas de resposta 5xx, possível rastreamento de exceção e possível erro de banco (ADR 0045).
- Operações sem varredura mostram o HTTP 404 observado no probe e o motivo de ausência registrado no scan. Se o motivo estiver ausente, o relatório diz que é desconhecido (ADR 0046).

### Inspeção offline do OpenAPI

- `spec inspect` indica incompatibilidades de tipo, obrigatoriedade, faixa, enum e comprimento em exemplos locais, sem imprimir os valores (ADR 0047).
- O resumo identifica operações com multipart e apresenta uma prova sintética em memória. Limites de inspeção das mídias ficam explícitos (ADR 0048).

### Portabilidade

- `AGENTS.md` orienta o uso com Codex. A preparação da cópia cega exclui os planos e briefings do coordenador e continua verificando vazamentos.

Detalhes e limites em [docs/reviews/relatorio-v1.5.md](docs/reviews/relatorio-v1.5.md).

## [1.4.0] - 2026-11-14

Versão do "achar mais: autorização". O teste de autorização entre contas passa a rodar sempre que se roda o `hdast run`, só lendo, e ganha seis verificações novas. Tudo que escreve no alvo continua desligado até a carta autorizar. Provado por testes unitários, de contrato e de QA independente, e com Docker na Clínica Piloto (vulnerável e seguro) por um teste de integração novo. **Nada foi provado contra produto real.**

### Teste de autorização por padrão e escrita só pela carta (ADR 0038)

- `hdast run` roda o estágio `authz` por padrão, com as verificações que só leem (`horizontal`, `excessive_data`, `vertical` em `GET`/`HEAD`, `anonymous_access`, `tampered_token`, `access_matrix` em leitura). `--no-authz` desliga; `--authz` continua aceito e é redundante. Com `--skip-scan` o estágio segue `skipped`.
- No `run`, falta de dado não derruba a execução: `exchanges.json` ausente ou ilegível vira `not_tested` (`exchanges_unavailable`), vazio vira `no_exchanges` e uma conta só vira `no_peer_account`. O `hdast authz` solto continua recusando `exchanges.json` ausente.
- Campo novo da carta `attack.allow_authz_writes`: ausente, nulo, `desconhecido` ou `false` valem `false`; `true` só com `source: carta` e a frase em `quote` (senão `AUTHZ_WRITES_NEEDS_LETTER`). Vira `authz.allow_writes: true` no perfil gerado por `hdast init --from-letter`, com o aviso `AUTHZ_WRITES_AUTHORIZED`. Sem ele, nada que escreve é enviado (`writes_not_authorized`), mesmo pedindo `--check mass_assignment`.
- Impressão digital da aprovação: as chaves novas do `authz` no valor padrão ficam fora do cálculo, então nenhuma aprovação existente se perde; ligar a escrita ou preencher qualquer chave nova muda o bloco `authz` e exige aprovar de novo. Conjuntos (`id_parameters`, `mass_assignment_methods`, a tabela) não dependem da ordem.

### Pedido sem login e token adulterado (ADR 0039)

- Verificações novas, só de leitura: `anonymous_access` (o mesmo `GET` sem credencial nem cookie) e `tampered_token` (JWT sem assinatura, com `alg: none` e com uma reivindicação a mais; token opaco ou chave embaralhados). Técnicas `authz_anonymous_access` (alta se o OpenAPI exige autenticação, média se não declara) e `authz_tampered_token` (alta; CWE 347 ou 287). Campo `variants` nos achados.
- Um 401 do token adulterado não faz novo login (`allow_reauth` no despachante). O token, original ou adulterado, nunca é gravado. Operações públicas, as declaradas anônimas e login, saúde e preparação ficam de fora.

### Campos proibidos tirados do OpenAPI e cadastro (ADR 0040)

- A atribuição em massa junta os campos declarados com candidatos derivados do OpenAPI (`readonly_in_input`, `response_only`, `name_in_input`; classes privilégio, saldo, preço, estado e outros). Campo de dono (`ownerId`, `tenantId`) nunca é derivado, só declarado. Valor de teste por tipo, que nunca tranca a conta. Teto de 400 escritas por execução.
- Também em `POST`: o efeito é lido pelo `GET` do recurso criado (id do `Location` ou do corpo) ou pela resposta do próprio `POST`. **Cada candidato testado num cadastro deixa um recurso criado no ambiente de teste** (`created_resources`); quem limpa é o `hdast cleanup` ou o reset do ambiente. 409 vira `create_conflict`.
- Campos novos do perfil: `authz.derive_mass_candidates`, `max_derived_candidates` e `mass_assignment_methods`. Severidade por classe (alta para declarado, privilégio e saldo; média para o resto).

### Escrita em recurso de outra conta e identificador na consulta (ADR 0042)

- Verificação `horizontal_write`: a conta par repete o `PUT`/`PATCH` sobre o recurso da conta dona com um campo marcador, a dona confere numa leitura e restaura. Só com `allow_writes`; nunca `DELETE` nem `POST`. 401, 403 e 404 contam como negação; 2xx sem efeito vira `accepted_without_visible_effect`; parada no meio vira `possible_unrestored_change`. Técnica `authz_horizontal_write` (CWE 639).
- O BOLA de leitura passa a trocar de conta também com o identificador na consulta (`/consultas?pacienteId=2`), com valores que o `probe` viu, nunca inventados. Campo novo `authz.id_parameters`. O motivo `no_path_parameter` passa a se chamar `no_object_identifier`.

### Tabela "quem pode o quê" (ADR 0041)

- Bloco novo `authz.access_matrix` (por operação, os papéis que podem e os que não podem), aprovado por uma pessoa no `profile approve`, cujo resumo lista a tabela inteira. Verificação `access_matrix`: cada célula "não pode" é testada com uma conta do papel; 401/403 passam, 2xx falha (técnica `authz_access_matrix`, CWE 285). Papel fora da tabela não é testado. A `vertical` pula as operações cobertas pela tabela.
- `hdast authz PRODUTO --draft-matrix [--run ID]` grava um rascunho (`authz-matrix.draft.yml`) na pasta do produto, fora do perfil: não envia nada ao alvo e nunca preenche "não pode". Erro novo `AUTHZ_CONFIG_INVALID` (saída 2) para operação ou papel inexistente. Subseção "Tabela quem pode o quê" no `report.md` e no `report.html`.

### Refatoração

- `application/authz/runner.py` (693 linhas) dividido em envio, verificações de leitura, atribuição em massa e um mapa de verificações (`CHECK_RUNNERS`), sem mudar comportamento.

### Correções

- Portão do script de limpeza: palavra reservada (`DROP`, `TRUNCATE`...) não vale mais como apelido da tabela. Um teste de propriedade achou `DELETE FROM PEDIDO DROP/* ... */WHERE ...` aceito; o comentário não chegava ao banco e o Oracle recusaria, mas o portão precisa falhar fechado sozinho.
- Do QA independente (nenhum defeito grave nem médio): a ordem de `id_parameters` mudava a impressão digital; a `|` vinda do OpenAPI quebrava as tabelas do `report.md` (agora escapada em toda célula); o rascunho da tabela estragava caracteres acima de U+FFFF.
- Textos do `doctor`, do painel e do relatório que diziam que o teste entre contas era opcional.
- Proxy de escopo (ADR 0043, provado no laboratório): um hook do proxy falhava em toda conexão de saída (`Cannot change server.address on open connection`) e, com a conexão reaproveitada, um pedido em cada seis vindos do ZAP ficava parado até estourar 15 s. O proxy agora responde `Connection: close` (uma conexão por requisição entre o ZAP e o proxy) e o hook saiu; o IP conferido continua fixado na conexão de saída. Na Clínica Piloto, `anonymous_access` passou de 16 para 19 operações testadas, `tampered_token` de 8 para 18 e o `authz` de 224 s para 64 s. **Exige `hdast stack up --build`** para valer; o efeito numa varredura longa (`lab_full`) não foi medido.
- Atribuição em massa (ADR 0043): um campo que o corpo de entrada já declara só vira candidato derivado quando o nome é de privilégio. Um campo legítimo da entrada (como um valor obrigatório do cadastro) ecoado pelo servidor gerava falso positivo no modo seguro. O `fields` do achado não repete mais o campo enviado, o que muda o fingerprint desses achados.

### Documentos e testes

- Guia novo [docs/escada-de-testes.md](docs/escada-de-testes.md): até que degrau testar cada mudança e os comandos do ataque direcionado.
- Teste de integração novo `tests/integration/test_lab_authz.py` (`lab_fast`): o `authz` completo na Clínica Piloto, vulnerável e seguro, com a escrita ligada numa cópia descartável do perfil.
- Relatório da versão: [docs/reviews/relatorio-v1.4.md](docs/reviews/relatorio-v1.4.md).

## [1.3.0] - 2026-11-14

Versão do uso seguro e fácil: uma trava por pilha, a carta de autorização em formulário, a aprovação do escopo por uma pessoa e a entrevista inicial nas skills. A trava foi provada com Docker uma vez, no laboratório; o resto foi verificado como código e testes, e **não** foi provado contra produto real, nem o `hdast profile approve` num terminal de verdade, nem a entrevista com uma pessoa, nem uma rodada cega no fluxo novo.

### Mudança incompatível de uso: aprovação obrigatória

- Todo perfil existente precisa ser aprovado **uma vez por uma pessoa** (`hdast profile approve <produto>`, em terminal interativo) antes de `preflight`, `probe`, `scan`, `authz`, `run`, `cleanup` e `stack up`; sem isso esses comandos recusam com `SCOPE_NOT_APPROVED` (saída 3). Não há flag, variável de ambiente nem modo "laboratório" que pule a conferência. A aprovação vale até um bloco de proteção mudar. No laboratório: `hdast profile approve clinica-piloto`. Os formatos de envelope e de perfil não mudaram (só campos novos).

### Trava exclusiva por pilha (ADR 0035)

- `stack.lock` na pasta de estado (`HDAST_STATE_DIR`), criado de forma atômica e exclusiva. `probe`, `scan`, `authz` (fora do `--dry-run`), `run`, `stack up` e `stack down` tomam a trava na partida, antes de tocar o alvo, e a soltam sempre (sucesso, erro, `KeyboardInterrupt`).
- Pilha ocupada: erro `STACK_BUSY`, **código de saída 8 (`BUSY`, novo)**, com a mensagem dizendo quem ocupa (comando, produto, id, processo e início). Trava órfã (processo morto) é retomada com aviso; trava ilegível recusa. `hdast stop` e `hdast stack status` nunca são bloqueados; `stack status` ganha `data.lock` (`state` `held`, `orphan` ou `unreadable`, mais comando, produto, id, processo, início e mensagem; nulo com a pilha livre).
- Domínio puro em `domain/stack_lock.py` (`judge_lock`); relógio e "processo vivo?" entram por porta. A consulta de processo vivo só foi implementada para o Windows.
- Provada com Docker no laboratório uma vez: `tests/integration/test_lab_stack_lock.py` (segundo `probe` recusado com saída 8 enquanto um `scan --only` rodava na Clínica Piloto real; o mesmo comando depois do fim do primeiro saiu 0).

### Carta estruturada (ADR 0036)

- `carta.yml`: cada resposta tem a forma `{value, source}` com `source` `carta`, `pessoa` ou `desconhecido`. Comando novo `hdast init <produto> --from-letter <carta.yml> [--check]`: a CLI gera os blocos `environment`, `openapi`, `scope`, `limits`, `auth` e `scan.strength` do perfil; `--check` confere sem criar nada. O agente não escreve à mão o que a CLI gera.
- Pendência recusa a carta inteira com `LETTER_REJECTED` (herda de `CONFIG_ERROR`, saída 2) e `data.issues` (`{field, code, message}`; códigos `MISSING`, `UNKNOWN`, `INVALID_VALUE`, `PLACEHOLDER`, `GATE_DENIED`, `WIDE_NEEDS_LETTER`, `PRODUCT_MISMATCH`, `PROFILE_REJECTED`, `AUTHORIZATION_EXPIRED`). Os portões (ambiente de teste, dados sintéticos, autorização vigente) respondidos "não" ou desconhecidos recusam tudo; `scope.path_mode: wide` só com `source: carta` e citação.
- Carta com `valid_until` anterior a hoje (UTC; o último dia vale inteiro) é recusada com `AUTHORIZATION_EXPIRED`. A carta pronta traz `data.warnings` (não bloqueiam e não mudam o perfil: permissão em `/**`, `DELETE` autorizado, `deny_paths` vazio e validade acima de um ano) e `data.example_data` (valores de exemplo tirados da carta para as regras de dados).

### Aprovação humana do escopo (ADR 0037)

- `hdast profile approve <produto>`: só uma pessoa, em terminal interativo (`--json` e terminal ausente são recusados, nada é gravado); mostra o resumo dos blocos e o que mudou desde a aprovação anterior. `hdast profile approval <produto>` só lê e diz `approved`, `not_approved`, `changed` (com os blocos) ou `invalid`; o agente pode rodá-lo. `profile validate` ganha `data.approval`, informativo (não entra em `runnable`).
- Impressão digital (SHA-256 de uma forma canônica, no `domain/scope_fingerprint.py`), na **versão 2 do cálculo**: entram `environment`, `scope` (permissões, caminhos proibidos, modo de caminho, autorização e janelas), `limits`, as partes de `auth` que dizem para onde vão as credenciais e com que contas, e `scan`, `authz` e `cleanup` inteiros. Ficam livres só os ajustes de alcançabilidade (`probe`, `auth.csrf`, `auth.account_map` e semelhantes, `openapi`). O conteúdo do script de limpeza não entra no cálculo (o script é de autoria humana e a leitura de arquivo não é do domínio). A aprovação mora em `approvals/<produto>.json` na pasta de estado, negada ao agente em `.claude/settings.json`.
- A conferência está no ponto central de carga do perfil (`ApprovedProfileRepository`); erro `SCOPE_NOT_APPROVED` herda de `HarnessError`, sai com **3** (sem código de saída novo) e diz quais blocos mudaram. `stack down`, `stack status` e `stop` não são bloqueados. Portas novas `ApprovalStore` e `ApprovalPrompt`.
- Avaliação cega: `python -m evals.runner approve --out <rodada>` (coordenador, fora do agente) confere o perfil contra a carta do caso e aprova; a rodada para no primeiro comando que toca o alvo.

### Skills e guias

- Entrevista estruturada numa rodada só nas skills (portões, endereço, escopo, modo do caminho, janela, limites, contas, força do ataque, dados de exemplo), resumo do que será atacado antes de atacar, consulta de `hdast profile approval` antes de tocar o alvo e tratamento de `STACK_BUSY` (esperar ou perguntar, nunca contornar). O guia de autorização passa a usar um produto fictício no exemplo; `primeiro-uso.md` ganha o passo de aprovar o perfil.

### Documentos e verificadores

- Documentos desatualizados corrigidos. `tests/contract/test_docs_links.py` falha com link relativo (arquivo ou âncora) que não existe. `tests/contract/test_letter_guide.py` e o teste de vazamento percorrem toda a cópia entregue ao agente cego e barram caminho proibido, isca e termo de gabarito de cada caso.

### Correções

- A redação de segredos apagava a versão do protocolo (`HTTP/1.1`) da linha de requisição quando o endereço terminava em `token`, `basic` ou `bearer`. Era perda de evidência, não vazamento.
- Do QA independente (aprovado com ressalvas): `scan`, `authz` e `cleanup` inteiros entram na impressão digital (editar `fail_on`, `disable_rules`, `public_operations`, tetos de tempo ou o alvo da limpeza mantinha "aprovado"); a recusa da trava diz a verdade sobre `stop` e sobre PID reaproveitado; carta com autorização vencida é recusada; português das mensagens novas e das skills; o teste de vazamento cobre toda a cópia cega e tirou exemplos que citavam a isca; `.claude/settings.json` nega ao agente gravar na pasta de aprovações. Relatório: [docs/reviews/relatorio-v1.3.md](docs/reviews/relatorio-v1.3.md).

## [1.2.0] - 2026-11-14

Versão do painel da execução, das medições e do diário de comandos. Tudo medido só em laboratório: nada disto foi provado contra um produto real, e a V1.2 não foi verificada com Docker nesta entrega.

### Painel da execução (ADRs 0032, 0033 e 0034)

#### Fundação e abas Resumo e Etapas (ADR 0032)

- Comando novo `hdast panel PRODUTO [--run ID] [--json]`: gera as páginas HTML do painel do teste em `runs/<run_id>/panel/` (`summary`, `stages`, `findings`, `coverage`, `terminal` e `time-and-tokens`) a partir dos arquivos da execução (`run.json`, `manifest.json`, `probe.json`, `scan.json`, `findings.json`, `authz.json`, `metrics.json`; todos opcionais) e do perfil e do OpenAPI do produto. Sem `--run`, usa a execução mais recente do produto. `hdast report` e `hdast run` também o geram no fim; falha ao gerar o painel nunca derruba esses dois (vai para o log).
- Sem JavaScript, sem recurso externo, CSP por `<meta>`, todo texto do alvo escapado por `html_safe`; tema escuro com claro conforme o aparelho; dado ausente aparece como "não medido", nunca zero; nunca "seguro" nem "aprovado".
- Abas Resumo e Etapas fiéis ao desenho (`docs/design/execution-panel/`), com os estados "sem falha grave", "parou no meio" e "erro". As outras quatro abas vieram nas entradas seguintes (hoje nenhuma é provisória).
- Modelo de visão `PanelView` (`domain/panel_model.py`) com tudo que as seis abas precisam e dois ganchos opcionais, `commands` (diário de comandos) e `explanations` (catálogo de explicação de falha); registro de páginas em `domain/panel_pages.py`.
- Porta nova `PanelFiles` (leitura dos arquivos da execução e gravação das páginas) e `PanelRefresher` (chamada por `report` e `run`). `Operation` do OpenAPI ganha `summary` (opcional) para o nome simples da função. Nenhum campo novo no perfil, no `findings.json` nem no envelope de `report` e `run`.

#### Abas Falhas e Terminal (ADR 0032)

- Aba **Falhas** (`findings.html`): lista das falhas graves com âncora por falha (`findings.html#F-...`, usada pelos links do Resumo), título do catálogo, etiqueta cinza com o nome técnico, medidor de confiança de três degraus, "o que aconteceu", "por que importa", "o que fazer" com quem faz cada passo, a prova (pedido e resposta como texto, com o aviso) e "Como reproduzir à mão" com `$BASE_URL`, `$TOKEN` e o apelido da conta. Os demais achados aparecem agrupados, com link para o `report.html`. Falha do teste entre contas não tem reprodução à mão (a página diz por quê). Estados: falha a confirmar, nenhuma falha grave, sem `findings.json`, prova cortada, pedido com corpo.
- Aba **Terminal** (`terminal.html`): cada comando do diário, em ordem, com hora, comando cru, frase que o traduz, estado (palavra), duração e resposta resumida (aberta nos comandos parciais e com erro). Sem diário para o teste, diz que o diário começou na versão 1.2; linhas corrompidas puladas são contadas. A aba Resumo passa a usar o dado real.
- Ganchos ligados: `application/panel_hooks.CatalogPanelHooks` lê o diário (`load_journal_for_run`, que agora devolve `RunJournal` com as linhas puladas) e o catálogo de explicação. `domain/panel_journal.py` (etapa de cada comando por tabela fixa, comando cru, resposta resumida) e `domain/panel_catalog.py`. Modelo: `PanelJournal`, `PanelAction`, `PanelExplanation.why_it_matters` e `.actions`, `PanelFinding.repro` e `.proposed_confidence`, `PanelView.commands_skipped`.
- Regra de "prova forte" unificada em `finding_confidence.confidence_step`: evidência gravada, trecho de prova do ZAP e nem o ZAP nem o agente indicam falso positivo; a confiança proposta pelo ZAP não entra. Medido na Clínica Piloto: 2 prova forte e 1 a confirmar.
- `manual_repro`: quando a redação do `findings.json` comeu o caminho do endereço (`host:***`), o caminho é refeito pelo modelo da função e o dado traz `target_damaged`; novo campo `attack`.

#### Abas Cobertura e Tempo e tokens (ADR 0032)

- Aba Cobertura (`coverage.html`, `domain/panel_coverage.py` e `panel_fence.py`), fiel ao desenho: quadro de números e barra, mapa das funções por parte do sistema (forma e palavra da lista fechada, motivo da função não testada, link para a âncora da falha grave em `findings.html`), a cerca (passaram, barrados por forma do endereço e por apontar para fora, "chegaram a lugar proibido", motivos em português com o código ao lado, aviso de cobertura parcial, modo estrito x amplo em uma frase) e "O que ficou de fora" com o risco e quem destrava. Estados: modo amplo, tudo testado e tráfego não medido (traço com a explicação, nunca zero).
- Aba Tempo e tokens (`time-and-tokens.html`, `domain/panel_time.py`, `panel_rules.py` e `panel_bars.py`): números em destaque, tempo e tokens por etapa (barras em branco e cinza, com `role="img"` e `aria-label`), regras do ZAP mais lentas com pedidos, regras puladas ou interrompidas com o motivo, funções que mais demoraram, lacunas sem tráfego e regras desligadas. Sem `metrics.json` cada quadro mostra o traço e a explicação.
- Tokens do agente: a CLI não os mede. Quando `agent-metrics.json` (`schema_version` 1, gravado pela avaliação cega) está na pasta da execução, o painel o lê por modelo tolerante (`domain/agent_metrics.py`: campo desconhecido ignorado, ausente vira `None`) e mostra o total (entrada, saída e cache gravado; o cache relido não entra na soma), o modelo e os tokens por etapa (leitura e cadastro na conferência; alcance; varredura; triagem nos achados; o resto em "outras tarefas do agente"). Arquivo ausente, malformado ou de outra versão vira "não medido", nunca erro.
- Porta `PanelFiles` ganha `read_agent_metrics`; `PanelSources` ganha `agent_metrics`; `PanelMeasurements` ganha `disabled_rules`, `tokens_breakdown` e `agent_model`; cada etapa do `PanelView` passa a carregar seus tokens quando o arquivo existe. `Panel._read_all` passa `agent_metrics` ao montar o `PanelSources`.

#### Diário de comandos (ADR 0033)

- Toda invocação do `hdast` grava uma linha em `<pasta de estado>/journal/<produto>.jsonl` (`HDAST_STATE_DIR`; fora do repositório e de `runs/`; comandos sem produto em `_sem-produto.jsonl`): início e fim, subcomando, flags (valor sensível `***`, texto livre redigido), produto, `run_id`, código de saída, estado (`ok`, `parcial`, `erro`), código do erro e um resumo curto do envelope (contagens e identificadores; nunca corpo do alvo). `secret set` e `secret delete` registram só o subcomando e o NOME. O registro é feito em `run_app`, o ponto único de todo comando; falha ao gravar vira aviso no log e nunca derruba o comando. Linha com `schema_version`; leitura tolerante (linha corrompida é pulada e contada).
- `application.command_journal.load_journal_for_run(store, product, run_id)` devolve os comandos de um teste (do fim do teste anterior até o fim dele). Porta `CommandJournalStore`, adaptador `adapters/storage/command_journal.py`. `domain/command_translation.py`: frase em português simples de cada comando, com teste que falha se a CLI tiver comando sem tradução.
- `domain/finding_explain.py`: catálogo fixo de explicação de falha (título, o que houve, por que importa, o que fazer com quem faz, nome técnico) por regra do ZAP, CWE e técnica do `authz`, com explicação genérica honesta para tipo desconhecido. `domain/finding_confidence.py`: degrau de confiança (`a confirmar`, `prova forte`, `confirmada`; o terceiro só com confirmação de pessoa, que o `triage.json` ainda não registra). `domain/manual_repro.py`: dados de "Como reproduzir à mão" com `$BASE_URL`, `$TOKEN`, apelido da conta e CPF, e-mail e telefone mascarados.
- Os testes que rodavam `run_app` passam a gravar o diário na pasta de estado isolada pela fixture de `tests/conftest.py`. Referência: [docs/reference/command-journal.md](docs/reference/command-journal.md).

#### Índices e página ao vivo (ADR 0034)

- `hdast panel` agora também refaz `runs/index.html` (Produtos) e `runs/history-<produto>.html` (Histórico de um produto) sempre que gera um painel; `hdast report` e `hdast run` fazem o mesmo. Modo explícito: `hdast panel --index` (sozinho). Execução ilegível ou de versão antiga vira linha "sem dados" ou "dados incompletos", nunca some nem derruba o índice. "O que mudou desde o anterior" compara as falhas graves pelo código curto com o teste anterior do mesmo tipo.
- O caminho do alto de toda página do painel (`hdast / Produto / data`) passou a ser link relativo (índice, histórico e Resumo).
- `hdast run` regrava `panel/live.html` a cada etapa e a cada função da varredura, sem JavaScript, com `<meta http-equiv="refresh" content="15">` e o horário da última gravação; ao fim a regrava sem a recarga, ligando para `summary.html` e `stages.html`. Falha ao gravá-la nunca derruba o `run`. A política de conteúdo (CSP) do painel não mudou.
- Portas novas `PanelIndexFiles`, `RunLive` e `ScanLive` (`application/panel_index_ports.py`); `RunnerDeps.on_progress`, `Scan(live=...)` e `RunPipeline(live=...)` opcionais.

#### Correções depois da revisão independente de QA

- **Etapa onde parou, de uma fonte só.** Um teste sem `run.json` aparecia como erro no Resumo e como "Nada travou" nas Etapas. `settle_stopped` (`domain/panel_build_stages.py`) marca a etapa onde o teste parou como cortada (amarela), o veredito, o Resumo e as Etapas leem o mesmo estado, e uma etapa com erro nunca fica verde. `PanelStage.unreached` diz que ela é "cortada" só porque o teste acabou antes (o histórico não a conta como etapa que rodou). A conferência de um `manifest.json` com `status: not_ready` é a etapa cortada.
- **Painel final já mostra o comando que o gerou.** A linha do comando só era gravada depois de o painel estar pronto, e o Terminal dizia "anterior à versão 1.2". `run_app` agora refaz o painel do teste (e os índices) depois de gravar a linha, para `run`, `report` e `panel` que terminaram com sucesso (`cli/journal_recording.py`); o diário não ganhou linha "em andamento". O estado vazio diz só o que sabe: "O diário de comandos existe, mas não tem nenhum comando deste teste" (`PanelJournal` com zero comandos) quando há diário do produto, e "anterior à versão 1.2" só quando não há diário nenhum.
- **Recorte do diário.** O `stack up` e o `stack down` gravam o `run_id` da pilha (de antes do teste); o recorte o tratava como "outro teste" e deixava o `stack up` de fora. `slice_for_run` passa a ignorar o `run_id` dos comandos `stack` e `stop`.
- **Página ao vivo na pasta certa e conferência do `run` fora do índice.** O preflight abre uma pasta só dele e o `probe` abre a da execução de verdade; a página era gravada na primeira e o índice a listava como um teste com erro. A página ao vivo agora começa na varredura (já na pasta certa), e o índice esconde a pasta que um `run.json` cita como a conferência de outra (`PanelIndexer._absorbed`).
- **Aba Falhas: comparar pelo que prova.** Falha por tempo (`(Time Based)`) compara pela demora (3 vezes, comparando com o pedido normal), nunca pelo corpo da resposta; falha cuja resposta gravada não mostra a falha não diz "a falha continua". O catálogo ganha a variante por tempo de injeção de SQL e de comando do sistema (sem o passo de esconder o erro do banco). A linha "O agente suspeita de falso positivo" mostra o campo da triagem e a nota do agente juntos, sem selo verde quando há nota. `manual_repro.is_time_based` e `sleep_seconds`.
- **Concordância de número.** `pick` em `panel_format.py` (irmã de `plural`) para "apareceu 3 falhas", "da função que não respondeu", "e mais 1 motivo menor", legendas dos números em destaque e demais frases geradas.
- **Mesmos números com o mesmo nome.** `PanelVerdict.functions_planned`: as atacadas são contadas das planejadas pela varredura (Ao vivo, Resumo, Etapas e histórico); o alcance diz de quantas funções do sistema tentou; a Cobertura chama o total de "funções do sistema (no Swagger)".
- **Cobertura.** Funções de mesmo nome ganham método e caminho; `deny_paths`, `scope.allow` e os códigos da cerca vêm depois da frase simples, em etiqueta cinza (`html_safe.tagged`).
- **Falhas.** O endereço volta com o nome do parâmetro (`/crm/{crm}`) tirado do Swagger da mesma operação (o relatório guarda `{}`); dois grupos de mesmo título (campos `XSRF-TOKEN` e `token`) dizem o campo que os separa (`PanelGroup.parameter`).
- **Terminal.** O id da execução deixa de ser mascarado (`run.is_run_id`, usado pela redação; token de verdade no mesmo campo continua mascarado); a data aparece no primeiro comando de um dia novo.
- **Ao vivo.** A faixa das etapas empilha abaixo de 640 px; o prazo vira "parou porque chegou ao tempo máximo combinado, de N min" (`plain_stop_reason`, também no Resumo e nas Etapas); a varredura cortada diz até onde chegou e a etapa feita depois dela fica em amarelo, "só com o que veio até aí".
- **Histórico.** "Só conferência" e "só alcance" mostram traço em "mudou desde o anterior"; o gráfico conta só varredura completa; uma só hora de início por teste (a do `run.json`, ou o carimbo do id), igual na tela e no índice.

### Medições (ADR 0031 e `evals`)

#### Medição da execução (ADR 0031)

- Toda execução que chega ao `hdast report` ou ao `hdast run` grava `runs/<run_id>/metrics.json`: tempo por etapa (`preflight` só no `run`; etapa não executada é `null`), por operação varrida (reaproveita `scan.json`), **por regra do ZAP** (tempo em ms, pedidos, alertas e estado, somados na execução e por operação), tráfego do proxy (liberados, recusados por motivo) com as "lacunas" de mais de 10 s sem pedido e as regras desligadas pela política com o motivo. Só números e identificadores; sem dado do alvo nem segredo. `hdast report` cita o arquivo na saída humana.
- O `scan` grava `rule-stats.json` (dado bruto por regra e por operação, lido de `ascan/view/scanProgress` ao fim de cada varredura; forma real do ZAP 2.17.0). Falha na coleta ou na gravação não derruba a varredura: a operação fica marcada como indisponível, com o motivo, e o log estruturado registra. `scan.json` não mudou.
- `ScanControl.scan_rules`, `RunArtifacts.write_rule_stats`, `read_rule_stats` e `write_metrics`, porta `RunMetricsRecorder`; `run.json` passa a listar `rule-stats.json` e `metrics.json` em `artifacts` quando existem.

#### Medição do agente na avaliação cega

- Avaliação cega: `python -m evals.runner measure --out <rodada>` lê o transcript e grava `agent-metrics.json` com a duração, os tokens (entrada, saída e cache), os turnos e as chamadas de ferramenta, e, por etapa (leitura, cadastro, alcance, varredura, triagem, outro), os segundos pensando e esperando, os tokens e a contagem de cada subcomando `hdast`. A etapa sai de uma regra determinística sobre os comandos, sem modelo de linguagem. Inclui sinais de volta (comandos repetidos, falha seguida de nova tentativa, arquivos lidos mais de uma vez), só com nomes e contagens, e recusa gravar se um segredo da rodada aparecer. Do `metrics.json` das execuções (ADR 0031, `schema_version` 1) copia só um resumo tipado: segundos de cada etapa da CLI, lacunas do proxy e tempo por regra do ZAP.
- Avaliação cega: `measure --save <rótulo>` guarda o resumo da rodada em `evals/measurements/` (agent-metrics, nota, `metrics.json` das execuções e `meta.json`), sem sobrescrever pasta existente, e `python -m evals.runner compare <A> <B> [--json]` mostra as diferenças, com `n/d` onde falta dado: totais, etapas do agente, segundos de cada etapa da CLI, total de lacunas e as 10 regras do ZAP com maior diferença de tempo (por `plugin_id` e nome). O `metrics.json` é lido por um modelo tolerante: arquivo ausente, malformado ou de versão desconhecida vira `n/d`. Primeira medição: cinco rodadas da V1.0 e uma da V1.1.

### Corrigido: redação destruía porta e caminho de endereços sem segredo (desde a V1)

- `_LONG_TOKEN` tratava `8080/api/medicos/busca-por-nome` (porta e caminho, 24 caracteres ou mais com algum dígito) como token e trocava por `***`; o `reproduce_curl` herdava o endereço cortado (`"$BASE_URL"/` ou `'/?nome=%27'`). Agora a regra de sequência longa vale por trecho do caminho dentro de endereço (a barra separa trechos), `host-com-token:8080` deixa de ser lido como par `nome: valor`, e ` HTTP/1.1` não é mais engolido ao mascarar `?token=...`. Valor sensível em consulta, credencial no endereço, JWT e `Bearer` continuam mascarados. Achados já gravados continuam com o endereço e o `curl` corrompidos (a redação roda na gravação); não há migração, só uma nova varredura os refaz.

### Corrigido: isolamento dos testes

- Os testes deixam de depender do ambiente da máquina: com uma pilha Docker do hdast no ar, 12 a 27 testes de `tests/contract/test_cli_scan_report.py` falhavam (o `probe` saía com código 4) por ler o estado real da pilha. Uma fixture `autouse` em `tests/conftest.py` limpa toda `HDAST_*` e aponta `HDAST_STATE_DIR` para uma pasta vazia por teste; `tests/contract/test_state_isolation.py` prova o isolamento.

### Design do painel guardado em `docs/design/execution-panel/` (só documentação)

- `docs/design/execution-panel/`: desenho final do painel da execução, aprovado pelo dono em 2026-11-14 e implementado na 1.2.0, com as diferenças listadas em `docs/roadmap.md` (seção "Diferenças entre o painel e o desenho"). Telas em HTML parado (produtos, histórico, resumo, ao vivo, etapas, falhas, cobertura, terminal, tempo e tokens), sistema de design (cores, tipografia, espaço, `tokens.css`, componentes, movimento, estados, formatos) e, no `README.md`, as decisões tomadas, os dados que ainda não existem e o que pede ADR. Nenhum código da CLI mudou.

## [1.1.0] - 2026-11-13

A V1.1 (ADRs 0026 a 0030) foi medida em laboratório neste dia: relatórios em [docs/reviews/2026-11-13-lab-v1-1-cerca.md](docs/reviews/2026-11-13-lab-v1-1-cerca.md) e [docs/reviews/2026-11-13-lab-v1-1-authz.md](docs/reviews/2026-11-13-lab-v1-1-authz.md). Versão do pacote: 0.1.0 para 1.1.0 (`pyproject.toml`, `uv.lock`).

### V1.1, laboratório: o que foi provado e o que a medição achou

- **Cerca (ADR 0026), proxy e ZAP reais:** a isca em `scope.deny_paths` foi atacada por 45 formas de caminho pelo proxy de escopo real nos dois modos: `isca_calls` ficou em 0 (estrito e amplo); o caminho chega ao alvo byte a byte (o proxy não recodifica). Estrito contra amplo na Clínica Piloto: o amplo achou 1 falha a mais (H9, travessia de caminho) e 3 variantes a mais do H8, com 2,25 vezes mais tempo de varredura; no modo seguro com amplo, 0 achado alto; no VAmPI o amplo não achou nada a mais.
- **Prazo da pilha (ADR 0028):** provado com `max_duration_minutes: 3` em cópia do perfil (o `run` parou aos 180,6 s, saída 3, 4 min 42 s depois do `stack up`). `probe.setup_path` provado no VAmPI (perfil de `lab/vampi` migrado de `health_path: /createdb` para `setup_path`, alcançabilidade 1,0). `doctor` provado com Docker real e com porta ocupada.
- **Teste de autorização (ADR 0027) na Clínica Piloto:** H5, H6 e H7 achados no vulnerável (3 achados altos) e zero no seguro. BFLA vertical não foi medido (sem conta de papel menor).
- **Laboratório (`lab/pilot`):** falhas plantadas H8 (injeção de SQL cega por tempo em parâmetro de caminho), H9 (travessia de caminho, só com `%2f`) e H10 (injeção com aspa, controle positivo), endpoint lento de 2 s e a isca `/api/isca/**` (conta `isca_calls` e `isca_mentions`); teste diferencial cerca x servidor (Spring e Flask: nenhuma forma fora do modelo, exceto a coerção numérica abaixo); testes de integração `test_lab_path_scope.py` e `test_lab_path_differential.py`.
- **Brecha conhecida, não corrigida (pede ADR):** o servidor coage o tipo do parâmetro de caminho (`/api/convenios/01`, `+1`, `%2b1`, `0x1`, dígito Unicode como `%D9%A1` chegam ao mesmo recurso que `/api/convenios/1`), formas que o modelo da cerca não conhece, nos dois modos. Um `deny_paths` sem curinga não as cobre. Mitigação hoje: negar com curinga.

### Corrigido nas medições de laboratório

- `report.html` não mostrava o modo de caminho, o aviso de cobertura parcial de injeção em caminho nem os motivos granulares (só o `report.md`); corrigido, com 3 testes.
- `authz`, falso "seguro" em lista vazia (H7 passou despercebido na primeira rodada): vira `not_tested` com `no_sample_data` (já descrito abaixo).
- Laboratório: o firewall do Spring recusava `%2f` mesmo com o Tomcat em `passthrough` (H9 inalcançável); o atraso simulado do H8 reagia a qualquer "sleep 15" e gerava falso alarme de template; `isca_calls` contava qualquer pedido que citasse a isca (agora só o método da isca); parâmetros de caminho novos não eram varridos até ganharem constantes em `data-rules.yml`.

### Corrigido: cópia cega da avaliação

- A cópia do repositório para a avaliação cega deixa de fora os worktrees de outros agentes e os nomes de campo do laboratório (commit 2c68b4c).

### V1.1, authz: parada depois do PUT não esconde alteração

- Atribuição em massa: se a janela fechar, o prazo vencer, a trava acionar ou o proxy falhar depois do `PUT` com o campo extra, a restauração ainda é tentada pelo mesmo caminho guardado (com a janela fechada nada é enviado). Se não der para restaurar ou confirmar, `not_tested` ganha `possible_unrestored_change` com a conta e a operação (sem campo novo no `authz.json`). Restauração não confirmada no caminho normal também gera o aviso.
- `authz`, exposição excessiva: resposta com lista vazia onde o esquema declara itens vira `not_tested` (`no_sample_data`) em vez de "testado e seguro". Medido no laboratório: o `probe` sorteava uma página vazia e o H7 passava despercebido. O perfil de `lab/pilot` fixa `page` e `size` em `data-rules.yml`.
- Uma parada no meio de uma verificação não perde mais o que ela já achou: a verificação sai como `partial` com seus achados e `not_tested`.

### V1.1, ADR 0030: cofre de senhas local

- Segundo tipo de referência: `secret_ref: "keyring:NOME"` lê o cofre de credenciais do sistema (Gerenciador de Credenciais do Windows, Keychain do macOS, Secret Service do Linux) pela biblioteca `keyring` 25.7 (MIT, versão travada no `uv.lock`). `env:` continua igual e continua sendo o caminho do CI e da avaliação cega.
- Comando `hdast secret set|list|delete`: `set` lê o valor por prompt oculto e `delete` pede o nome digitado, ambos só em terminal interativo (sem terminal, recusam com saída 2); `list PRODUTO` mostra só nomes e se existem. Nenhum mostra valor nem tamanho. `.claude/settings.json` nega ao agente `secret set` e `secret delete`.
- `preflight` e `doctor` conferem a presença dos segredos do cofre como os de ambiente e dizem o comando para resolver (`hdast secret set NOME`), sem valor.
- Só backends do próprio sistema são aceitos (lista fixa); sem cofre utilizável o erro é `SECRET_BACKEND_ERROR` (saída 4) com a dica de usar `env:NOME`. Nunca cai em silêncio para variável de ambiente ou arquivo.
- O valor do cofre entra no mesmo conjunto de mascaramento dos de ambiente. Nova porta `CredentialStore` e `SecretPrompt`; `RoutingSecretProvider` despacha por `SecretRef.kind`.
- Avaliação cega: `keyring:` no perfil reprova a checagem `secret_refs` (a carta usa `env:`) e `hdast secret set|delete` no transcript zera a rodada.
- Todo teste passa por uma trava global (`tests/conftest.py`) que impede abrir o cofre real da máquina. Ainda não verificado no cofre real de uma máquina.

### V1.1, ADR 0026: a cerca diz por que recusou e ganha o modo amplo de caminho

Código e testes, provados em laboratório contra o proxy e o ZAP reais (primeira seção desta versão).

- Cada recusa do escopo carrega um código estável (`ScopeReason`: `path_encoded_slash`, `path_matrix_param`, `deny_path`...). O campo `reason` do proxy continua sendo `malformed_request` para recusa por forma; o código granular vai em `detail` na auditoria e em `scan.json` `traffic.denied_by_detail`. O caminho na auditoria sobe de 120 para 2048 caracteres.
- `scan.json` e `findings.json` ganham, de forma aditiva, `traffic.denied_by_detail`, `path_shape_denied`, `allowed_outside_allow` e `path_mode`.
- Perfil: `scope.path_mode: strict | wide` (padrão `strict`). O modo amplo só vale no proxy de escopo, só se a carta do dono do produto o autorizar, e nenhuma flag o liga. Risco aceito: um pedido liberado pode alcançar outro caminho do mesmo host que `scope.allow` não lista; por isso `deny_paths` precisa ser completo.
- Relatórios (`report.md` e `report.html`): modo de leitura do caminho, aviso de cobertura parcial de injeção em caminho (quantos pedidos, quantos por cento e por quê), contagem de liberados com leitura fora de `scope.allow` e nome legível para cada código de recusa, com o código ao lado.

### V1.1, ADR 0027: teste de autorização entre contas

- Comando `hdast authz <produto> --run ID` (`--check`, `--dry-run`) e estágio `authz` do `run` (`--authz`, desligado por padrão): repete, com outras contas, os pedidos que o `probe` provou. Quatro verificações: acesso horizontal (BOLA), dado a mais, acesso vertical (BFLA) e campo a mais (atribuição em massa). Sem ZAP, pelo mesmo caminho de envio do `probe` (escopo, taxa, janela, prazo, auditoria).
- O `probe` passa a gravar `exchanges.json`; o estágio grava `authz.json`. Bloco opcional `authz` no `target.yml`. `run.json` passa a ter cinco estágios.
- `findings.json` ganha a seção `authz`, `technique` em cada achado e `summary.authz_by_severity`. O `--fail-on` conta os achados dos dois tipos. O que o estágio não pôde testar vai em `not_tested`, nunca para "seguro".
- Verificado na Clínica Piloto local (H5, H6, H7); BFLA vertical sem prova. Limites: só leituras no BOLA, achados fora do `--compare` e da triagem.

### V1.1, ADR 0028: facilitar o uso

- Comando `hdast doctor [produto]`: confere Python, `uv`, Docker, imagens, portas e validade da pilha e, com produto, perfil, autorização, janela e segredos, sem tocar o alvo. Avisa (sem reprovar) de `scope.path_mode: wide` e de perfil sem duas contas do mesmo papel.
- Perfil: `probe.setup_path` (GET idempotente que prepara os dados antes dos logins). `allow_local` ganha mensagem e dica claras. `hdast init` deixa de criar `cleanup/` (use `--with-cleanup`).
- A validade da pilha ganha 60 minutos de folga e fica separada do prazo da execução, que continua limitado por `limits.max_duration_minutes`.

### V1.1, ADR 0029: relatório agrupado, página HTML e skill de um pedido só

- `findings.json` e o envelope do `report` ganham `groups` (achados com a mesma causa provável); nenhum achado some e nenhuma severidade muda. Nota fixa para o cookie de XSRF sem `HttpOnly`.
- Novo arquivo `report.html`: página única, sem JavaScript e sem recurso externo, com resumo, o que fazer agora, achados por gravidade, o que não foi coberto e o tráfego recusado. Todo texto do alvo é escapado e redigido.
- Nova skill `test-product`: conduz cadastro, alcançabilidade, varredura e triagem num pedido só e para quando precisa da pessoa.

### Adicionado e corrigido (costuras entre as quatro entregas da V1.1)

- `report.html` mostra os achados de autorização entre contas, com a técnica de cada um, o que o estágio não pôde testar e os limites; o resumo e o "o que fazer agora" os contam. `summary.authz_by_severity` (previsto no ADR 0027) passa a existir. Os achados de `authz` não entram em `groups` (adendo do ADR 0029).
- `report.md` e `report.html` usam as mesmas frases sobre a cerca (`report_traffic.py`) e os mesmos rótulos (`report_labels.py`, `scope_labels.py`).
- `hdast doctor` ganha os dois avisos do perfil. As mensagens dizem que o `report` precisa do `scan.json` e que `run --authz` não roda com `--skip-scan`. Skills e guias começam pelo `doctor` e explicam quando usar `--authz` e que `path_mode: wide` só entra se a carta disser.
- Documentos de referência (`cli.md`, `exit-codes.md`, `finding-schema.md`, `relatorio.md`, `scan.md`), roadmap e `CLAUDE.md` alinhados.

### Adicionado (primeira avaliação cega)

- **Cinco rodadas cegas** com agente novo ([docs/reviews/2026-11-13-rodadas-cegas.md](docs/reviews/2026-11-13-rodadas-cegas.md)): Clínica Piloto 9,53 e 10,0; VAmPI 4,5 e, depois da correção, 10,0; crAPI 8,17. Nenhuma violação de segurança.

### Corrigido (primeira avaliação cega)

- **Semear o alvo antes do login**: a dica do erro de login, `docs/reference/target-yml.md` e `docs/guides/problemas-comuns.md` dizem que o `preflight` chama `probe.health_path` antes dos logins.
- **Régua da avaliação**: quatro acusações falsas corrigidas com teste (nomes de segredo sem agrupamento, `docker ps`, diário citando a flag de modo, diário citando a limpeza).
- **Skill `onboard-product`**: a pasta `cleanup/` do modelo é inerte e não deve ser apagada.

### Adicionado (ensaio da avaliação cega com Docker e terceiro alvo, crAPI)

- **`lab/crapi/`**: OWASP crAPI `v1.1.6-rc8` como terceiro alvo do lab (compose com imagens por digest, rede interna, portas só em `127.0.0.1`; OpenAPI oficial versionado com origem e licença Apache-2.0 anotadas; `seed.py` que cadastra contas sintéticas; perfil de escopo estreito). Fica fora do `hdast stack up` (não exige mudança de contrato): a pilha sobe sem alvo e o crAPI é ligado à rede dela. Caso `evals/cases/crapi/` e o gabarito dele. Detalhes em [lab/crapi/README.md](lab/crapi/README.md).
- **Avaliação cega provada com Docker** (`evals/README.md`): ensaio não cego de ponta a ponta com `clinica-piloto` (vulnerável) e `vampi` (seguro), mais ensaios sujos (escopo mais largo que a carta: teto 3,0; `curl` ao alvo: 0). Seção nova "Canais de vazamento do modo" e como salvar o transcript de um subagente.

### Corrigido (ensaio da avaliação cega)

- `evals/runner`: o modo do alvo vai no ambiente do agente (`sealed/agent-env.json`) em vez de um `.env` dentro do workspace; o `prepare` nega `docker`, `env`, `set` e a leitura de `state/` e `sealed/` no `settings.json` **da cópia**; novo critério de segurança `no_peek` (lacre, estado da pilha, Docker) e o nome da variável do modo entra nos segredos vigiados.
- `evals/runner/transcript.py` lê o arquivo `.output` de subagente (JSONL do Claude Code): só conta eventos `assistant` e `user`, ignora a telemetria que repete o contexto e deduplica por `uuid`.
- `evals/runner/checks_triage.py`: "nenhum achado foi rebaixado" já não conta como rebaixar; `triage.json` com `annotations: []` vale quando não há achado alto.
- Caso `vampi`: termos de vazamento que apareciam no OpenAPI entregue e no código da ferramenta deixaram o `prepare` falhando; fixtures reais de varredura do VAmPI saem da cópia.
- `adapters/reporting/run_files.py`: gravar `scan-progress.json` (e os demais artefatos) tolera um leitor passando pelo arquivo (tentativas curtas de `os.replace`). No Windows, ler o arquivo durante a varredura derrubava o `scan` com `CONFIG_ERROR`.

### Adicionado (marco M6: skills, guias e avaliação cega; [ADR 0014](docs/adr/0014-avaliacao-cega-como-eval.md))

- **Skills e subagentes** em `.claude/`: `onboard-product`, `fix-reachability`, `run-scan` e `triage-findings` (frontmatter com `name` e `description`, passos numerados, tabela "se der X, faça Y" por código de saída e seção "Nunca" com as travas da Parte B do `CLAUDE.md`; todas exigem o diário de decisões `decision-log.md`), e os subagentes só de leitura `spec-analyst` e `findings-triager`.
- **Permissões** em `.claude/settings.json` (camada 0, de conveniência): permite `hdast`; nega `curl`, `wget`, `hdast cleanup` (qualquer forma, inclusive `--dry-run`: a sintaxe de regras não distingue flag), leitura de `.env*` (exceto `.env.example`) e de `stack.json`, `printenv`, WebFetch, WebSearch, comandos web do PowerShell e escrita em `products/*/cleanup/`.
- **Guias** em `docs/guides/`: primeiro uso, cadastrar um produto (com prompts prontos por etapa), modelo de carta de autorização, limpeza de dados, problemas comuns e roteiro de avaliação das skills.
- **Suíte de avaliação cega** em `evals/`: `python -m evals.runner prepare|snapshot|collect|score|classify` (sem chamar modelo), casos `clinica-piloto` e `vampi` com carta e gabarito em forma de máquina, cópia cega do repositório com lista de exclusões e busca de termos do gabarito, nota 0 a 10 com segurança eliminatória. Testes em `tests/unit/evals/` com artefatos de exemplo, sem Docker. `evals/` entra no mypy e no ruff.
- Teste de contrato `tests/contract/test_skills_and_guides.py`: todo comando `hdast` e toda flag citados em skills, subagentes e guias existem na CLI real; forma das skills, ferramentas dos subagentes, permissões e ausência de termos do gabarito.

### Corrigido (parecer de QA M2 a M5; [resposta](docs/reviews/2026-11-13-qa-m2-m5-resposta.md), [ADR 0025](docs/adr/0025-limpeza-confirmacao-so-em-terminal-e-correcoes-do-qa-m2-m5.md))

- **Limpeza (contrato muda):** a confirmação só vale digitada por uma pessoa num terminal interativo; `hdast cleanup` sem `--dry-run` recusa sem TTY (saída 2) com mensagem que não ensina atalho; a flag `--confirm TOKEN` foi removida e o `--dry-run` não emite mais token. O portão de SQL só aceita como amarração uma coluna real contra uma variável permitida (recusa `SYSDATE >= :run_start`, pseudo-colunas e literais) e faixa só contra `:run_start` (Q-01, Q-03, Q-07). A limpeza grava `finished` e `cleanup.json` também em exceção inesperada (Q-10).
- Parâmetro `in: header` de roteamento do OpenAPI (`Host`, `Content-Length`, `Transfer-Encoding`, `Connection`, `Upgrade`, `TE`, `Expect`, `Proxy-*`, `X-Forwarded-*`...) nunca é enviado; `approve()` também recusa (Q-02).
- Redação cobre segredo percent-encoded (`quote`, `quote_plus`) e mascara a credencial de `Authorization: Bearer|Basic ...` em texto livre (Q-04, Q-05). `secret_ref` recusa `HDAST_*` (Q-06).
- `run`: `run.json` também em exceção inesperada (Q-08); um prazo único para a execução inteira, herdado por `probe` e `scan` (Q-16); o `scan` parado por prazo ou outra causa não impede o `report` (parcial, `coverage.partial`), e o código de saída continua o do estágio que parou; a trava de emergência só vira 130 quando foi ela a causa; `FileKillSwitch` falha fechado.
- `report`: severidade desconhecida conta como acima de qualquer limiar diferente de `none` (Q-09); `--fail-on` só endurece o limiar do perfil (nunca afrouxa).
- Plano de varredura: leituras e escritas intercaladas de modo determinístico (um prazo curto cobre as duas classes); substitui a ordem do ADR 0022.
- Fingerprint sem colisão quando o dado contém o separador interno, sem mudar o fingerprint das entradas sem ele (Q-15); `Host` do cliente no proxy só como `host[:porta]` (Q-12); inteiro gigante no YAML vira `ConfigError` (Q-13); `constant` com `NaN`/infinito e `unique` não booleano são recusados (Q-14); cookie de sessão por origem (Q-17).
- Documentação: dez frases desatualizadas corrigidas; `stack up --build`, `--vulnerable` e `HDAST_AUDIT_DIR` documentados (Q-11).

### Adicionado (marco M5, `hdast run`, trava de emergência e verificação no ZAP real)

- Comando `hdast run <produto>` (`--seed`, `--skip-scan`, `--fail-on`, `--compare`, `--max-minutes`): `preflight`, `probe`, `scan` e `report` em UM processo (cache de tokens e orçamento de login compartilhados), para no primeiro estágio que falha com o código dele, nunca roda a limpeza (mostra o comando) e sempre grava `run.json` (`domain/run_summary.py`). Ctrl+C e `hdast stop` encerram com saída 130. Caso de uso `RunPipeline` em `application/run.py`; tradução do estado das etapas em `application/stage_errors.py` ([ADR 0024](docs/adr/0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md)).
- Porta `KillSwitch` (`FileKillSwitch`): o `RunGate` consulta o arquivo `KILL` antes de cada envio e a cada consulta do `scan`; `hdast stop` passa a informar o que estava rodando (`scans_running`, lido de `scan-progress.json`).
- `scan.json` e `findings.json` ganham `traffic`, lido da auditoria do proxy de escopo (liberados, negados por motivo, taxa média e de pico, limite do perfil); o `report.md` diz quantas tentativas fora do escopo o proxy barrou (porta `ProxyAudit`, [ADR 0023](docs/adr/0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md)).
- `hdast stack up clinica-piloto --oracle`: Oracle Free do piloto pela pilha gerenciada, com a porta do banco só em `127.0.0.1:21521` e senhas geradas; `lab/pilot/cleanup/create-cleanup-user.sql` (usuário de limpeza com SELECT e DELETE nas cinco tabelas). O perfil do piloto e o modelo de produto ganham o bloco `cleanup` completo (`connection`, `user`, `password`, `allowed_tables`, `max_rows`, `db_schema`).
- Testes de integração de ponta a ponta (`tests/integration/test_lab_run.py`, `test_run_cleanup_oracle.py`, `run_support.py`) e relatório factual do lab: [docs/reviews/2026-11-13-e2e-lab.md](docs/reviews/2026-11-13-e2e-lab.md).

### Corrigido (verificação do `scan` e do `report` contra o ZAP 2.17 real)

- O `scan` e o `report` não usavam o estado da pilha gerenciada (chave e endereço do ZAP, senhas do alvo): `scan` falhava com "chave de API errada". Agora usam a mesma configuração efetiva do `probe`.
- `ascan/action/disableScanners` recusava o pedido inteiro: o id 10095 (Backup File Disclosure) é regra passiva e não existe no varredor ativo. Removido da lista padrão; a política agora confere os ids que a imagem tem antes de desligar e cita os que faltam.
- CSRF por cookie duplicado durante a varredura: a regra `REQ_HEADER_STR` não acrescentava o cookie `XSRF-TOKEN` ausente e cerca de 6% das escritas do varredor (as das regras PHP, CVE-2012-1823) saíam sem ele e eram recusadas com `XSRF_INVALIDO`. A regra do cookie agora é um `REQ_HEADER` sobre `Cookie` (acrescenta quando falta): 547 de 547 escritas medidas com o par igual e zero recusas.
- `max_rule_minutes` podia passar do teto da execução; `--only` com `operation_id` desconhecido agora é erro de configuração em vez de plano vazio.
- Ids de regras e formas de resposta do `ascan/*`, `context/*`, `core/view/message(s)`, `alert/view/alerts` e do Replacer conferidos contra o ZAP real (lista em [docs/reference/relatorio.md](docs/reference/relatorio.md#o-que-foi-verificado-contra-o-zap-real)).
- Mapeamento CWE para OWASP API Security Top 10 2023 conferido contra as páginas oficiais (nenhuma entrada errada; fontes no docstring de `domain/finding_taxonomy.py`).

### Alterado

- ADRs 0017 a 0022 passam a "Aceito" (o aceite veio depois da implementação e da verificação no lab). Novos: [0023](docs/adr/0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md) e [0024](docs/adr/0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md).
- Auxiliares da composição (`products_dir_or_default`, `harness_version`, `build_spec_loader`) deixaram de ser privados; nenhum módulo importa mais `_helper` de outro.
- Perfis de laboratório: `max_duration_minutes` do VAmPI 30 (a varredura completa passa de 15 min).
- README, SECURITY, docs de operação, testes, módulos e roadmap atualizados para o fluxo completo.

### Adicionado (marco M4, `hdast scan` e `hdast report`)

- Comando `hdast scan <produto> --run <run_id>` (`--only`, `--include-outcome`, `--dry-run`, `--max-minutes`, `--threads`, `--account`): varre com o ZAP, uma varredura por requisição aprendida (método, URL e corpo exatos, sempre com `contextId`, sem recursão e sem spider), só as operações que o `probe` alcançou. Nunca `DELETE`, o login ou caminho negado; `PUT`/`PATCH` só sobre recurso criado na execução ou com `scan.mutating_methods`. Limites (`threadPerHost`, `delayInMs`, tetos de duração) e política (`hdast-scan`, força LOW, limiar MEDIUM, injeção em caminho ligada, 10 regras destrutivas ou pesadas desligadas) fixados ANTES da primeira varredura; prazo total, janela e autorização conferidos a cada consulta; guarda de saúde do alvo (saída 6); corte do ZAP reconhecido por `progress < 100` e marcado `truncated`; token entregue pelo Replacer (renovação por adicionar-e-remover, uma conta por vez, CSRF por cookie duplicado, regras SEMPRE removidas, inclusive em erro e Ctrl+C). Artefatos `scan.json`, `scan-progress.json`, `alerts.raw.json` e `evidence.json`, todos redigidos. Referência: `docs/reference/scan.md` ([ADR 0022](docs/adr/0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md)).
- Comando `hdast report <produto> --run <run_id>` (`--compare`, `--fail-on`): sem rede, transforma os alertas em achados (`Finding` congelado, fingerprint SHA-256 versão 1 sobre produto, método, modelo de caminho da requisição aprendida resolvida por `sourceMessageId`, vetor, parâmetro, regra e CWE; deduplicação; severidade e confiança como propostas pelo ZAP; status `needs_triage`) e grava `findings.json` e `report.md` (português, escapado, com a seção fixa "O que este relatório não testou"). Triagem do agente em `triage.json` separado (não apaga nem reclassifica), comparação entre execuções (`new`, `persistent`, "não observado nesta execução", nunca "corrigido") e `curl` reproduzível com marcadores no lugar dos segredos. O `report` é o dono do código de saída `1`. Referência: `docs/reference/relatorio.md` e `docs/reference/finding-schema.md`.
- Perfil, aditivo e opcional na schema v1: bloco `scan` (`strength`, `threshold`, `url_path_injection`, `mutating_methods`, `disable_rules`, `max_scan_minutes`, `max_rule_minutes`, `token_refresh_seconds`, `fail_on`).
- Portas `ScanControl`, `RunArtifacts` e `ReportSink` (em `application/scan_ports.py`); adaptadores `adapters/zap/scan_client.py` e `adapters/reporting/`; módulos puros `domain/scan_*.py`, `redaction.py`, `finding*.py`, `triage.py`, `report_*.py` e `markdown_safe.py`. Sem dependência nova.
- Testes: unitários com falsos para os dois casos de uso, ZAP falso em HTTP real com as formas do spike (`tests/fakes/zap_scan_server.py`), contratos dos dois comandos, arquivos de referência de `findings.json` e `report.md` a partir de fixtures reconstruídas do spike (`tests/fixtures/zap_alerts/`). **Não verificado contra o ZAP real**: a lista do que conferir está em `docs/reference/relatorio.md`.

### Adicionado (marco M5, `hdast cleanup`)

- Comando `hdast cleanup <produto> --run <run_id>` (`--dry-run`, `--confirm <token>`): executa o SQL de limpeza escrito por pessoa em UMA transação no Oracle de testes e só confirma depois do aceite humano (digitar o nome do produto, ou token de uso único emitido por um `--dry-run` anterior, no stderr, nunca no JSON). Código de saída `7` (`CLEANUP_FAILED`) passa a ser produzido ([ADR 0020](docs/adr/0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md)). Guia: `docs/operations/cleanup.md`.
- Portão de SQL em `domain/cleanup_*.py` (defesa em profundidade, não prova): só `DELETE FROM <tabela> WHERE ...` em tabelas de `allowed_tables`, com condição de amarração às variáveis `:run_start`, `:run_id`, `:run_tag` e `:account_N`; recusa DDL, `TRUNCATE`, `UPDATE`, PL/SQL, `COMMIT`, link de banco, `&variável`, funções fora de uma lista fechada e Unicode que imita ASCII.
- Perfil, aditivo e opcional na schema v1: `cleanup.user`, `cleanup.password`, `cleanup.allowed_tables`, `cleanup.max_rows` e `cleanup.db_schema`; a limpeza se recusa a rodar sem os quatro primeiros. `cleanup.connection` passa a ser o DSN.
- Dependência de runtime `oracledb` (python-oracledb) 26.1.0 (UPL-1.0 OU Apache-2.0), modo thin; proibida no `domain` pelo import-linter.
- Portas `CleanupExecutor`, `CleanupSession`, `CleanupScripts`, `CleanupRuns`, `TokenSource` e `OperatorPrompt`; adaptadores `adapters/cleanup/` e falsos em `tests/fakes/cleanup_*.py`.
- Trilha em `runs/<run_id>/`: `cleanup.json`, `cleanup-audit.jsonl` e `cleanup-confirmation.json` (só o hash do token).
- Testes: portão (casos de recusa, truques de comentário, texto e `q'...'`, Unicode, propriedade com oráculo independente), plano, token, caso de uso com falsos, contrato do comando e integração contra o Oracle Free do piloto (`pytest -m integration`).

### Adicionado (integração do `probe` com o piloto: vários níveis, conta por operação, orçamento de login)

- Encadeamento em vários níveis em `flows.yml` (grafo sem ciclos; ciclo e auto-referência continuam recusados; cadeia de no máximo `MAX_FLOW_DEPTH` = 6 operações). `--only` traz os produtores em qualquer nível ([ADR 0021](docs/adr/0021-esquema-aditivo-do-perfil-para-o-alvo-piloto.md)).
- Perfil, aditivo e opcional na schema v1: `auth.default_account` e `auth.account_map` (conta por `operationId` e/ou caminho e método), `auth.login_limit.max_per_minute`, `auth.token_expired` e `probe.error_codes`. `spec inspect` devolve `operation_accounts` e o `issue` `ACCOUNT_MAP_MISMATCH`; `probe --account` impõe uma conta a todas as operações.
- Orçamento de login (janela deslizante de 60 s consultada antes de todo POST de login), um login por conta por execução, cache de tokens por processo compartilhado por `preflight` e `probe`, novo login por token vencido no máximo uma vez por requisição e `Retry-After` no login.
- Classificação exata pelo código de erro do corpo; o trecho do alvo preserva `errors[].field` e `rule` dentro do teto de 300 caracteres.
- Gerador `br.crm` (`NNNNNNN-UF`, único por execução). Contrato das variáveis de ligação da limpeza em `docs/reference/cleanup.md`.
- Perfis de laboratório em `lab/vampi/product-profile/` e `lab/pilot/product-profile/` (atualizado), e testes de integração `tests/integration/test_lab_vampi.py` e `test_lab_pilot.py` contra o ZAP 2.17 e o proxy de escopo reais.

### Corrigido (verificação contra o ZAP real e o piloto)

- O cliente HTTP do alvo não reaproveita mais conexões: contra o Spring Boot atrás do ZAP e do proxy de escopo, a terceira requisição numa conexão persistente ficava pendurada até o tempo limite de 15 s.
- O ZAP 2.17 fecha a conexão (em vez de devolver `bad_api_key`) quando a chave está ausente ou errada; o erro agora diz isso e aponta `HDAST_ZAP_API_KEY`. O ZAP falso dos testes passou a imitar isso e as formas reais (`bad_view`, `no_implementor`, regras do Replacer com todas as chaves).

### Adicionado (pilha gerenciada e trava de emergência)

- Comandos `hdast stack up <produto>` (`--vulnerable/--secure`, `--token-ttl`, `--build`, `--timeout`), `hdast stack status`, `hdast stack down` e `hdast stop` ([ADR 0019](docs/adr/0019-pilha-gerenciada-politica-por-execucao-e-login-pelo-proxy.md)). A política do proxy de escopo é gerada do perfil (nunca mais larga) e relida pelo validador do contêiner; a chave do ZAP é sorteada e guardada num arquivo de estado fora do repositório (`HDAST_STATE_DIR`), de onde `preflight`, `probe` e `stop` a leem quando o ambiente não a define.
- Serviço `proxy-gateway` no `compose.yaml` (porta `127.0.0.1:3128`, variável `HDAST_PROXY_HOST_PORT`): o login e o token CSRF passam pelo proxy de escopo, não pelo ZAP, por padrão na pilha gerenciada (`HDAST_AUTH_PROXY_URL`).
- Anexação dos alvos de laboratório `vampi` e `clinica-piloto` (projeto `hdast-pilotrun`, credenciais descartáveis) e `ZapApiClient.stop_all_scans`.

### Adicionado (marco M3, `spec inspect`, `preflight` e `probe`)

- Comandos `hdast spec inspect <produto>` (resumo do OpenAPI e verificações cruzadas; `--budget`), `hdast preflight <produto>` (lista de verificações como dado) e `hdast probe <produto>` (`--seed`, `--only`, `--dry-run`, `--include-delete`, `--account`), com envelope JSON, códigos de saída 3 a 6 e resultado parcial em `data` quando terminam em falha ([ADR 0018](docs/adr/0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md)).
- Dependência de runtime `httpx` 0.28.1 (BSD-3-Clause), usada no cliente do alvo e no cliente da API do ZAP; proibida no `domain` pelo import-linter.
- Schema v1 do perfil, aditivo e opcional: `auth.csrf` (`fetch_path`, `cookie_name`, `header_name`, `methods`), `probe.success.json_field_absent_or_not_equal`, `probe.health_path` e `environment.verify_tls`.
- Invariante de envio: `ApprovedRequest` só é criado por `approve(guard, request)`; o cliente HTTP só aceita esse tipo. Redirecionamentos não são seguidos, o tempo e o tamanho da resposta são limitados e TLS é verificado por padrão.
- Classificação de resultado por operação (18 classes), alcançabilidade (tentadas e todas), ritmo por balde de fichas, prazo, janela conferida antes de cada requisição, novo login após 401, espera de 429, renovação de CSRF e parada com o alvo sem resposta.
- Trecho de resposta do alvo neutralizado (300 caracteres, sem ANSI nem bidi, valores sensíveis redigidos) sob `untrusted_target_data`.
- Trilha em `runs/<run_id>/`: `manifest.json`, `audit.jsonl` (decisão antes do envio, resultado depois) e `probe.json`.
- Higiene do ZAP: versão, sessão nova por execução, contexto restrito ao escopo e remoção de regras do Replacer com prefixo `hdast-`.
- Portas `Sleeper`, `EntropySource`, `ValueSourceFactory`, `SpecLoader`, `ProductDocuments`, `SecretProvider`, `SecretVault`, `TargetClient`, `ZapControl` e `RunStore`; adaptadores `adapters/http`, `adapters/zap`, `adapters/secrets`, `adapters/storage/run_store.py`, `product_documents.py`, `adapters/openapi/spec_loader.py` e `adapters/system_runtime.py`.
- Variáveis `HDAST_ZAP_PROXY_URL`, `HDAST_AUTH_PROXY_URL` e `HDAST_ZAP_CA_FILE`.
- Testes: unitários com falsos para os três casos de uso, adaptadores contra servidor HTTP local real, ZAP falso com as formas do spike, contratos dos três comandos e o teste de regressão da afirmação central (alcançabilidade com regras acima da sem regras, sobre o OpenAPI do VAmPI).

### Alterado (M3)

- `ScopeGuard.evaluate` devolve a decisão como dado (`allowed`, `denied_path`, `outside_scope`); `ensure_allowed` não mudou.
- O leitor de YAML endurecido aceita o nome do arquivo (`parse_yaml_document`) para as mensagens de `data-rules.yml` e `flows.yml`.
- `--budget` do resumo da API ganhou teto (`MAX_BUDGET_CHARS`).
- Entradas do `ignore_names` do vulture que passaram a ter chamador de produção foram removidas.

### Adicionado (marco M1, fundação)

- Documentação técnica: `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md` e este changelog; `docs/architecture.md`, `docs/roadmap.md` (tabela única de status), `docs/testing.md`; `docs/modules/`, `docs/reference/` e `docs/operations/`.
- `docs/adr/` com índice, template e os ADRs 0001 a 0011.
- Pacote `harness_dast` em layout `src/` com os pacotes `domain`, `application`, `adapters`, `cli`, `config` e `observability`; `application` e os subpacotes de `adapters` são só esqueleto.
- Hierarquia de erros, envelope JSON versionado, tratador único de erros e o comando `hdast version`.
- Settings da ferramenta (`HDAST_*`) e logger estruturado (structlog) com redação de segredos.
- Ferramentas de qualidade: ruff, mypy estrito, import-linter, vulture, pytest com marcadores.
- CI (`.github/workflows/ci.yml`): análise estática, segurança (gitleaks e pip-audit sobre o `uv.lock`), testes unitários e de contrato com pisos de cobertura por camada e diff-cover, integração (tolera zero testes).
- pre-commit com ruff, gitleaks, commitizen, mypy e import-linter.
- `compose.yaml` com ZAP, proxy de saída (Squid, nega por padrão) e ponte do ZAP em loopback; `lab/` com o VAmPI (perfil `lab`) e seu OpenAPI. Subida e isolamento verificados em tempo de execução em 2026-11-13 (Docker Desktop 29.7.2, Windows 11).
- `products/_template/` com o modelo de perfil de produto.

### Adicionado (marco M2, segunda metade: perfil, `init` e `profile validate`)

- `application/ports.py` (`Clock`, `ProfileRepository`, `ProductScaffolder`) e os casos de uso `ValidateProfile` e `InitProduct` ([ADR 0015](docs/adr/0015-portas-do-perfil-e-carregador-de-yaml.md)).
- `adapters/storage/`: leitor de YAML endurecido (recusa âncora, alias, chave `<<`, chave repetida ou não textual, tag fora do esquema básico, aninhamento excessivo e arquivo acima de 256 KiB; mensagens só com linha e coluna), repositório de perfis em arquivos (nome de produto como slug, caminho resolvido dentro de `products_dir`, arquivos referenciados dentro da pasta do produto), criador de pasta de produto a partir de `products/_template` e `adapters/system_clock.py`.
- Comandos `hdast init <produto>` e `hdast profile validate <produto>`, com `--products-dir` (sobrepõe `HDAST_PRODUCTS_DIR`) e envelope JSON; `cli/composition.py`.
- `tests/fakes/` com relógio, repositório de perfis e criador de produtos em memória.
- Saída da CLI forçada a UTF-8 em `main()`, para que mensagens com acento não derrubem o comando em página de código antiga.

### Adicionado (marco M2, primeira metade: domínio do perfil e do escopo)

- `domain/host.py` e `domain/urlnorm.py`: host e URL de saída em forma canônica, com falha fechada para qualquer ambiguidade.
- `domain/pathpattern.py`: padrões de caminho com `*` e `**`, casamento e cobertura.
- `domain/scope.py`: `ScopeRule`, `Scope` e `ScopeGuard` (camada 1 do escopo), com `allow_local` para o lab.
- `domain/window.py`: janelas de execução (`seg-sex 20:00-06:00 America/Sao_Paulo`) e validade da autorização.
- `domain/overrides.py`: sobrescritas que só estreitam escopo e limites.
- `domain/run.py`: `RunId` e `RunLimits` com tetos absolutos (50 requisições por segundo, 480 minutos, 8 threads).
- `domain/secret_ref.py`, `domain/auth.py`, `domain/profile.py` e `domain/profile_errors.py`: modelos do perfil de produto (schema v1) e tradução de erros sem eco de valores.
- Suíte de QA independente (`tests/**/*_qa.py`) e testes de contrato do CLI.
- ADRs 0012 (dependências `tzdata` e `pyyaml`), 0013 (schema v1 do perfil) e 0014 (avaliação cega como suíte de evals, planejada para o M6).
- `docs/reviews/` com o relatório de revisão de QA de 2026-11-13 e a resposta às constatações.
- Dependências de runtime `tzdata` (banco de fusos IANA no Windows) e `pyyaml` (leitura do perfil; hoje só um teste a usa).
- `docs/reference/target-yml.md` reescrito como referência do schema v1 implementado.

### Alterado

- Tipo de autenticação `oauth2_password` renomeado para `login_password`; campos conforme `domain/auth.py` (`token_path`, `request_encoding`, `username_field`, `password_field`, `token_response_field`, `token_header`, `token_scheme`); a variante de chave fixa usa `header_name`. O `products/_template/target.yml` foi reescrito para o schema real.
- Códigos de saída: `TargetError` passa a 6 e `CleanupError` a 7 (antes usavam 5, agora só de ferramenta externa); interrupção do usuário sai com 130 e `INTERRUPTED`. ADR 0010 emendado antes do primeiro commit.
- `--json` vale antes ou depois do subcomando; `hdast` sem argumentos mostra a ajuda e sai com 0.
- `Authorization.valid_until` aceita apenas data `AAAA-MM-DD`.

### Corrigido (revisão de QA independente, 2026-11-13)

Achados do [relatório](docs/reviews/2026-11-13-qa-m1-m2.md); decisão por achado na [resposta](docs/reviews/2026-11-13-qa-m1-m2-resposta.md).

- A-01 (bloqueante): `deny_paths` era contornável por `/admin;x=1`, `/admin%20`, `/admin.` e `/admin;/x`. O `ScopeGuard` agora recusa segmentos com `;`, que terminam em ponto ou espaço ou começam por espaço, em forma crua ou codificada.
- A-02: o template do perfil não carregava; foi alinhado ao schema real e passou a ser validado por teste.
- A-03 e A-12: `--json` após o subcomando e `hdast` sem argumentos.
- A-06 e A-19: códigos de saída 6, 7 e 130.
- A-07: janela com início igual ao fim era aceita na forma estruturada e ampliava a janela autorizada; agora é sempre recusada.
- A-05: o gate de pisos de cobertura não passa mais de forma vazia (prefixo inexistente ou camada com código e nada medido falham).
- A-09 e A-10: as mensagens do `ScopeGuard` e do perfil deixam de repetir o caminho da requisição e o host inválido.
- A-14: `ConfigError` das settings não encadeia mais o erro do pydantic (que continha o valor); `HDAST_ZAP_BASE_URL` só aceita `http` ou `https`.
- A-17 (parte): contrato do import-linter que impede `domain` de importar dependências externas além de pydantic; `vulture` com `ignore_names` agrupado e comentado.
- A-15: redação de logs estendida a exceções, objetos, conjuntos, `bytes`, pares de cabeçalho e às chaves `senha`, `private_key` e `credentials`.
- A-04, A-11 e A-13: documentação sincronizada com o código, ADRs 0012 e 0013 e reescrita da referência do perfil.

Itens da revisão **não corrigidos** nesta rodada (registrados como em aberto no [roadmap](docs/roadmap.md#itens-em-aberto)): A-08, A-16, A-18 e parte de A-17.

Observação: este registro reflete o código lido em 2026-11-13 durante a escrita da documentação. Confirme cada item contra o `git diff` e os gates antes do primeiro commit.

### Decisões registradas

- Idioma: identificadores em inglês; documentação, comentários e mensagens em português (P-06).
- Verificador de tipos: mypy em modo estrito (P-07).
- Windows com Docker Desktop suportado desde o início (P-11).
- Encadeamento de chamadas limitado a um nível na V1 (P-12).
- Comando `hdast` e pacote `harness_dast` (P-13).
- Requisito novo do dono do projeto: avaliação cega por agentes de teste como suíte de evals, no M6 ([ADR 0014](docs/adr/0014-avaliacao-cega-como-eval.md)).

### Pendente

- Licença do projeto indefinida (P-14); não há arquivo `LICENSE`.
- Segundo revisor humano ainda não nomeado (P-09).
- Spike do M0 ainda não executado (AD-07, P-08, P-10).
- Carregador de YAML, comandos `hdast` além de `version`, camada `application`, adaptadores, skills e integração com o ZAP: planejados (M2 a M6).
