# Estado da arte: agentes de IA em testes de segurança (foco em APIs web) — novembro/2026

> Notas de pesquisa coletadas em 2026-11-12. Convenções: **[FATO]** = verificado em fonte primária aberta nesta sessão; **[VENDOR]** = afirmação do próprio fornecedor (não replicada de forma independente); **[SECUNDÁRIO]** = só encontrei em fonte de terceiros/agregador; **[INFERÊNCIA]** = conclusão minha. Toda data indica quando o número foi publicado. Nomes de modelos (ex.: "Claude Opus 5", "GPT-5.4", "DeepSeek v3.2") estão transcritos como aparecem nas páginas consultadas.

## 1. Como funcionam as ferramentas (XBOW, Escape, Strix, Shannon, PentAGI e outras)

### Takeaway
Praticamente todas as ferramentas relevantes em 2026 convergiram para o mesmo desenho: um coordenador que não testa nada, sub-agentes especializados por classe de vulnerabilidade rodando em sandbox (browser + proxy HTTP + terminal), e uma etapa separada de validação por exploração real ("no exploit, no report"). As diferenças práticas estão em: exigir ou não código-fonte (Shannon OSS exige), aceitar OpenAPI como entrada (Strix, Neo, Escape, Pynt aceitam), licença (AGPL vs Apache/MIT) e preço (de "só o custo do LLM" até ~US$ 4.000 por pentest).

### Cited Findings

**XBOW (comercial, SaaS)**
- [FATO, jun/2025] Validação por "validators": "automated peer reviewers that confirm each vulnerability"; às vezes é um LLM, às vezes checagem programática customizada; para XSS, um headless browser visita o alvo e confirma que o payload JavaScript realmente executou. — [XBOW blog, "The road to Top 1", 24/06/2025](https://xbow.com/blog/top-1-how-xbow-did-it/)
- [FATO, jun/2025] Seleção de alvos por pontuação (WAF, status HTTP, redirects, formulários de autenticação, nº de endpoints, tecnologias), deduplicação com SimHash + screenshots/imagehash; escopos de programas interpretados com LLM + curadoria manual. — [XBOW blog](https://xbow.com/blog/top-1-how-xbow-did-it/)
- [FATO, jun/2025] O post diz que "All findings were fully automated", mas também que o time de segurança revisou os achados antes do envio para cumprir a política do HackerOne — as duas frases ficam em tensão e o post não quantifica o filtro humano. — [XBOW blog](https://xbow.com/blog/top-1-how-xbow-did-it/)
- [SECUNDÁRIO] Descrição de "coordenador persistente que dirige milhares de agentes" + lógica determinística para validação; uso de canários/flags plantados no sistema para provar exploração; "perguntar ao LLM se a vulnerabilidade é real dá taxa de FP muito alta". — [welcome.ai](https://welcome.ai/company/xbow/technology); [Cyberbuilders substack](https://cyberbuilders.substack.com/p/intelligent-security-requires-validation)
- [CONFLITO, 2025–2026] Preço: a página própria mostrou "starts at $4,000/per test" ([xbow.com/pentest](https://xbow.com/pentest)); release sindicado do lançamento do Pentest On-Demand cita US$ 6.000 ([StreetInsider](https://www.streetinsider.com/Press+Releases/Announcing+XBOW+Pentest+On-Demand+for+Security+at+Machine+Speed/25603595.html)); terceiros relatam que os tiers públicos sumiram de xbow.com/pricing em meados de julho/2026 e hoje é "Request Pricing" ([CodeAnt](https://codeant.ai/blogs/xbow-pricing)). No estudo Doyensec, cada scan XBOW (tier "Plus"/Lightspeed) custou US$ 4.000 ([Hacktron, 05/06/2026](https://www.hacktron.ai/blog/hacktron-vs-xbow-and-aikido)).

**Escape (escape.tech) — comercial**
- [VENDOR, 30/04/2026] Motor "Cascade": um coordenador que mantém o estado do pentest e só delega (prompt citado: "You are a COORDINATION AGENT ONLY. You do NOT perform any security testing"); agentes de contexto/suporte; agentes por classe (Agentic Crawler, XSS Agent, SQLi Agent, BOLA Agent, Business Logic Agent, Regression Testing Agent, Adversarial Vulnerability Validator); ferramentas em sandbox: browser, proxy HTTP, terminal; toda requisição passa por proxy configurável. — [Escape, "AI Pentesting Agents 2.0 – A Deep Dive"](https://escape.tech/blog/ai-pentesting-agents/)
- [VENDOR] BOLA Agent valida isolamento entre tenants (horizontal) e escalada de privilégio (vertical) usando autenticação multiusuário; Business Logic Agent cobre bypass de workflow, manipulação de estado e ataques multi-etapa. — [Escape docs, BOLA agent](https://docs.escape.tech/documentation/ai-pentesting/bola-agent); [How AI Pentesting Works](https://docs.escape.tech/documentation/ai-pentesting/how-it-works/)
- [FATO, abr/2026] No benchmark da própria Escape, todas as ferramentas receberam URL + **spec OpenAPI** + dois pares de credenciais (grey-box) — ou seja, Escape, Shannon, Strix e PentAGI rodam com esse tipo de entrada. — [Escape, benchmark 30/04/2026](https://escape.tech/blog/benchmarking-agentic-ai-pentesting-tools/)
- Preço: não publicado nas páginas consultadas (ver Gaps).

**Strix (usestrix/strix) — open source**
- [FATO, lido em 12/11/2026] Licença Apache-2.0; 75,2k stars; arquitetura "Graph of Agents" (agentes especializados de recon, exploração e pós-exploração que compartilham achados); ferramentas: proxy de interceptação HTTP (Caido), browser automatizado, shell interativo, sandbox Python; alvos aceitos: diretório local, repo GitHub, URL viva, **arquivos OpenAPI/Swagger, exports/coleções Postman**, listas de alvos; modo CI `-n/--non-interactive` com exit code ≠ 0 quando acha vulnerabilidade; `--scan-mode quick`; requer Docker e chave de LLM; modelos locais via `LLM_API_BASE`. — [GitHub usestrix/strix](https://github.com/usestrix/strix)
- [VENDOR] "Real exploit validation - working PoCs, not false positives". — [GitHub usestrix/strix](https://github.com/usestrix/strix)
- [SECUNDÁRIO] Agente raiz orquestra e sub-agentes especializam; criação de agentes e mensagens são ferramentas de primeira classe; chamadas de ferramenta em tags estilo XML; roteamento via LiteLLM. — [análise de repositório (codedocs)](https://codedocs-2gm.pages.dev/raw/strix/00_overview)
- Preço do Strix Cloud/Enterprise: não publicado. — [GitHub usestrix/strix](https://github.com/usestrix/strix)

**Shannon (KeygraphHQ/shannon) — open source + comercial**
- [FATO, lido em 12/11/2026] Licença **AGPL-3.0** (licença comercial sob contato); 51,8k stars; edição OSS: paga-se só o custo do modelo; Pro: US$ 50 por desenvolvedor ativo/mês; Enterprise sob consulta; programa Community gratuito para ONGs 501(c)(3) e startups pré-Series A com ≤20 devs. — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)
- [FATO] Pipeline: recon + análise de vulnerabilidade com agentes por classe (Injection, XSS, SSRF, Authentication, Authorization) → análise agêntica de código → reconciliação/deduplicação em fila de exploração → agentes de exploração → validação → relatório (PDF, Markdown, JSON, SARIF 2.1.0). Cada scan roda em container Docker efêmero. — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)
- [FATO] **White-box**: o Shannon OSS analisa o código-fonte e precisa de alvo com fonte disponível; black-box só no "Blackbox Pentester" e nas edições Pro/Enterprise/Community. Política "No exploit, no report". O README não menciona OpenAPI. — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)
- [FATO] Avisos do próprio README: não é scanner passivo e pode alterar estado (usar staging/dados descartáveis); achados exigem revisão humana ("LLM-generated reports can contain weakly supported or incorrect details"); modelos mais fracos geram pentests mais fracos; não escanear codebases não confiáveis (risco de prompt injection). A versão 1.9.0 é descrita como "the final release built on the Claude Agent SDK". — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)

**PentAGI (vxcontrol/pentagi) — open source**
- [FATO, lido em 12/11/2026] Licença MIT; 34,0k stars; stack Go + React + GraphQL; o repositório inclui `docker-compose-graphiti.yml`, `docker-compose-langfuse.yml` e `docker-compose-observability.yml` (indica grafo de conhecimento Graphiti e observabilidade Langfuse). — [GitHub vxcontrol/pentagi](https://github.com/vxcontrol/pentagi)
- [SECUNDÁRIO] Orquestrador analisa o pedido, escolhe o agente especialista (pesquisador/searcher, desenvolvedor, executor/pentester), passa contexto e ferramentas e decide se delega mais; trabalho organizado em flows → tasks → subtasks; execução em container Docker baseado em Kali com 20+ ferramentas; memória persistente entre sessões; o modo multiagente pode ser desligado; delegação gasta mais tokens; release v1.2.0 em 25/02/2026. — [Help Net Security, 22/04/2026](https://www.helpnetsecurity.com/2026/04/22/pentagi-autonomous-ai-penetration-testing/); [Emelia review](https://emelia.io/hub/pentagi-ai-penetration-testing-review)
- [SECUNDÁRIO] Revisores contestam o marketing de "zero intervenção humana". — [Emelia (DE)](https://emelia.io/de/hub/pentagi-autonomer-ki-agent-hacking-leitfaden-2026)

**ProjectDiscovery Neo — comercial (dos autores do nuclei)**
- [VENDOR/docs] Orquestrador delega a 20+ sub-agentes embutidos (Sandbox agent com "the complete security toolchain", browser, recon passivo, **API security**, XSS, triage etc.); sandbox e memória de tarefa compartilhados; 25 skills carregáveis (ex.: escrita de templates Nuclei, SQLMap, Semgrep). **Verifier agent** reproduz de forma independente cada achado e devolve *confirmed / false positive / needs retry*; **Validation agent** testa contra URLs vivas (auth bypass, IDOR, SSRF, XSS, path traversal). O **API security agent ingere especificações OpenAPI**, enumera endpoints e testa auth bypass, injeção e lógica de negócio. — [Neo docs, agent architecture](https://docs.neo.projectdiscovery.io/concepts/agent-architecture)
- [SECUNDÁRIO, 04/08/2026] Neo v1 em GA com preço pay-as-you-go. — [PR Newswire via StreetInsider](https://www.streetinsider.com/PRNewswire/ProjectDiscovery+Makes+Neo+Generally+Available+with+Pay-As-You-Go+Pricing/26861971.html)

**OWASP ZAP (open source) — esforços próprios de IA/MCP**
- [FATO, 02/04/2026] Add-on oficial "ZAP MCP Integration", release **alpha**. Tools: `zap_version`, `zap_info`, `zap_create_context`, `zap_start_spider`/`zap_stop_spider`/`zap_get_spider_status`, equivalentes para AJAX spider e active scan, `zap_get_passive_scan_status`, `zap_generate_report`. Resources: `zap://alerts`, `zap://alerts/{alertRef}`, `zap://contexts`, `zap://history`, `zap://history/{id}`, `zap://scan-policies`, `zap://scan-status`, `zap://sites`, `zap://sites-tree`, `zap://report-templates`. Prompts: `zap_baseline_scan`, `zap_full_scan`. Security key habilitada por padrão (header `Authorization`); "Secure Only" = true por padrão. **Limitação declarada: "This release does not directly support authenticating to target apps"**; a página não menciona import de OpenAPI via MCP. — [ZAP blog](https://www.zaproxy.org/blog/2026-04-02-zap-mcp-server/)
- [SECUNDÁRIO] Em maio/2026 o ZAP passou a escanear servidores MCP como alvo; em setembro/2026 saiu add-on opt-in para conectar o ZAP a um LLM escolhido pelo usuário. — [ZAP blog index](https://zaproxy.org/blog/)
- [SECUNDÁRIO] Alternativas comunitárias: `dtkmn/mcp-zap-server` (Java/Spring Boot; spider, active scan, relatórios; descrito como "work in progress", não afiliado ao OWASP) — [mcpservers.org](https://mcpservers.org/servers/dtkmn/mcp-zap-server); `mcp-server-zap` no PyPI (Python, ~37 tools) — [PyPI](https://pypi.org/project/mcp-server-zap/)

**Burp Suite (PortSwigger) — comercial**
- [FATO, 20/02/2025] Shadow Repeater: extensão do Burp Pro que envia variações dos ataques manuais do testador e manda respostas interessantes ao Organizer. — [PortSwigger Research](https://portswigger.net/research/shadow-repeater-ai-enhanced-manual-testing)
- [FATO] Extensão oficial "MCP Server" na BApp Store integra o Burp a clientes de IA via MCP (com proxy stdio empacotado). — [BApp Store](https://portswigger.net/bappstore/9952290f04ed4f628e624d0aa9dccebc)

**Aikido "Attack" AI Pentest — comercial**
- [SECUNDÁRIO, 2026] Standard pentest US$ 4.000 e Advanced US$ 8.000 (compra avulsa). — [G2](https://www.g2.com/products/aikido-security/pricing)
- [FATO via terceiros, 2026] No estudo Doyensec (patrocinado pela Aikido), Aikido levou ~8h40 no Fider; XBOW ~1 semana de calendário. — [Hacktron](https://www.hacktron.ai/blog/hacktron-vs-xbow-and-aikido); relatório original: [Doyensec PDF](https://doyensec.com/resources/ComparingAIApplicationSecurityTestingPlatforms_Doyensec.pdf) (PDF em imagem, não consegui extrair o texto)

**Invicti (DAST clássico + camada agêntica) — comercial**
- [VENDOR, 08/10/2026] Em Fider/Photoview, 27 de 52 achados (52%) atribuídos ao DAST determinístico e 25 (48%) à camada agêntica; a empresa descreve o DAST como detecção rápida/ampla/repetível e a camada agêntica como achados específicos da aplicação que o DAST perdeu (~93% de aumento de cobertura sobre o DAST sozinho). — [Invicti Security Labs](https://www.invicti.com/blog/security-labs/invicti-agentic-pentest-benchmark-fider-photoview)

**Terra Security — comercial, human-in-the-loop**
- [VENDOR] Enxame de agentes + testadores humanos que validam os achados; guardrails em três grupos (ações autônomas, ações que exigem aprovação humana explícita, ações proibidas), tudo logado para auditoria. Série A de US$ 30M (set/2025). — [Terra blog, guardrails](https://www.terra.security/blog/ai-pentesting-guardrails); [Terra Series A](https://www.terra.security/blog/terra-security-raises-30m-series-a-to-redefine-penetration-testing-with-agentic-ai)

**PentestGPT (GreyDGL) — open source (MIT)**
- [SECUNDÁRIO/maintainer-reported, dez/2025] 86,5% (90/104) no XBOW validation suite; custo médio US$ 1,11 e mediano US$ 0,42 por benchmark resolvido; tempo médio 6,1 min; por nível: 91,1% (L1), 74,5% (L2), 62,5% (L3). O README avisa que é "a historical research result, not a current pentestgpt-agent regression guarantee". — [mirror do README](https://gitcode.com/GitHub_Trending/pe/PentestGPT/blob/main/README.md)

**MAPTA (acadêmico, código aberto)**
- [FATO, 28/08/2025] Coordenador + agentes de sandbox + validação de exploit ponta a ponta; 76,9% no XBOW (104). — [arXiv 2508.20816](https://arxiv.org/abs/2508.20816)

**ARTEMIS (Stanford, acadêmico)**
- [FATO, 10/12/2025] Supervisor (lista de tarefas, notas, sumarização) + sub-agentes arbitrários com system prompt gerado por tarefa + **módulo de triagem** que checa relevância, reprodutibilidade e duplicatas antes de submeter. — [arXiv 2512.09882](https://arxiv.org/html/2512.09882v1)

**Outros**
- HexStrike AI (0x4m4/hexstrike-ai): servidor MCP que expõe "150+ security tools" e "12+ autonomous AI agents"; [SECUNDÁRIO] MIT, ~10,2k stars (dado de 27/04/2026). É uma camada de ferramentas, não um pentester com validação. — [GitHub](https://github.com/0x4m4/hexstrike-ai); [dev.co](https://dev.co/ai/frameworks/hexstrike-ai)
- CAI (Alias Robotics): framework open source leve para construir agentes de segurança, padrão ReACT; a família de modelos "alias" é medida em CAIBench (alias2: 25/33 = 76%). — [arXiv 2601.14614](https://arxiv.org/pdf/2601.14614v3)
- Google Big Sleep: foco em descoberta de vulnerabilidades em código (memória/C/C++), não em pentest de API; 20 falhas em open source divulgadas em ago/2025 com humano na verificação final. — [TechCrunch, 04/08/2025](https://techcrunch.com/2025/08/04/google-says-its-ai-based-bug-hunter-found-20-security-vulnerabilities/)
- Pynt: gera cenários de teste a partir de OpenAPI/Swagger e coleções Postman; afirma automatizar detecção de BOLA analisando tráfego real; sem preço público. — [Pynt](https://www.pynt.io/product/business-logic-pynt); [G2](https://g2.com/products/pynt-api-security-testing/pricing)
- Akto: núcleo original open source (MIT) com descoberta de APIs e DAST em CI/CD, biblioteca de 1000+ testes; foco comercial atual em segurança de agentes/MCP. — [GitHub akto](https://www.github.com/akto-api-security/akto); [AppSecSanta](https://appsecsanta.com/akto)
- RunSybil: orquestrador "Sybil" controla agentes especializados; US$ 40M anunciados em 18/03/2026; documentação pública escassa. — [CodeAnt](https://codeant.ai/blogs/xbow-alternatives)
- Horizon3 NodeZero: forte em rede/infra interna (abuso de credenciais, movimento lateral), não é primariamente um testador de aplicação web/API. — [CodeAnt](https://www.codeant.ai/blogs/nodezero-pricing)

### Inferences
- [INFERÊNCIA] Para o caso "Swagger + escopo + credenciais de teste → agente → ZAP/HTTP/nuclei → validação → relatório", os análogos mais próximos já existentes são **Strix** (Apache-2.0, aceita OpenAPI/Postman, modo CI) e o **API security agent do Neo** (comercial). Shannon OSS não serve como black-box de API porque exige código-fonte e é AGPL-3.0 (atenção jurídica se for embutir/derivar).
- [INFERÊNCIA] O MCP oficial do ZAP, em nov/2026, não resolve autenticação no alvo nem import de OpenAPI; um CLI interno provavelmente falaria com a API REST nativa do ZAP (import OpenAPI, contexts, usuários) e usaria o ZAP sobretudo como proxy/gravador + active scan determinístico, deixando BOLA/BFLA para um cliente HTTP dirigido pelo agente.
- [INFERÊNCIA] O padrão "validador separado e, quando possível, determinístico" é o único elemento presente em todos os produtos que publicam taxas de FP baixas (XBOW, Neo, Escape, Shannon, ARTEMIS).

### Gaps
- Arquitetura interna detalhada do XBOW (solvers de vida curta, "model alloys") — não consegui abrir os posts de engenharia correspondentes; só o post do HackerOne e fontes secundárias.
- Docs oficiais do PentAGI (lista de agentes como adviser/reflector/memorist, limites de tool-calls): as páginas Mintlify retornaram HTTP 410; o README renderizado não trouxe esses detalhes.
- Preço de Escape, Strix Cloud, RunSybil, NodeZero, Pynt: não público.
- Licença exata do CAI e do HexStrike não confirmadas em fonte primária.
- Relatório Doyensec original: PDF só em imagem; números vêm de quem o cita (Hacktron, Invicti, Escape, Strobes — todos concorrentes).
- Burp AI (créditos, recursos de IA no scanner) não foi coberto além de Shadow Repeater e MCP Server.

## 2. Quais arquiteturas funcionam melhor e por quê

### Takeaway
A evidência (acadêmica e de fornecedores) aponta na mesma direção: hierarquia coordenador → especialistas de contexto curto supera agente único, e o harness (laço de ação, autenticação, validação) pesa mais que o modelo. Mas há contraexemplo relevante: um agente único genérico (Claude Code) superou Strix e PentAGI em F1 num protocolo de 2026 — então "multiagente" por si só não garante nada; o que se repete como determinante é gestão de contexto + triagem/validação separada.

### Cited Findings
- [FATO, 2024/rev. 2025] HPTSA: planner hierárquico → team manager → 6 agentes especialistas (XSS, SQLi, CSRF, SSTI, **ZAP**, genérico). Em 14 vulnerabilidades web reais: 42% pass@5 e 18% pass@1; GPT-4 agente único sem descrição ≈ 2,0× pior em pass@5 e 4,3× pior em pass@1. Ablações: sem agentes especialistas → pass@1 2,1× menor; **sem estrutura hierárquica → pass@1 13× menor e pass@5 6× menor**. ZAP e Metasploit sozinhos: 0%. — [arXiv 2406.01637v2](https://arxiv.org/html/2406.01637v2)
- [VENDOR, 30/04/2026] Escape justifica multiagente: um agente geral fazendo recon+XSS+BOLA+SQLi+lógica "luta contra a própria janela de contexto"; agentes especializados com prompts focados e acesso restrito a ferramentas performam melhor e alucinam menos; escopo estreito permite permissões estreitas (segurança). — [Escape](https://escape.tech/blog/ai-pentesting-agents/)
- [VENDOR, 30/04/2026] "A camada de orquestração importa mais que o modelo": três ferramentas com o mesmo modelo (DeepSeek v3.2) fizeram 1/20 (Strix), 6/20 (Shannon) e 9/20 (PentAGI) no mesmo alvo. — [Escape benchmark](https://escape.tech/blog/benchmarking-agentic-ai-pentesting-tools/)
- [VENDOR, 30/06/2026] Harness (orquestração, contexto persistente, teste autenticado multi-persona, validação) rendeu ~4× mais achados que o mesmo modelo frontier "cru" em apps novos: Fider 26–28 (Cascade) vs 7 (Claude Opus 4.8 sem harness). — [Escape, in-depth benchmark](https://escape.tech/blog/modern-ai-powered-pentesting-tools-in-depth-benchmark/)
- [FATO, 10/12/2025] ARTEMIS foi criado porque frameworks existentes tinham poucos sub-agentes, gestão de contexto ruim para execuções longas e pouca expertise de segurança; divide o trabalho em sessões, sumariza e limpa contexto; pico de 8 sub-agentes concorrentes (média 2,82 por iteração do supervisor). Scaffolds rígidos/rasos (Codex, CyAgent) entregaram basicamente achados de scanner; Codex terminou em <20 min. — [arXiv 2512.09882](https://arxiv.org/html/2512.09882v1)
- [FATO, 11/05/2026 — contraexemplo] Em 3 alvos (108 vulnerabilidades de ground truth), **Claude Code (agente único genérico, Sonnet 4.6)** foi o melhor no geral: F1 +16,79 p.p. vs Strix-Sonnet (p=0,0141) e +14,49 p.p. vs PentAGI-GPT; menor custo e tempo, porém com muitas duplicatas e precisão 81,24%. PentAGI-Sonnet: maior recall e severidade, mas mais FPs e maior custo; Strix-Sonnet: menos FPs, menor recall. — [arXiv 2605.10834 (Ethiack)](https://arxiv.org/html/2605.10834v1)
- [FATO, 28/08/2025] MAPTA (coordenador + agentes de sandbox + validação ponta a ponta): sucesso correlaciona com eficiência; sugerem **early stopping em ~40 tool calls ou US$ 0,30 por desafio**. — [arXiv 2508.20816](https://arxiv.org/abs/2508.20816)
- [FATO, jun/2025] XBOW: precisão é o desafio central e é tratada por validadores (LLM ou programáticos) separados do agente que descobre. — [XBOW blog](https://xbow.com/blog/top-1-how-xbow-did-it/)
- [VENDOR, 23/10/2026] Cobalt recomenda: multiagente com agentes de foco estreito, agentes supervisores, misturar modelos/níveis de esforço para diversificar caminhos, reexecutar com mesmo escopo e reconciliar, construir sobre ferramental automatizado estabelecido, manter scanners tradicionais como camada complementar. — [Cobalt](https://www.cobalt.io/blog/why-one-ai-pentest-run-isnt-enough)
- [VENDOR, 08/10/2026] Híbrido DAST determinístico + agente: 52% dos achados vieram do DAST, 48% do agente. — [Invicti](https://www.invicti.com/blog/security-labs/invicti-agentic-pentest-benchmark-fider-photoview)
- [VENDOR, 05/06/2026] Hacktron: a maioria dos bugs de camada de aplicação não precisa do modelo mais caro em cada passo; rotear entre modelo forte e barato dá resultado similar a custo menor. — [Hacktron](https://www.hacktron.ai/blog/hacktron-vs-xbow-and-aikido)

### Inferences
- [INFERÊNCIA] Receita com maior respaldo: (1) coordenador que só planeja/delegar; (2) sub-agentes curtos por classe de vulnerabilidade e por grupo de endpoints, com contexto limpo; (3) validador independente — determinístico quando a classe permite (ex.: BOLA = repetir a requisição com o token do usuário B e comparar status/corpo; XSS = headless browser); (4) triagem de duplicatas antes do relatório; (5) orçamento/early-stop por sub-tarefa.
- [INFERÊNCIA] Para APIs com OpenAPI, a decomposição natural é por recurso/operação × classe (authn, BOLA, BFLA, mass assignment, injeção), o que casa com "muitos agentes curtos" e evita o problema de janela de contexto.
- [INFERÊNCIA] O resultado do Claude Code no paper da Ethiack sugere começar com um laço de agente único bem instrumentado + validador, e só adicionar hierarquia quando o contexto estourar — em vez de copiar a complexidade do PentAGI de saída.

### Gaps
- Não há estudo controlado e independente comparando arquiteturas (agente único vs multiagente vs planner-executor) com o mesmo modelo e o mesmo orçamento em alvos realistas de API; HPTSA usa GPT-4 de 2024 e 14 CVEs.
- A ablação do HPTSA não foi replicada com modelos de 2026.
- A Ethiack é fornecedora (produto "Hackian" aparece como melhor no blog parte 2: F1 +12,28 p.p. vs Claude Code) — [Ethiack parte 2, 22/07/2026](https://ethiack.com/info-hub/research/evaluating-pentesting-agents-part-2).

## 3. Benchmarks públicos e resultados

### Takeaway
Os placares ~96% no benchmark XBOW (104 desafios) são auto-reportados, em condições diferentes (Shannon: white-box em versão "limpa"; Strix: sem replicação independente) e sobre um conjunto CTF que a própria XBOW declara obsoleto. Em avaliações com alvos mais realistas os números despencam: 13% (CVE-Bench), 21% autônomo (AutoPenBench), 12,5% em Detect (BountyBench), 5%–75% de detecção num app vulnerável com OpenAPI (Escape). O "nº 1 do HackerOne" do XBOW é real, mas ~43% dos ~1.060 envios foram duplicado/informativo/N.A.

### Cited Findings

**XBOW validation benchmarks (104 desafios, "XBEN")**
- [FATO, 09/11/2024] 104 benchmarks estilo CTF construídos por empresas de pentest contratadas; XBOW marcou 85%, descrito como equivalente a um pentester experiente em uma semana. **Nota do editor atual: os benchmarks estão desatualizados e "should no longer be used to measure offensive performance".** — [XBOW blog](https://xbow.com/blog/benchmarks)
- [VENDOR] Cinco pentesters com 40 h: o principal igualou os 85% do XBOW; o staff fez 59%; XBOW levou 28 min. — [XBOW, xbow-vs-humans](https://xbow.com/blog/xbow-vs-humans)
- [VENDOR] Shannon Lite: **96,15% (100/104) em modo white-box, numa versão "hint-free"** da qual a Keygraph removeu nomes de variáveis descritivos, comentários, caminhos/nomes de arquivos, títulos e configurações de Dockerfile. — [GitHub KeygraphHQ/xbow-validation-benchmarks](https://github.com/KeygraphHQ/xbow-validation-benchmarks)
- [VENDOR/SECUNDÁRIO, 2026] Strix: 100/104 (~96%); artigo de 01/08/2026 classifica como "vendor and community-reported", custo ~US$ 3,37 por desafio com GPT-5.4, **sem replicação independente citada até agosto/2026**. Outros guias secundários atribuem o resultado à v0.4.0 com Gemini 3 Pro Preview em black-box — as fontes não coincidem quanto ao modelo. — [DEV/Creeta](https://dev.to/creeta/strix-claims-96-on-xben-that-number-is-vendor-reported-3en8); [wavect](https://wavect.io/blog/strix-ai-pentesting-pilot-guide-2026.md). O repositório do harness existe mas a página não mostra resultados: [usestrix/benchmarks](https://github.com/usestrix/benchmarks)
- [maintainer-reported, dez/2025] PentestGPT: 86,5% (90/104). — [mirror do README](https://gitcode.com/GitHub_Trending/pe/PentestGPT/blob/main/README.md)
- [FATO, 28/08/2025] MAPTA: 76,9%; por classe: SSRF 100%, misconfiguration 100%, SSTI 85%, SQLi 83%, **broken authorization 83%**, XSS 57%, **blind SQLi 0%**. — [arXiv 2508.20816](https://arxiv.org/abs/2508.20816)
- [SECUNDÁRIO] MAPTA também publicou correções para 43 de 104 imagens Docker desatualizadas do benchmark. — [arXiv 2508.20816v1](https://arxiv.org/html/2508.20816v1)
- [FATO, 11/05/2026] Crítica: benchmarks CTF "reduce success to capture-the-flag in closed settings"; até um cenário simples (xben-090) contém múltiplas vulnerabilidades (a Ethiack catalogou 20), inclusive não intencionais, que o critério de flag ignora; xben-090 funcionou como teste de estresse de precisão, com FP alto mesmo para setups conservadores. — [arXiv 2605.10834](https://arxiv.org/html/2605.10834v1)

**XBOW no HackerOne**
- [FATO, 24/06/2025] "Nearly 1,060" vulnerabilidades submetidas: 130 resolved, 303 triaged (maioria em VDPs), 33 new, 125 pending, **208 duplicate, 209 informative, 36 not applicable** (a maioria fechada pelo próprio time). Severidade nos últimos 90 dias: 54 critical, 242 high, 524 medium, 65 low. ~45% ainda aguardando resolução. — [XBOW blog](https://xbow.com/blog/top-1-how-xbow-did-it/)
- [FATO, 25/06/2025 — crítica] O ranking foi no leaderboard de VDP (sem recompensa, menos concorrência), não no de bounty; os relatórios não foram publicados, então não se sabe se eram "low-hanging fruit"; não se sabe quanto foi automatizado vs assistido; as classes destacadas são "bread and butter" de DAST convencional; XBOW não fala de autenticação. — [Utku Sen](https://utkusen.substack.com/p/does-xbow-ai-hacker-deserve-the-hype)
- [SECUNDÁRIO] Outra crítica na mesma linha: [LessWrong, "Be skeptical of milestone announcements by young AI startups"](https://www.lesswrong.com/posts/qefrWyeiMvWEFRitN/be-skeptical-of-milestone-announcements-by-young-ai-startups)

**Benchmarks acadêmicos**
- [FATO, 2024/2025] HPTSA: 42% pass@5, 18% pass@1 em 14 vulnerabilidades web reais; ZAP/Metasploit 0%. — [arXiv 2406.01637v2](https://arxiv.org/html/2406.01637v2)
- [FATO, mar/2025, rev. jun/2025] CVE-Bench (CVEs web de severidade crítica): o melhor framework de agentes resolve **até 13%**. — [arXiv 2503.17332](https://arxiv.org/abs/2503.17332)
- [FATO, out/2024] AutoPenBench (33 tarefas): **21% totalmente autônomo vs 64% com assistência humana**. — [arXiv 2410.03225](https://arxiv.org/abs/2410.03225)
- [FATO, mai/2025, rev. dez/2025] BountyBench (25 sistemas, 40 bounties de US$ 10 a US$ 30.485, 9 riscos do OWASP Top 10; até 3 tentativas): Detect — Codex CLI o3-high 12,5%; Exploit — Claude Code 57,5%, agente customizado Claude 3.7 Sonnet Thinking 67,5%, Codex o3-high 47,5%; Patch — Codex 90%, Claude Code 87,5%. — [arXiv 2505.15216](https://arxiv.org/abs/2505.15216)
- [FATO, ICLR 2026] CyberGym (1.507 instâncias, 188 projetos; foco em reprodução de vulnerabilidades em código): melhor combinação sem thinking 17,9% (OpenHands + Claude Sonnet 4); GPT-5 de 7,7% para 22,0% com thinking. — [arXiv 2506.02548v2](https://arxiv.org/html/2506.02548v2)

**Comparativos em aplicações (2026)**
- [VENDOR, 30/04/2026] Duck Store (FastAPI + React, 20 vulnerabilidades; entrada: URL + **OpenAPI** + 2 credenciais; 1 execução por ferramenta):

  | Ferramenta | Modelo | Achou | Tempo | FP |
  |---|---|---|---|---|
  | Escape | proprietário/multi-modelo | 15/20 (75%) | 4h | 6,25% |
  | PentAGI | DeepSeek v3.2 | 9/20 (45%) | 4h | 10% |
  | Shannon (com código-fonte) | DeepSeek v3.2 | 6/20 (30%) | 6h | 25% |
  | Strix | DeepSeek v3.2 | 1/20 (5%) | 2h | 0% |

  Por classe: IDOR — Escape ✓, PentAGI ✓, Shannon ✗, Strix ✗; lógica de negócio — Escape 75%, PentAGI 75%, Shannon ✗, Strix ✗; access control — Escape 75%, PentAGI 25%, demais ✗; injeção — todos ✓. — [Escape](https://escape.tech/blog/benchmarking-agentic-ai-pentesting-tools/)
- [FATO via terceiros, mar–abr/2026] Doyensec (patrocinado pela Aikido), Fider 0.33.0 + Photoview 2.4.0, US$ 4.000 por scan: 49 achados validados para Aikido e 31 para XBOW; FP 4% (2/49) e 3% (1/31). No Fider: Aikido 17 TP/2 FP, XBOW 24 TP/1 FP; Doyensec rebaixou a severidade de 11 dos 32 achados da Aikido no Photoview. — [Escape in-depth](https://escape.tech/blog/modern-ai-powered-pentesting-tools-in-depth-benchmark/); [Invicti](https://www.invicti.com/blog/security-labs/invicti-agentic-pentest-benchmark-fider-photoview); [Aikido](https://www.aikido.dev/reports/aikido-vs-xbow)
- [SECUNDÁRIO] Sobreposição baixa entre ferramentas no mesmo alvo: no Fider, Aikido 17 e XBOW 24 com apenas 3 coincidentes; no Photoview 32 e 7 com 4 coincidentes. — [devtoollab](https://devtoollab.com/blog/best-ai-penetration-testing-tools)
- [VENDOR, 05/06/2026] Hacktron no Fider: 31 reportados, 27 TP, 4 FP, US$ 350, 27 min; achou 8 de 10 bugs recentemente corrigidos; perdeu um IDOR/bypass de moderação e uma sobrescrita de blob autenticada; severidade bateu com revisão humana em só 22% dos casos (Aikido 76%, XBOW 71%). — [Hacktron](https://www.hacktron.ai/blog/hacktron-vs-xbow-and-aikido)
- [VENDOR, jun/2026] Strobes no Fider: 45 achados validados, 0 FP, ~US$ 1,1k; a própria página informa que "Doyensec did not assess the Strobes run" e contém inconsistências aritméticas (US$ 4.000/13 ≠ US$ 235). — [Strobes whitepaper](https://strobes.co/whitepaper/autonomous-pentesting-benchmark-report)
- [FATO, 10/12/2025] ARTEMIS em rede universitária real (~8.000 hosts): A2 ficou em 2º lugar geral, acima de 9 de 10 pentesters humanos (11 achados, 82% válidos); A1: 11 achados, 55% válidos; Codex (GPT-5): 7, 57%; CyAgent (Sonnet 4): 7, 57%. Claude Code e MAPTA recusaram a tarefa; Incalmo travou no recon. — [arXiv 2512.09882](https://arxiv.org/html/2512.09882v1)

### Inferences
- [INFERÊNCIA] Os "96%" de Shannon e Strix não são comparáveis entre si nem com os 85% do XBOW: condições (white-box vs black-box), modelo e versão do benchmark diferem; o Strix, que reivindica ~96% no XBEN, fez 1/20 no Duck Store com DeepSeek v3.2 — o que indica que placar de CTF + modelo forte não prediz desempenho em app com lógica de negócio (ou que o resultado é fortemente dependente do modelo).
- [INFERÊNCIA] A baixa sobreposição entre ferramentas no mesmo alvo (3 achados em comum no Fider) sugere que nenhuma ferramenta, isoladamente, se aproxima de cobertura completa.
- [INFERÊNCIA] Risco de contaminação é real: Escape relata o modelo frontier "consultando write-ups públicos" e excluiu o Juice Shop das conclusões por memorização provável ([Escape](https://escape.tech/blog/modern-ai-powered-pentesting-tools-in-depth-benchmark/)). Para avaliar um CLI interno, usar um app próprio com vulnerabilidades plantadas (canários), não Juice Shop/crAPI.

### Gaps
- Não achei avaliação independente (sem patrocínio/sem fornecedor) de XBOW, Escape, Strix, Shannon e PentAGI no mesmo alvo. O mais próximo é o protocolo da Ethiack (fornecedora) e o Doyensec (patrocinado).
- Página de resultados do Shannon no XBEN (custo/tempo por desafio, desafios que falharam): HTTP 410. Um resumo de busca citou "US$ 15,50 por desafio" dessa página, não verificado.
- Cybench (arXiv 2408.08926) e o paper original do PentestGPT (arXiv 2308.06782) não foram reabertos nesta sessão; não incluo números deles.
- CVE-Bench: não confirmei nesta sessão o número de CVEs nem a taxa no cenário one-day.
- A afirmação de que "~90% do score do XBOW veio de XSS" apareceu só de segunda mão e não foi confirmada.

## 4. O que agentes acham que scanners não acham — e onde ainda falham

### Takeaway
Agentes com harness multiusuário encontram autorização quebrada (IDOR/BOLA, BFLA), lógica de negócio e inconsistências entre rotas que DAST por assinatura não encontra (ZAP/Metasploit: 0% no HPTSA). As falhas recorrentes são: falsos positivos acima do nível humano (18%–45% sem triagem forte; 0%–6% com validação por exploit, segundo fornecedores), severidade inflada, "provar" exploits inexistentes, superficialidade (reportar e seguir em frente), endpoints não documentados, autenticação não padrão e cadeias multi-etapa.

### Cited Findings

**O que acham a mais**
- [FATO, 2024] ZAP e Metasploit: 0% nas 14 vulnerabilidades reais do HPTSA; o agente hierárquico: 42% pass@5. — [arXiv 2406.01637v2](https://arxiv.org/html/2406.01637v2)
- [VENDOR, 30/04/2026] Exemplo concreto dirigido por spec: Escape achou "update de testimonials sem autenticação" **comparando, no OpenAPI, a rota de criação autenticada com a rota de update não autenticada** — nenhuma outra ferramenta achou. IDOR achado por Escape e PentAGI; lógica de negócio 75% para ambos. — [Escape](https://escape.tech/blog/benchmarking-agentic-ai-pentesting-tools/)
- [FATO, 28/08/2025] Broken authorization: 83% de sucesso do MAPTA no XBOW. — [arXiv 2508.20816](https://arxiv.org/abs/2508.20816)
- [VENDOR, 08/10/2026] 48% dos achados da Invicti vieram da camada agêntica e não do DAST; num Photoview controlado: 1 SQLi crítico + 3 achados altos de autorização/sessão. — [Invicti](https://www.invicti.com/blog/security-labs/invicti-agentic-pentest-benchmark-fider-photoview)
- [VENDOR, jun/2026] Encadeamento: Strobes relata admin takeover em 189 s via endpoint de OTP desprotegido → pivot por webhook → SSRF cego até AWS IMDS. — [Strobes](https://strobes.co/whitepaper/autonomous-pentesting-benchmark-report)
- [FATO, 10/12/2025] Vantagens observadas de agentes: paralelismo (retomam pistas que humanos anotam e esquecem), trabalho sustentado em horizonte longo, exploração via CLI (ex.: `curl -k` em iDRAC antigo que browsers de humanos recusaram). — [arXiv 2512.09882](https://arxiv.org/html/2512.09882v1)
- [CONTRAPONTO, 25/06/2025] As classes que o XBOW destacou (RCE, SQLi, XXE, path traversal, SSRF, XSS) são justamente o "feijão com arroz" de DAST convencional. — [Utku Sen](https://utkusen.substack.com/p/does-xbow-ai-hacker-deserve-the-hype)
- [VENDOR, 23/10/2026] Scanners tradicionais devem continuar como camada complementar: IA dificilmente os iguala em vulnerabilidades conhecidas. — [Cobalt](https://www.cobalt.io/blog/why-one-ai-pentest-run-isnt-enough)

**Onde falham — números de FP/alucinação**
- [FATO, 10/12/2025] Taxa de envios inválidos: ARTEMIS A2 18%, A1 45%, Codex 43%, CyAgent (Sonnet 4) 43%, CyAgent (GPT-5) 20%; humanos majoritariamente 0% (faixa 0–25%). Exemplo de FP: reportou login com credencial default após "200 OK" que na verdade era redirect para a página de login. — [arXiv 2512.09882](https://arxiv.org/html/2512.09882v1)
- [FATO, 11/05/2026] Claude Code: precisão 81,24% (~19% FP); PentAGI-Sonnet: precisão 25,70 p.p. abaixo do Strix-Sonnet; FPs se acumulam rápido na segunda metade da execução enquanto os TPs estabilizam (paygoat, run 3). — [arXiv 2605.10834](https://arxiv.org/html/2605.10834v1)
- [VENDOR, 30/04/2026] FP: Shannon 25%, PentAGI 10%, Escape 6,25%, Strix 0% (com 1 único achado). — [Escape](https://escape.tech/blog/benchmarking-agentic-ai-pentesting-tools/)
- [Doyensec via terceiros, 2026] Plataformas comerciais com validação: Aikido 4% (2/49), XBOW 3% (1/31). — [Escape in-depth](https://escape.tech/blog/modern-ai-powered-pentesting-tools-in-depth-benchmark/)
- [VENDOR] Hacktron 4/31 (~13%) no Fider; Invicti 2,4%; Strobes 0%; Cascade 0%. — [Hacktron](https://www.hacktron.ai/blog/hacktron-vs-xbow-and-aikido); [Invicti](https://www.invicti.com/blog/security-labs/invicti-agentic-pentest-benchmark-fider-photoview); [Strobes](https://strobes.co/whitepaper/autonomous-pentesting-benchmark-report); [Escape](https://escape.tech/blog/modern-ai-powered-pentesting-tools-in-depth-benchmark/)
- [FATO, jun/2025] Mesmo com validadores, 209 de ~1.060 envios do XBOW foram "informative" e 36 "not applicable" (~23% sem valor para o programa), além de 208 duplicados. — [XBOW blog](https://xbow.com/blog/top-1-how-xbow-did-it/)
- [VENDOR, 30/04/2026] Escape admite: modelos podem alucinar e "provar" exploits que não existem; agentes perdem cadeias multi-etapa que exigem pensamento lateral; dificuldade com autenticação não padrão, protocolos de nicho e ambientes muito customizados; recomenda teste humano para alvos de alto valor, lógica de negócio nova e fluxos críticos de compliance. — [Escape](https://escape.tech/blog/ai-pentesting-agents/)
- [FATO] Shannon avisa que relatórios gerados por LLM "can contain weakly supported or incorrect details" e exigem revisão humana. — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)
- [SECUNDÁRIO] "Simplesmente perguntar a um LLM se a vulnerabilidade é real dá FP muito alto" — motivo para validação por evidência (canário/flag/exploit reproduzido). — [Cyberbuilders](https://cyberbuilders.substack.com/p/intelligent-security-requires-validation)

**Onde falham — comportamento**
- [FATO, 10/12/2025] Superficialidade: ARTEMIS submete o achado e segue em frente, enquanto os melhores humanos pivotam mais fundo a partir de um foothold; não operou GUI de browser e perdeu um RCE crítico (TinyPilot), reportando CORS/cookies no lugar. — [arXiv 2512.09882](https://arxiv.org/html/2512.09882v1)
- [FATO, 2024/2025] Descoberta: HPTSA falhou quando o endpoint de API necessário não estava documentado nem visível no site (CVE-2024-25635, alf.io) e quando a rota vulnerável não tinha campos visíveis. — [arXiv 2406.01637v2](https://arxiv.org/html/2406.01637v2)
- [FATO, 28/08/2025] Blind SQLi 0% e XSS 57% no MAPTA — classes sem feedback direto na resposta são difíceis. — [arXiv 2508.20816](https://arxiv.org/abs/2508.20816)
- [FATO, 11/05/2026] "No setup fully covers the targets or reports all known vulnerabilities in a single run"; muitos falsos negativos em todos os setups; modelos open-weight reportam menos. — [arXiv 2605.10834](https://arxiv.org/html/2605.10834v1)
- [FATO, 10/12/2025] Recusas: Claude Code e MAPTA recusaram a tarefa ofensiva "out of the box"; no HPTSA, Llama 3.1 405B recusou ~31% das vezes e modelos abertos não exploraram nada. — [arXiv 2512.09882](https://arxiv.org/html/2512.09882v1); [arXiv 2406.01637v2](https://arxiv.org/html/2406.01637v2)
- [VENDOR, 05/06/2026] Severidade inflada: classificação do Hacktron bateu com a revisão em 22% dos casos; Doyensec rebaixou 11/32 achados da Aikido no Photoview, a maioria para informativo. — [Hacktron](https://www.hacktron.ai/blog/hacktron-vs-xbow-and-aikido); [Escape in-depth](https://escape.tech/blog/modern-ai-powered-pentesting-tools-in-depth-benchmark/)
- [VENDOR, 30/06/2026] Operacional: run do XBOW no Fider levou >1 semana com crashes, reinícios e 20+ e-mails de suporte (relato de concorrente). — [Escape in-depth](https://escape.tech/blog/modern-ai-powered-pentesting-tools-in-depth-benchmark/)
- [FATO] Efeitos colaterais: Shannon não é passivo e pode alterar estado do alvo — usar staging/dados descartáveis. — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)
- [SECUNDÁRIO] Limite conceitual: o agente não consegue checar uma regra de negócio que ele não tem como aprender; regras precisam ser observáveis pelo comportamento (ou fornecidas). — [Strobes blog](https://strobes.co/blog/ai-pentesting-business-logic-flaws/)

### Inferences
- [INFERÊNCIA] Ordem de grandeza de FP: agente sem validador dedicado ≈ 20%–45%; com triagem LLM ≈ 10%–20%; com validação por exploração reproduzida + checagem determinística ≈ 0%–6% (números de fornecedores, então otimistas). O validador é o componente de maior retorno.
- [INFERÊNCIA] Para healthtech (dados sensíveis/LGPD), o ganho sobre o ZAP está em BOLA/BFLA entre contas de teste de tenants/perfis diferentes. Isso exige ≥2 contas por papel e, idealmente, descrição das regras de autorização esperadas como entrada — sem isso o agente só "adivinha" a regra.
- [INFERÊNCIA] Fornecer o OpenAPI mitiga a falha de descoberta vista no HPTSA, mas endpoints fora do spec (shadow APIs) continuam invisíveis; vale combinar com histórico do proxy do ZAP.
- [INFERÊNCIA] Severidade deve ser recalculada por regra/humano, não aceita do agente.

### Gaps
- Não encontrei taxa de "vulnerabilidade alucinada" medida de forma padronizada e independente por ferramenta; os números misturam FP de qualquer origem.
- Não achei dados públicos específicos para mass assignment (BOPLA) por agentes.
- Sem dados quantitativos independentes sobre fluxos stateful longos (ex.: agendamento → pagamento → cancelamento) — só afirmações qualitativas de fornecedores.

## 5. Não-determinismo e variância entre execuções

### Takeaway
A evidência disponível (pouca, mas consistente) diz que execuções repetidas no mesmo alvo acham coisas diferentes e que a união de k execuções aumenta o recall — às vezes quase dobrando — ao custo de acumular falsos positivos. O grau de variância depende do harness: PentAGI repetiu ~75% dos verdadeiros positivos nas 3 execuções; Strix teve sobreposição bem menor.

### Cited Findings
- [FATO, 11/05/2026] 3 execuções por configuração: nenhuma cobre tudo em uma execução; agregar 3 execuções melhora F1 via recall; **Strix-Sonnet quase dobra o recall no acumulado** e atinge o maior F0.5 cumulativo (atribuído à estocasticidade do harness do Strix); para PentAGI-Sonnet o F1 acumulado cai abaixo da média por execução porque FPs acumulam mais rápido que o recall. — [arXiv 2605.10834](https://arxiv.org/html/2605.10834v1)
- [FATO, 22/07/2026] ~75% dos TPs do PentAGI Sonnet 4.6 aparecem nas três execuções, contra sobreposição muito menor no Strix Sonnet 4.6; rodar ~40% do custo do benchmark completo retém >80% de correlação com o resultado completo. — [Ethiack parte 2](https://ethiack.com/info-hub/research/evaluating-pentesting-agents-part-2)
- [FATO, 2024/2025] pass@1 = 18% vs pass@5 = 42% no HPTSA: 5 tentativas mais que dobram o sucesso; estudo de caso (flusity-CMS) mostra execuções individuais variando entre sucesso e falha no mesmo alvo. — [arXiv 2406.01637v2](https://arxiv.org/html/2406.01637v2)
- [FATO] BountyBench avalia com até 3 tentativas por tarefa. — [arXiv 2505.15216](https://arxiv.org/abs/2505.15216)
- [VENDOR, 23/10/2026 — ilustrativo, não é dado medido] Tabela de exemplo da Cobalt: 4 execuções achando 4, 5, 3 e 4 de 8 vulnerabilidades; união 7/8 (88%); uma vulnerabilidade perdida por todas. O texto diz "nenhuma execução acima de 50%" mas a tabela mostra uma com 62,5%; não cita agente, alvo ou estudo. Observa que, como o total de vulnerabilidades é desconhecido, não dá para calcular quantas reexecuções bastam. — [Cobalt](https://www.cobalt.io/blog/why-one-ai-pentest-run-isnt-enough)
- [VENDOR, 30/04/2026] Escape rodou cada ferramenta uma única vez e reconhece o não-determinismo: resultados são "snapshot", não ranking. — [Escape](https://escape.tech/blog/benchmarking-agentic-ai-pentesting-tools/)
- [FATO, 2026] Sobreposição baixa também entre ferramentas diferentes no mesmo alvo (Fider: 3 achados em comum entre Aikido e XBOW). — [devtoollab](https://devtoollab.com/blog/best-ai-penetration-testing-tools)

### Inferences
- [INFERÊNCIA] Para QA: um run de agente não é um teste de regressão determinístico. Tratar como amostragem — rodar k≥3 por release (ou rodadas diferenciais por endpoints alterados), unir, deduplicar e passar tudo pelo validador; a precisão da união depende inteiramente do validador.
- [INFERÊNCIA] Todo achado validado deve virar um caso de regressão determinístico (requisição + asserção, ex.: teste JUnit/RestAssured ou template nuclei) — é o que dá repetibilidade; o agente fica para descoberta.
- [INFERÊNCIA] Diversificar deliberadamente (modelos diferentes, ordem de endpoints, seeds de prompt) deve aumentar a cobertura da união, na linha recomendada pela Cobalt — sem evidência quantitativa pública.
- [INFERÊNCIA] Limitar o tempo de execução por sub-tarefa ajuda a precisão: FPs crescem no fim das execuções longas enquanto TPs estabilizam.

### Gaps
- Não achei estudo revisado por pares com curva "tamanho da união vs k" para agentes de pentest em alvos web/API; o melhor dado é o k=3 da Ethiack (fornecedora) e pass@5 do HPTSA (2024, GPT-4).
- Valores absolutos por execução (recall/precisão) do paper da Ethiack estão em figuras; só extraí diferenças pareadas.
- Sem dados sobre variância com temperatura 0 ou com prompts/planos fixados.

## 6. Tempo de execução e custo por alvo/run

### Takeaway
Ordem de grandeza em 2026: ferramentas open source com chave própria custam de dezenas a poucas centenas de dólares de LLM e levam 1–6 h por aplicação; plataformas comerciais cobram ~US$ 350 a US$ 4.000–8.000 por pentest e levam de ~30 min a mais de uma semana. Em desafios CTF isolados o custo é de centavos a poucos dólares por desafio. Quase todos os números são auto-reportados e dependem do modelo.

### Cited Findings
- [FATO] Shannon: execução completa leva ~1–1,5 h; o README atual **não dá valor em dólar** (custo depende do modelo e da complexidade). — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)
- [SECUNDÁRIO] O "~US$ 50 por run com Claude 4.5 Sonnet" do Shannon vem de reviews que citam a documentação antiga da Keygraph. — [DEV/max_quimby](https://dev.to/max_quimby/shannon-ai-review-autonomous-web-pentesting-agent-3jdi); [agentconn](https://agentconn.com/blog/shannon-ai-pentester-review-autonomous-web-security-2026)
- [VENDOR, abr/2026] No benchmark da Escape o Shannon levou 6 h (com DeepSeek v3.2), PentAGI 4 h, Escape 4 h, Strix 2 h; custo não reportado. — [Escape](https://escape.tech/blog/benchmarking-agentic-ai-pentesting-tools/)
- [VENDOR, 30/06/2026] Tempo por app: Cascade ~1,5 h; Claude Opus 4.8 sem harness ~1 h; Aikido ~8 h; XBOW ~2 dias (Photoview) e >1 semana (Fider), com relatório até 5 dias após o scan; uso de modelo cru pode custar "hundreds of dollars a day on tokens". — [Escape in-depth](https://escape.tech/blog/modern-ai-powered-pentesting-tools-in-depth-benchmark/)
- [FATO via terceiros, 2026] Aikido e XBOW: US$ 4.000 por scan no estudo Doyensec. Hacktron: US$ 350 e 27 min no Fider. — [Hacktron](https://www.hacktron.ai/blog/hacktron-vs-xbow-and-aikido)
- [VENDOR, out/2026] Invicti: 46 min (Fider) e 50 min (Photoview); US$ 345,54 no total a preço introdutório (~US$ 6,64 por achado). — [Invicti](https://www.invicti.com/blog/security-labs/invicti-agentic-pentest-benchmark-fider-photoview)
- [VENDOR, jun/2026] Strobes: ~US$ 1,1k em créditos no Fider (US$ 22–27 por achado); XBOW ~US$ 167 por achado. — [Strobes](https://strobes.co/whitepaper/autonomous-pentesting-benchmark-report)
- [CONFLITO] XBOW Pentest On-Demand: "starts at $4,000" ([xbow.com/pentest](https://xbow.com/pentest)) vs US$ 6.000 em release sindicado ([StreetInsider](https://www.streetinsider.com/Press+Releases/Announcing+XBOW+Pentest+On-Demand+for+Security+at+Machine+Speed/25603595.html)); resultados em até ~5 dias úteis; preço público removido em jul/2026 ([CodeAnt](https://codeant.ai/blogs/xbow-pricing)).
- [SECUNDÁRIO] Aikido: Standard US$ 4.000, Advanced US$ 8.000. — [G2](https://www.g2.com/products/aikido-security/pricing)
- [FATO] Shannon Pro: US$ 50 por desenvolvedor ativo/mês. — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)
- [SECUNDÁRIO, ago/2026] Strix: ~US$ 3,37 por desafio XBEN com GPT-5.4 (≈ US$ 350 para os 104). — [DEV/Creeta](https://dev.to/creeta/strix-claims-96-on-xben-that-number-is-vendor-reported-3en8)
- [maintainer-reported, dez/2025] PentestGPT: média US$ 1,11 / mediana US$ 0,42 por benchmark resolvido; 6,1 min em média. — [mirror do README](https://gitcode.com/GitHub_Trending/pe/PentestGPT/blob/main/README.md)
- [FATO, 28/08/2025] MAPTA: US$ 21,38 no total para os 104 desafios; mediana US$ 0,073 nos sucessos vs US$ 0,357 nas falhas; US$ 3,67 em média por avaliação de repositório open source real. — [arXiv 2508.20816](https://arxiv.org/abs/2508.20816)
- [FATO, 2024/2025] HPTSA (GPT-4): US$ 4,39 por execução, US$ 24,4 por exploit bem-sucedido; estimativa de humano ~US$ 75. — [arXiv 2406.01637v2](https://arxiv.org/html/2406.01637v2)
- [FATO, 10/12/2025] ARTEMIS: A1 US$ 291,47 no total (~US$ 18,21/h) com 55% de envios válidos; A2 US$ 944,07 (~US$ 59/h) com 82% válidos; pentester profissional ~US$ 60/h. A configuração barata é a de pior precisão. — [arXiv 2512.09882](https://arxiv.org/html/2512.09882v1)
- [FATO, mai/2025] BountyBench reporta valor em dólar dos bounties correspondentes (ex.: Detect do Codex o3-high ≈ US$ 3.720), não custo de execução. — [arXiv 2505.15216](https://arxiv.org/abs/2505.15216)
- [VENDOR] Escape afirma que um pentest de aplicação web pode terminar em ~2 h. — [Escape](https://escape.tech/blog/ai-pentesting-agents/)
- [SECUNDÁRIO] PentAGI: a delegação multiagente consome mais tokens que o modo de agente único. — [docs PentAGI (mirror)](https://www.mintlify.com/vxcontrol/pentagi/features/autonomous-testing)

### Inferences
- [INFERÊNCIA] Para um CLI interno com modelo frontier, uma estimativa defensável é US$ 20–150 e 1–4 h por execução completa de uma API de porte médio; rodar k=3 multiplica o custo. Roteamento de modelos (barato para recon/enumeração, forte para raciocínio de autorização/validação) e early-stop por sub-tarefa (~40 tool calls, como no MAPTA) são as alavancas de custo com respaldo.
- [INFERÊNCIA] Falhas custam mais que sucessos (MAPTA: ~5× na mediana) — orçamento por sub-tarefa evita que endpoints "sem saída" consumam a maior parte do gasto.
- [INFERÊNCIA] Comparado a US$ 4.000 por pentest comercial, construir internamente compensa pelo custo marginal, mas o custo real está em engenharia do harness (autenticação, validadores, deduplicação), que é exatamente o que os benchmarks apontam como diferencial.

### Gaps
- Custo em tokens/dólar por run de Strix e PentAGI em aplicações reais (não CTF): não encontrei fonte primária; o paper da Ethiack diz que Claude Code teve o menor custo e PentAGI-Sonnet o maior, mas sem valores absolutos no texto.
- O "~US$ 50 por run" do Shannon não consta mais no README atual; tratar como dado de 2025/início de 2026 de fonte secundária.
- Preço efetivo do Neo (pay-as-you-go) e do Escape: não obtidos.
- Nenhuma fonte dá custo por endpoint de API, que seria a métrica mais útil para dimensionar o CLI.
