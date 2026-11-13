# Economia e operação por release de um harness de testes de segurança de API baseado em agente LLM

Data de coleta: 2026-11-12. Todos os preços/figuras têm a data em que foram lidos e a URL. Convenções: **[VERIFICADO]** = lido em fonte primária nesta sessão; **[ALEGAÇÃO DE FORNECEDOR]** = número publicado pelo próprio vendedor/projeto; **[TERCEIRO]** = blog/agregador, não confirmado na fonte primária; **ESTIMATIVA** = cálculo ou julgamento meu, não publicado em lugar nenhum.

Aviso geral de qualidade: a maior parte dos números de custo por execução de agentes de pentest vem de fornecedores ou de blogs que vendem produtos concorrentes. Não encontrei nenhum benchmark independente e revisado por pares de custo por execução contra uma API real (não-CTF).

---

## 1. Build vs. buy: harnesses open-source, runtimes de agente e opções comerciais

### Takeaway
Não é preciso construir o loop de agente do zero: Strix (Apache-2.0) já faz teste black-box contra URL hospedada com OpenAPI/Postman, modo não-interativo e teto de orçamento, e é o candidato mais direto a "adotar ou embrulhar"; Shannon open-source é AGPL-3.0 e white-box (precisa do código-fonte), então não atende o caso "só URL + spec" sem a edição paga. As opções comerciais de "AI pentest" giram em torno de US$ 4.000 por teste (Aikido, XBOW), o que as torna inviáveis para "toda release" mas úteis como comparação de valor.

### Cited Findings

**Open-source — harnesses prontos**
- **Strix** (usestrix/strix): licença Apache-2.0; 75,2k stars; aceita `strix --target https://your-app.com` como "Black-box web application assessment"; aceita arquivos OpenAPI/Swagger, exports Postman ou coleções Postman por ID combinados com uma base URL viva; teste autenticado (grey-box) passando credenciais em `--instruction`; modo `-n/--non-interactive` que "Exits with non-zero code when vulnerabilities are found"; exemplo de GitHub Actions em `pull_request` (`strix -n -t ./ --scan-mode quick`); provedores: OpenAI, Anthropic, Google/Vertex, Bedrock, Azure, OpenRouter, DeepSeek, modelos locais via `LLM_API_BASE`; ferramentas embutidas: proxy HTTP (Caido), browser automatizado, shell, sandbox Python; resultados em `strix_runs/<run-name>` e visualizador local `strix view`. O README não descreve explicitamente múltiplas contas/papéis nem formatos de relatório (SARIF/JSON) — [VERIFICADO, lido em 2026-11-12] — [GitHub usestrix/strix](https://github.com/usestrix/strix)
- Strix: a referência de CLI define modos quick/standard/deep, escopo diff/full e um orçamento máximo de modelo; `--max-budget-usd` descrito como teto rígido que encerra o loop, grava os achados confirmados em `strix_runs/` e sai com código de status próprio — [TERCEIRO; não confirmei na doc oficial do CLI] — [wavect.io pilot guide](https://wavect.io/blog/strix-ai-pentesting-pilot-guide-2026/); [Medium/codetodeploy](https://medium.com/codetodeploy/strix-ai-pentest-in-ci-cd-keep-llm-costs-under-1-per-pr-4df6981b9ffb)
- Strix hospedado: Pro a US$ 29/seat/mês com pentests cobrados à parte por teste (snapshot de 2026-08-09 da página de preços, relatado por terceiro); Strix Cloud usa créditos pré-pagos consumidos por token — [TERCEIRO] — [wavect.io](https://wavect.io/blog/strix-ai-pentesting-pilot-guide-2026/)
- **Shannon** (KeygraphHQ/shannon): open-source sob **AGPL-3.0**; 51,8k stars; a edição open-source é **white-box** (lê o código-fonte montado read-only); teste **black-box é recurso de Pro/Enterprise/Community Program** ou do produto separado "Blackbox Pentester"; Pro a **US$ 50 por desenvolvedor ativo/mês**, Enterprise sob consulta, Community Program gratuito para ONGs e startups pequenas elegíveis; execução completa ~1–1,5 h (README); BYOK, provedores Anthropic, OpenAI, xAI, Bedrock; a versão 1.9.0 foi "the final release built on the Claude Agent SDK" (migrou para o harness "Pi"); autenticação por arquivo de configuração (credenciais, fluxo de login, TOTP, e-mail) — detalhes em `docs/configuration.md`; integrações oficiais GitHub Actions (`KeygraphHQ/shannon-action`) e GitLab CI; gates de severidade contam só achados com `status: exploited`; relatórios PDF, Markdown, JSON e **SARIF 2.1.0**; limitações declaradas: achados exigem revisão humana, relatórios do LLM podem conter detalhes incorretos, risco de prompt injection em codebases não confiáveis — [VERIFICADO, 2026-11-12] — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)
- **PentAGI** (vxcontrol/pentagi): núcleo sob licença MIT; serviços VXControl Cloud exigem License Key separada; um blog afirma que forks que usam a integração do VXControl Cloud SDK ficam sujeitos a AGPL-3.0 (fonte única, verificar no LICENSE do repo) — [TERCEIRO] — [themenonlab.blog](https://themenonlab.blog/blog/pentagi-autonomous-ai-pentesting-multi-agent); [everydev.ai](https://www.everydev.ai/tools/pentagi)

**Runtime de agente para construir (Claude Agent SDK / Claude Code headless)**
- Claude Code headless/Agent SDK oferece `--max-turns` (limita turnos agênticos; sai com erro no limite) e `--max-budget-usd` (teto de gasto por invocação; ao exceder retorna resultado com subtype `error_max_budget_usd`); a mensagem de resultado traz `total_cost_usd`, que a doc oficial descreve como estimativa do lado do cliente, não dado de faturamento autoritativo; cada `query()` devolve seu próprio total — é preciso acumular entre chamadas — [VERIFICADO parcialmente: doc oficial em japonês + terceiros] — [code.claude.com cost-tracking](https://code.claude.com/docs/ja/agent-sdk/cost-tracking); [mer.vin](https://mer.vin/news/what-max-budget-usd-actually-kills-mid-agent-loop/)
- Sinal de mercado: Shannon abandonou o Claude Agent SDK após a v1.9.0 em favor de harness agnóstico de provedor — [VERIFICADO] — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)

**Comerciais — preços públicos**
- **Aikido AI Pentest** (1 crédito = US$ 1): Standard Pentest 4.000 créditos (uma aplicação e suas APIs primárias, time-boxed); referência black-box: Standard 4.000 / Large 8.000 / Complex 16.000 / Enterprise 32.000; **Continuous Pentesting: 10 créditos por execução de agente** — só lança agentes para mudanças relevantes de segurança a cada deploy ou execução agendada; todo nível inclui relatório compliance-ready e reteste; página sem data — [VERIFICADO, lido em 2026-11-12] — [help.aikido.dev pentest-pricing](https://help.aikido.dev/pentests/pentest-pricing.md)
- **XBOW**: página de preços listava Plus US$ 4.000/teste e Premium US$ 8.000/teste; release de nov/2025 falava em a partir de US$ 6.000; um blog concorrente (CodeAnt) afirma que os tiers publicados sumiram de xbow.com/pricing em meados de julho/2026 e que agora é "Request Pricing" — **evidência conflitante, preço atual não verificado** — [xbow.com/pentest](https://xbow.com/pentest); [Business Wire 2025-11-12](https://www.businesswire.com/news/home/20251112470912/en/); [codeant.ai](https://codeant.ai/blogs/xbow-pricing)
- **StackHawk**: plano "Wingman" US$ 10/usuário/mês, apps ilimitados, 50 scans/usuário/mês, trial de 14 dias, sem plano gratuito permanente; plano "Scale" sob consulta (scans ilimitados, API discovery, SSO) — [VERIFICADO, 2026-11-12] — [stackhawk.com/pricing](https://www.stackhawk.com/pricing/). Agregadores citam US$ 5, 25, 42 e 49 por contribuidor — desatualizados/conflitantes — [appsecsanta.com](https://appsecsanta.com/appsec-pricing-guide)
- **Escape**: não publica preço de plataforma; um blog concorrente (Aikido) diz que Escape lista AI pentest on-demand a US$ 3.000 por unidade no AWS Marketplace em contrato de 12 meses — [TERCEIRO/concorrente, não verificado] — [aikido.dev/blog/escape-tech-alternatives](https://www.aikido.dev/blog/escape-tech-alternatives)
- **42Crunch**: Capterra lista a partir de US$ 15/mês/usuário (Single User) e Teams a US$ 375/mês até 25 usuários; Enterprise não listado — [TERCEIRO] — [capterra.com](https://www.capterra.com/p/10032364/42Crunch/)
- **Akto**: núcleo open-source gratuito; guia de 2025 cita plano Professional ~US$ 1.890/mês para 500 endpoints (out/2025) — [TERCEIRO, publicado no blog de um concorrente (Pynt)] — [pynt.io](https://www.pynt.io/learning-hub/api-security-guide/api-discovery-tools)
- **Pynt**: listagem Slashdot 2026 mostra US$ 1.888/mês; outro guia diz preço enterprise sob consulta — [TERCEIRO, conflitante] — [slashdot.org](https://slashdot.org/software/p/42Crunch/alternatives)

**Carga de manutenção de tooling LLM caseiro**
- Recomendações de prática: quando o modelo é atualizado, rodar evals nas versões atual e anterior do prompt; exigir evals de regressão antes de promover mudança — [druce.ai, 2026-09](https://druce.ai/2026/09/agent-reliability-engineering)
- Braintrust: evals que importam permitem trocar de modelo em 24 h e se alimentam de bugs reais — [braintrust.dev](https://www.braintrust.dev/blog/five-lessons-evals)
- Paper de 2024 sobre agente de pentest com LLMs off-the-shelf conclui que o agente "can be constantly improved through prompt engineering driven by usage" (ou seja, manutenção contínua de prompt é parte do modelo operacional) — [arXiv 2401.17459](https://arxiv.org/html/2401.17459)
- Tokenizer muda entre gerações: modelos Claude 4.7+ produzem ~30% mais tokens para o mesmo texto que Sonnet 4.6 e anteriores — upgrade de modelo altera custo mesmo com preço por token igual — [VERIFICADO] — [platform.claude.com pricing](https://platform.claude.com/docs/en/about-claude/pricing)

### Inferences
- Para "só URL hospedada + OpenAPI + contas de teste", Strix é o único dos open-source verificados que cobre o caso sem código-fonte e com licença permissiva. Shannon OSS exigiria montar o repositório (o que a equipe pode até ter, mas muda o desenho para white-box) e traz AGPL.
- AGPL-3.0 para uso interno: rodar o Shannon sem modificá-lo, como ferramenta interna de CI, não aciona obrigação de publicar código; a cláusula de rede (seção 13) passa a importar se o harness **modificado** for oferecido como serviço a terceiros pela rede. Embrulhar via CLI/processo separado é diferente de linkar/derivar. **Isto é minha leitura geral da licença, não parecer jurídico e não foi verificado contra fonte nesta sessão** — validar com jurídico se houver intenção de modificar.
- O "Continuous Pentesting" do Aikido (US$ 10 por execução de agente, disparado só em mudanças relevantes) é o único preço comercial verificado cujo formato se aproxima de "por release"; os demais são por engajamento (~US$ 4k) ou por seat.
- StackHawk Wingman (US$ 10/usuário/mês, 50 scans) é DAST determinístico barato; para uma equipe de 1 QA é ordem de grandeza mais barato que qualquer coisa agêntica comercial, mas não cobre lógica de negócio/BOLA com o mesmo raciocínio de um agente (inferência; não testado).
- ESTIMATIVA de desenho híbrido para equipe minúscula: (a) camada determinística (ZAP API scan + Schemathesis/nuclei) em toda release; (b) Strix (ou harness próprio fino sobre Claude Agent SDK) para autorização/lógica, com orçamento por produto; (c) DefectDojo para ciclo de vida. Construir só a "cola" (config por produto, fingerprint, replays) em vez do loop de agente.

### Gaps
- **CAI (aliasrobotics)**: licença e maturidade não verificadas nesta sessão (a busca não retornou resultados).
- **OpenAI Agents SDK, LangGraph**: não pesquisados nesta sessão; nenhum dado com fonte.
- **MCP servers para ZAP/Burp/nuclei**: não verifiquei existência/estado de add-on MCP oficial do ZAP ou do Burp em nov/2026.
- Suporte explícito a **múltiplas contas/papéis** (matriz de autorização) em Strix: README só menciona credenciais via `--instruction`; não confirmado se há config estruturada por papel.
- Preço atual de XBOW, Escape, Pynt, Akto, 42Crunch: nenhum confirmado em página oficial do fornecedor nesta sessão.
- Não encontrei relato público quantificado (horas/mês) do custo de manutenção de um agente de pentest caseiro.

---

## 2. Estimativas de esforço para construir

### Takeaway
Não encontrei nenhum relato público confiável com número de pessoas-mês para construir um agente de pentest de API comparável; qualquer número aqui é estimativa minha.

### Cited Findings
- A busca por write-ups "we built an AI pentester" com esforço quantificado não retornou nenhum post específico; os resultados foram textos genéricos de lições sobre agentes/evals — [druce.ai](https://druce.ai/2026/09/agent-reliability-engineering); [AWS DevOps Agent blog](https://aws.amazon.com/blogs/devops/from-ai-agent-prototype-to-product-lessons-from-building-aws-devops-agent/)
- Indicador indireto de complexidade: Shannon e Strix são produtos com dezenas de milhares de stars, edições pagas e (Shannon) troca de runtime de agente entre versões — isto é, projetos mantidos por empresas, não scripts de fim de semana — [Shannon](https://github.com/KeygraphHQ/shannon); [Strix](https://github.com/usestrix/strix)

### Inferences
- **ESTIMATIVA** (minha, para 1 QA com base Java/Spring, usando runtime pronto como Claude Agent SDK ou embrulhando o Strix):
  - PoC "agente + HTTP client + OpenAPI + 2 contas, relatório Markdown" contra 1 produto: 1–2 semanas.
  - MVP operável (config por produto, auth por papel, orçamento, saída SARIF/JSON com fingerprint, import no DefectDojo, job de CI não-bloqueante): 4–8 semanas adicionais.
  - Robustez (replays determinísticos de achados, suíte de eval com alvos vulneráveis conhecidos, modo incremental por spec-diff, 3+ produtos): mais 2–3 meses em tempo parcial.
  - Manutenção recorrente: 2–4 dias/mês (upgrades de modelo, deriva de prompt, quebras de auth dos ambientes, triagem de falsos positivos).
  - Embrulhar o Strix em vez de escrever o loop reduz principalmente as duas primeiras fases; a "cola" (config, dedup, replays, CI) permanece.

### Gaps
- Sem dados públicos de esforço real; as faixas acima não têm fonte e devem ser apresentadas como estimativa.

---

## 3. Custo e tempo de LLM por execução; preços de API em nov/2026; controle de custo

### Takeaway
Os números publicados para uma execução agêntica completa contra uma aplicação variam de ~US$ 6 a ~US$ 115 e de ~2,5 h a ~5,5 h dependendo do modelo (Shannon, white-box, uma execução por modelo); em benchmarks estilo CTF/CVE o custo fica em ~US$ 0,3–10 por tarefa. Com os preços de nov/2026 (cache read a 2,5–10% do input, batch a 50%), o modelo e a disciplina de contexto dominam o custo.

### Cited Findings

**Custo/tempo publicados por execução**
- Shannon v3 vs Photoview 2.4.0 (white-box, exploit mode, só credencial admin, **uma execução por modelo**): DeepSeek v4 Flash **US$ 6,10 / 2h37**, 18 reportados/18 TP; Grok 4.6 **US$ 35,07 / 5h26**, 10/10 TP; Claude Opus 5 **US$ 115 / 2h24**, 24 reportados/23 TP/1 FP. Comparadores (do estudo Doyensec): Aikido US$ 4.000, <8 h, 32 TP; XBOW US$ 4.000, ~2 dias, 7 TP. Recall sobre 7 vulnerabilidades depois corrigidas: Opus 6/7, Grok 3/7, DeepSeek 3/7. Tokens não reportados. Concordância de severidade com reavaliação manual: 50–72% — [ALEGAÇÃO DE FORNECEDOR; sem data explícita, ©2026] — [shannon-xbow-aikido-benchmark.md](https://github.com/KeygraphHQ/shannon/blob/main/docs/shannon-xbow-aikido-benchmark.md)
- Shannon README: execução completa ~1–1,5 h (conflita com 2,4–5,4 h do próprio benchmark v3) — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon). Reviews antigas citam ~US$ 50 por execução, atrelado a preços de Claude 3.5 Sonnet (desatualizado) — [TERCEIRO] — [byteiota.com](https://byteiota.com/shannon-ai-pentester-96-success-50-cost/)
- Strix no benchmark XBEN: ~US$ 3,37 por desafio, ~US$ 337 para 104 desafios, 100/104 resolvidos (CTF, não aplicação real) — [TERCEIRO] — [news.creeta.com](https://news.creeta.com/en/strix-ai-pen-testing-agents-vs-nuclei-zap/)
- Strix em scans reais (blogs, pouco confiáveis e mutuamente inconsistentes): "40.000–100.000 tokens" para scan standard em app média; um scan com 340.000 tokens = US$ 5,10 a preço GPT-5.4; "~US$ 3–20/scan"; um avaliador avisa que o custo/tokens reportados pelo Strix "can be quite inaccurate" — [TERCEIRO] — [wavect.io](https://wavect.io/blog/strix-ai-pentesting-pilot-guide-2026/); [theartificialq.github.io 2026-04-14](https://theartificialq.github.io/2026/04/14/agentic-ai-pentesting-with-strix-results-from-18-llm-models.html)
- CVE-Bench (paper): custo total do benchmark abaixo de US$ 100; médias por configuração ~US$ 0,60–1,70 por tarefa (média de 5 repetições); cenário one-day custa mais que zero-day — [arXiv 2503.17332](https://arxiv.org/html/2503.17332v3)
- Cybench (subconjunto defensivo, site de terceiro): de US$ 0,23/tarefa (MiniMax M2.1, 11,1% acerto) a US$ 9,71/tarefa (Claude Opus 4.5, 61,1%) — [TERCEIRO] — [cotool.ai](https://www.cotool.ai/research/cybench)
- BountyBench reporta métricas de uso/custo de tokens por tarefa, mas não obtive os valores — [crfm.stanford.edu](https://crfm.stanford.edu/2025/05/21/bountybench.html)

**Preços oficiais de API (lidos em 2026-11-12; USD por milhão de tokens)**
- **Anthropic** — [platform.claude.com/docs/en/about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing):

| Modelo | Input | Cache write 5m | Cache write 1h | Cache hit | Output |
|---|---|---|---|---|---|
| Claude Fable 5.2 | 8 | 10 | 16 | 0,20 | 40 |
| Claude Fable 5.1 | 10 | 12,50 | 20 | 0,25 | 50 |
| Claude Opus 5.5 | 4 | 5 | 8 | 0,20 | 20 |
| Claude Opus 5 | 5 | 6,25 | 10 | 0,50 | 25 |
| Claude Sonnet 5.5 | 2 | 2,50 | 4 | 0,10 | 10 |
| Claude Sonnet 5 | 2 | 2,50 | 4 | 0,20 | 10 |
| Claude Haiku 5.5 (prompt ≤100k tokens) | 0,10 | 0,125 | 0,20 | 0,01 | 0,50 |
| Claude Haiku 5.5 (prompt >100k tokens) | 0,50 | 0,625 | 1 | 0,05 | 2,50 |
| Claude Haiku 4.5 | 1 | 1,25 | 2 | 0,10 | 5 |

  - Cache hit = 0,025× input em Fable 5.1/5.2; 0,05× em Opus 5.5 e Sonnet 5.5; 0,1× nos demais. Mythos 5.x tem os mesmos preços do Fable mas disponibilidade limitada a organizações verificadas (ex.: Cyber Verification Program). `inference_geo: "us"` aplica multiplicador 1,1× — mesma fonte.
- **OpenAI** (contexto curto ≤272K) — [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing) (openai.com/api/pricing retornou HTTP 403):

| Modelo | Input | Cached input | Output |
|---|---|---|---|
| gpt-6-astra | 10,00 | 1,00 | 50,00 |
| gpt-6.1-sol | 2,00 | 0,10 | 10,00 |
| gpt-6.1-terra | 1,00 | 0,05 | 5,00 |
| gpt-6-luna | 0,10 | 0,01 | 0,50 |
| gpt-5.6-sol | 4,00 | 0,40 | 20,00 |
| gpt-5.5 | 5,00 | 0,50 | 30,00 |
| gpt-5.4 | 2,50 | 0,25 | 15,00 |

  - Batch API = 50% do preço padrão em input, cached input e output — mesma fonte.
- **Google Gemini** (paid tier) — [aistudio.google.com/docs/pricing](https://aistudio.google.com/docs/pricing) (ai.google.dev/gemini-api/docs/pricing redireciona para lá):

| Modelo | Input | Output | Context caching |
|---|---|---|---|
| Gemini 3.1 Pro Preview (≤200k / >200k) | 2,00 / 4,00 | 12,00 / 18,00 | 0,20 / 0,40 + US$ 4,50 por 1M tokens/hora de storage |
| Gemini 3.8 Flash (até 2026-12-31) | 0,75 | 3,75 | 0,075 |
| Gemini 3.8 Flash (a partir de 2027-01-01) | 1,50 | 7,50 | 0,15 |
| Gemini 3.5 Flash-Lite | 0,30 | 2,50 | 0,03 |
| Gemini 3.1 Flash-Lite | 0,25 | 1,50 | 0,025 |

  - Batch = "50% cost reduction". A página também lista Gemini 4 Carbon/Argon/Hydrogen, cujos preços não capturei (página truncada em 100k caracteres). Atenção: o preço do Gemini 3.8 Flash **dobra em 2027-01-01** — mesma fonte.

**Técnicas de controle de custo (com fonte)**
- Prompt caching: leitura de cache custa 2,5–10% do input na Anthropic; 5–10% na OpenAI; ~10% no Gemini (mais storage por hora) — fontes das tabelas acima.
- Batch API a 50% (OpenAI, Gemini) — útil para triagem/dedup/redação de relatório offline, não para o loop interativo — fontes acima.
- Tiering por modelo comprovadamente muda a ordem de grandeza: mesma ferramenta e alvo, US$ 6,10 (DeepSeek) vs US$ 115 (Opus 5), com recall 3/7 vs 6/7 — [Shannon benchmark](https://github.com/KeygraphHQ/shannon/blob/main/docs/shannon-xbow-aikido-benchmark.md)
- Teto de orçamento/turnos: `--max-budget-usd`, `--max-turns` (Claude Code/Agent SDK) — [code.claude.com](https://code.claude.com/docs/ja/agent-sdk/cost-tracking); `--max-budget-usd` e modos quick/standard/deep no Strix — [TERCEIRO] — [wavect.io](https://wavect.io/blog/strix-ai-pentesting-pilot-guide-2026/)
- Escopo por diff em PR: no Strix, "quick" em PR é limitado aos arquivos alterados — [GitHub usestrix/strix](https://github.com/usestrix/strix); Aikido Continuous só lança agentes para mudanças relevantes de segurança — [help.aikido.dev](https://help.aikido.dev/pentests/pentest-pricing.md)
- Faixa de preço por tamanho de prompt: Haiku 5.5 custa 5× mais acima de 100k tokens de prompt; Gemini 3.1 Pro 2× acima de 200k; OpenAI tem tarifa maior acima de 272K — manter contexto curto (truncar/sumarizar respostas HTTP) tem efeito direto de preço — fontes das tabelas acima.

### Inferences
- **ESTIMATIVA** de custo por execução de um harness próprio black-box (hipótese: 3M tokens de input acumulados no loop, 85% lidos de cache, 150k tokens de output; ignora cache writes):
  - Claude Sonnet 5.5: 0,45M×2 + 2,55M×0,10 + 0,15M×10 ≈ **US$ 2,7**
  - Claude Fable 5.2: 0,45M×8 + 2,55M×0,20 + 0,15M×40 ≈ **US$ 10**
  - Claude Haiku 5.5 (≤100k): ≈ **US$ 0,15**
  - Sem cache (Sonnet 5.5): 3M×2 + 1,5 ≈ US$ 7,5 — o cache reduz ~65% neste perfil.
  - A hipótese de volume de tokens é minha; os dados reais de Shannon (US$ 6–115) sugerem que execuções profundas consomem bem mais. Faixa de planejamento razoável: **US$ 3–40 por produto por release** com modelo intermediário e orçamento fixo; **US$ 100+** com modelo de topo sem teto.
- Técnicas sem fonte específica encontrada nesta sessão, mas decorrentes da estrutura de preços (tratar como recomendações minhas): orçamento por endpoint; deixar ZAP/nuclei/ffuf gerar o tráfego em massa e passar ao LLM só resumos; persistir o "entendimento da API" (mapa de recursos, papéis, IDs de objetos) como artefato entre execuções para não repagar reconhecimento; truncar corpos de resposta (status + headers relevantes + primeiros N bytes + diff contra baseline).
- Tempo de parede de 2,5–5,5 h (Shannon) é incompatível com gate síncrono de pipeline; implica execução assíncrona/noturna.

### Gaps
- Nenhum número de **tokens** por execução publicado por Shannon/XBOW; XBOW não publica custo interno.
- PentAGI e AutoPenBench: nenhum custo por execução/tarefa encontrado.
- Nenhum dado publicado para o cenário exato (black-box, só API, OpenAPI, múltiplos papéis).
- Preços dos modelos Gemini 4 não capturados.
- Não encontrei fonte quantificando o ganho de sumarizar respostas HTTP ou de cachear o artefato de entendimento da API.

---

## 4. Rodar em toda release: acha coisas novas ou as mesmas? Variância e deriva de cobertura

### Takeaway
A evidência disponível indica variância alta entre execuções idênticas de agentes de pentest (25–85% de sucesso no mesmo cenário), de modo que uma execução única por release não é um teste de regressão confiável; achados confirmados devem virar testes determinísticos.

### Cited Findings
- Survey de 2026 sobre pentest com LLM relata estudo simulado de 400 execuções: o mesmo cenário repetido 100 vezes por agente gera taxas de sucesso de **25% a 85%** entre cinco agentes (atribuído a Erdem et al., ref. 57; não li o paper original) — [arXiv 2607.02605](https://arxiv.org/html/2607.02605v1)
- Comentário de praticante (ago/2026): alta variância pode esconder um achado numa passada e revelá-lo em outra; avaliação repetida dá quadro operacional mais fiel — [nhimg.org](https://nhimg.org/articles/frontier-llm-pentesting-still-depends-on-strategy-over-raw-power/)
- No benchmark Shannon, cada modelo foi rodado **uma única vez**; modelos diferentes acharam conjuntos diferentes (3/7, 3/7, 6/7 das vulnerabilidades corrigidas); os autores estimam que um ensemble Grok+DeepSeek cobriria 4/7 por US$ 41 (teórico) — [Shannon benchmark](https://github.com/KeygraphHQ/shannon/blob/main/docs/shannon-xbow-aikido-benchmark.md)
- CVE-Bench reporta médias de 5 repetições por configuração, prática que reconhece a variância — [arXiv 2503.17332](https://arxiv.org/html/2503.17332v3)
- Estudo de web agents: duas execuções do mesmo agente podem ter taxa agregada quase igual e discordar em fração relevante das tarefas individuais — [arXiv 2606.15017](https://arxiv.org/pdf/2606.15017)
- Aikido posiciona "Continuous Pentesting" como testes focados em mudanças, não repetição do teste completo a cada deploy — [help.aikido.dev](https://help.aikido.dev/pentests/pentest-pricing.md)

### Inferences
- Re-executar o agente na mesma versão tende a produzir a união de achados antigos (reencontrados com probabilidade <100%) e alguns novos por sorte de exploração. Logo: (1) um achado "sumir" numa execução **não** prova correção; (2) fechar achados automaticamente por ausência é perigoso para a parte agêntica (ver seção 5).
- Recomendações (minhas, coerentes com as fontes): converter cada achado confirmado em replay determinístico (requisição + asserção) que roda em toda release; manter base de conhecimento persistente por produto (mapa de endpoints, papéis, objetos, hipóteses já testadas); plano de teste semeado (checklist por endpoint × papel × classe de vulnerabilidade) que o agente deve cobrir, com registro de cobertura; variar deliberadamente o foco entre releases (rodízio) em vez de esperar que a aleatoriedade faça isso.

### Gaps
- Não encontrei estudo que meça sobreposição de achados entre execuções repetidas contra a mesma API real, nem "coverage drift" ao longo de releases.
- Paper original de Erdem et al. não localizado/lido.

---

## 5. Deduplicação e ciclo de vida de achados entre execuções/releases

### Takeaway
O padrão prático é dar a cada achado um identificador estável gerado pela própria ferramenta e deixar o DefectDojo gerenciar o ciclo de vida via reimport; para achados gerados por LLM, o identificador precisa ser construído a partir de campos estruturais (endpoint normalizado, método, parâmetro, classe, contexto de auth), nunca do título em texto livre.

### Cited Findings
- DefectDojo OSS tem quatro algoritmos por parser: `unique_id_from_tool`, `hash_code`, `unique_id_from_tool_or_hash_code`, `legacy` (fallback), configuráveis via `DD_DEDUPLICATION_ALGORITHM_PER_PARSER` — [docs.defectdojo.com dedup algorithms](https://docs.defectdojo.com/en/working_with_findings/finding_deduplication/deduplication_algorithms); [dedup tuning OSS](https://docs.defectdojo.com/triage_findings/finding_deduplication/os__deduplication_tuning/)
- No modo híbrido tenta-se primeiro o ID único da ferramenta (endpoints ignorados nesse caminho) e depois cai para hash code — [docs.defectdojo.com](https://docs.defectdojo.com/en/working_with_findings/finding_deduplication/deduplication_algorithms)
- Campos do hash configuráveis por scanner com `DD_HASHCODE_FIELDS_PER_SCANNER`, exemplo da doc: `{"ZAP Scan":["title","cwe","severity"]}`; `HASH_CODE_FIELDS_ALWAYS` = `["service"]` é sempre anexado (valor de `service` diferente impede dedup); se endpoints não entram no hash, `DEDUPE_ALGO_ENDPOINT_FIELDS` (default `["host","path"]`) define a comparação, e "only one endpoint pair must match"; mudança de configuração não é retroativa — rodar `python manage.py dedupe` — [dedup tuning OSS](https://docs.defectdojo.com/triage_findings/finding_deduplication/os__deduplication_tuning/)
- Reimport compara o scan novo com o Test existente; achados fechados que reaparecem são reabertos automaticamente; import simples sempre cria Test novo e nunca reativa — [docs.defectdojo.com reimport](https://docs.defectdojo.com/import_data/import_intro/reimport/)
- `close_old_findings` fecha achados ausentes do novo relatório (data do scan vira data de mitigação); `do_not_reactivate` mantém fechados os achados já fechados, criando só os novos — [docs.defectdojo.com reimport](https://docs.defectdojo.com/import_data/import_intro/reimport/); [API ReimportScan](https://defectdojo-api-generated.readthedocs.io/en/latest/apimodels/ReimportScanApi/)
- Armadilhas: upgrades do DefectDojo já mudaram o cálculo de `hash_code`/IDs de alguns parsers, exigindo recomputar (`./manage.py dedupe --parser <nome> --hash_code_only`) — [upgrade notes 3.2](https://docs.defectdojo.com/releases/os_upgrading/3.2/); PR #12249 relata status false positive/out of scope/risk accepted sendo descartados no reimport (não confirmei se o fix foi lançado) — [PR 12249](https://github.com/DefectDojo/django-DefectDojo/pull/12249)
- Para evitar fechar/recriar por atributos instáveis, a doc recomenda ajustar a dedup de reimport para identificadores estáveis como Unique ID From Tool — [avoid excess duplicates](https://docs.defectdojo.com/triage_findings/finding_deduplication/avoid_excess_duplicates/)
- SARIF/GitHub code scanning: o rastreamento de alertas usa `partialFingerprints.primaryLocationLineHash`; se ausente, a action `upload-sarif` tenta calcular a partir dos arquivos-fonte; upload pela API crua sem fingerprint pode gerar alertas duplicados — [docs.github.com SARIF support](https://docs.github.com/en/enterprise-server@3.15/code-security/reference/code-scanning/sarif-files/sarif-support-for-code-scanning)
- Shannon conta para gate apenas achados `status: exploited` — forma de separar hipótese de achado confirmado no ciclo de vida — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)

### Inferences
- GitHub code scanning é orientado a arquivo/linha; achado DAST não tem linha de código, então o fingerprint derivado de fonte não faz sentido — o produtor deve emitir seu próprio `partialFingerprints` estável (inferência minha; a fonte não trata DAST). Para esta equipe, DefectDojo é o destino mais natural que code scanning.
- Fingerprint recomendado (proposta minha): `sha256(produto | método | path-template normalizado (ex.: /pacientes/{id}) | parâmetro/campo afetado | classe (CWE ou categoria OWASP API Top 10) | contexto de auth (papel atacante → papel vítima))`. Excluir: título, descrição, payload exato, IDs concretos, host do ambiente, severidade. Enviar como `unique_id_from_tool` e configurar o parser para `unique_id_from_tool`.
- Como a parte agêntica é não-determinística (seção 4), **não usar `close_old_findings` nos imports do agente**; fechar achado só quando o replay determinístico correspondente passar. Para a parte determinística (ZAP), reimport com fechamento automático é adequado.
- Dedup semântica por LLM (comparar descrições) deve ser, no máximo, sugestão para humano: riscos são fusão de achados distintos no mesmo endpoint (ex.: BOLA em GET vs. em PUT), instabilidade entre execuções e custo; a chave estrutural deve ser a fonte de verdade (julgamento meu, sem fonte específica).
- Mudanças de path entre releases (rename de endpoint) quebram o fingerprint; o spec-diff (seção 6) pode alimentar um mapa de renomeações.

### Gaps
- Não capturei os campos default de hash para os parsers "ZAP Scan", "SARIF" e "Generic Findings Import" (a página de tuning não os lista).
- Dependency-Track: não pesquisado além de constar a integração com DefectDojo — [docs.dependencytrack.org](https://docs.dependencytrack.org/integrations/defectdojo/).
- Não li a seção de fingerprints da especificação SARIF 2.1.0 (OASIS) nesta sessão.
- Não encontrei avaliação publicada de dedup semântica por LLM em achados de segurança.

---

## 6. Modo incremental (diff de OpenAPI entre releases)

### Takeaway
oasdiff é a ferramenta open-source viva para diff de OpenAPI (Optic foi arquivado em jan/2026); usar o diff para **priorizar** é barato e alinhado ao que fornecedores fazem, mas testar só o diff deixa passar regressões de autorização em endpoints inalterados.

### Cited Findings
- oasdiff: open-source Apache 2.0, binário standalone, 300+ regras de breaking change; GitHub Action com subcomandos `breaking`, `changelog` e `diff` (ex.: `oasdiff/oasdiff-action/changelog@v0.0.43`) — [github.com/oasdiff/oasdiff](https://github.com/TuFin/oasdiff); [dev.to migration guide](https://dev.to/deepaksatyam/optic-is-dead-a-2026-migration-guide-for-openapi-breaking-changes-4go2)
- Optic: repositório arquivado em 2026-01-12, último release v1.0.9 (ago/2025), domínio useoptic.com fora do ar — [TERCEIRO, posts DEV Community] — [dev.to](https://dev.to/flarecanary/optic-is-dead-what-now-for-api-drift-detection-2kb8)
- openapi-diff (JVM) continua sendo opção se a dependência de JVM já for aceitável no pipeline — [apidog.com](https://apidog.com/blog/openapi-diff/)
- Fornecedores: Aikido Continuous Pentesting verifica cada deploy mas só lança agentes para mudanças relevantes de segurança — [help.aikido.dev](https://help.aikido.dev/pentests/pentest-pricing.md); Strix em PR limita o modo quick aos arquivos alterados — [GitHub usestrix/strix](https://github.com/usestrix/strix); StackHawk anuncia descoberta de endpoints novos/alterados/não documentados a cada commit e PR, mas não achei recurso documentado de "escanear só endpoints alterados" — [stackhawk.com/product/api-discovery](https://stackhawk.com/product/api-discovery)
- GitLab DAST compara resultados entre branch de origem e destino para determinar vulnerabilidades novas (diff de **resultados**, não de escopo) — [docs.gitlab.com DAST](https://docs.GitLab.com/ee/user/application_security/dast/)

### Inferences
- Riscos do diff-only (raciocínio meu): (1) mudança de código sem mudança de spec (ex.: refatoração de filtro de autorização no Spring Security) não aparece no diff; (2) regressão de autorização em endpoint inalterado causada por mudança transversal (novo papel, mudança de tenant); (3) spec desatualizado em relação ao código; (4) novo endpoint pode expor objetos de endpoints antigos (interações).
- Política sugerida: diff do spec define o **foco profundo** do agente (endpoints novos/alterados recebem a maior fatia do orçamento); endpoints inalterados são cobertos por replays determinísticos + matriz de autorização determinística (papel × endpoint) em toda release; varredura agêntica completa em cadência mais lenta (ex.: mensal ou em release maior). Para time Java/Spring, complementar com diff de código em controllers/configuração de segurança como gatilho.
- oasdiff por ser binário Go único é mais simples de embutir num CLI que openapi-diff (JVM), embora a equipe seja Java.

### Gaps
- Não confirmei se a saída `changelog` do oasdiff lista explicitamente endpoints **adicionados** (a busca não esclareceu; testar com dois specs).
- Escape e 42Crunch: nenhuma evidência encontrada sobre scan incremental/por PR.
- Nenhum estudo quantificando vulnerabilidades perdidas por teste diff-only.

---

## 7. Integração CI/CD para scans longos tipo DAST

### Takeaway
As fontes convergem em rodar DAST após deploy em ambiente de teste, fora do caminho crítico, com código de saída/gate controlado; para o agente, tempo de parede de horas e não-determinismo pedem execução assíncrona com teto de orçamento e gate só em achados confirmados.

### Cited Findings
- GitLab: o scan de API roda no stage `dast` por padrão, após deploy em ambiente de teste; mudanças concorrentes na API durante o scan (usuários, tarefas agendadas, outros pipelines) podem causar resultados imprecisos — [docs.gitlab.com API security testing](https://docs.gitlab.com/ee/user/application_security/api_security_testing/)
- ZAP Automation Framework: job `exitStatus` define o código de saída do ZAP a partir dos resultados (níveis warn/error), colocado tipicamente por último no plano — [zaproxy.org job-exitstatus](https://www.zaproxy.org/docs/desktop/addons/automation-framework/job-exitstatus/); AF suporta todos os mecanismos de autenticação do ZAP — [zaproxy.org automation framework](https://www.zaproxy.org/docs/automate/automation-framework/)
- Usuários relatam que a autenticação pode funcionar na GUI e falhar no plano YAML em CI; recomenda-se checar as estatísticas de autenticação para confirmar — [zaproxy-users](https://groups.google.com/g/zaproxy-users/c/p0BY1vr8Ohs)
- Strix: modo não-interativo sai com código não-zero quando há vulnerabilidades; exemplo em `pull_request` com modo quick — [GitHub usestrix/strix](https://github.com/usestrix/strix)
- Shannon: actions oficiais para GitHub/GitLab; gates de severidade contam só `status: exploited` — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)
- Duração observada de execução agêntica completa: 2h24 a 5h26 — [Shannon benchmark](https://github.com/KeygraphHQ/shannon/blob/main/docs/shannon-xbow-aikido-benchmark.md)
- StackHawk descreve subir a API e dependências em containers a cada PR e escanear — [stackhawk.com blog](https://www.stackhawk.com/blog/stackhawk-apis)

### Inferences
- Padrão sugerido (meu): (a) por PR/merge: nada agêntico ou só "quick" com teto de ~US$ 1 e 10–15 min, não-bloqueante; (b) por release candidate em ambiente de teste: camada determinística (ZAP API scan, replays, matriz de autorização) **bloqueante** apenas em replay de achado confirmado High/Critical que voltou a falhar; (c) agente em job assíncrono disparado pela release (ou noturno), time-box de 1–3 h e `--max-budget-usd`, resultado importado no DefectDojo e triado por humano; nunca bloquear release em achado de LLM não confirmado.
- Como o ambiente de teste é hospedado e compartilhado, serializar execuções por produto (lock) e avisar o time, dado o alerta do GitLab sobre mudanças concorrentes.
- Preflight barato antes de gastar tokens: validar login de cada conta/papel e saúde do ambiente; falha de auth é causa comum de scans vazios (conforme relatos na lista do ZAP).

### Gaps
- Não obtive doc do StackHawk sobre `failureThreshold` nem recomendações explícitas de GitLab/ZAP sobre "noturno vs. por release".
- Não verifiquei a action "ZAP Automation Framework Scan" do Marketplace.

---

## 8. Relatórios

### Takeaway
Os harnesses de referência convergem em SARIF 2.1.0 + JSON + Markdown/PDF, com distinção explícita entre achado explorado e hipótese; a concordância de severidade automática com reavaliação humana é baixa (50–72%), então severidade deve ser revisada na triagem.

### Cited Findings
- Shannon emite PDF, Markdown, JSON e SARIF 2.1.0 (SARIF por padrão em exploit mode); admite que relatórios de LLM podem conter detalhes fracos ou incorretos e exigem revisão humana — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)
- Severidade atribuída pelas ferramentas concordou com reavaliação manual CVSS 3.1 em 50–72% (Shannon por modelo), 66% (Aikido), 57% (XBOW) — [Shannon benchmark](https://github.com/KeygraphHQ/shannon/blob/main/docs/shannon-xbow-aikido-benchmark.md)
- Exemplo de falso positivo típico: funcionalidade admin-only legítima interpretada como exploit — [Shannon benchmark](https://github.com/KeygraphHQ/shannon/blob/main/docs/shannon-xbow-aikido-benchmark.md)
- Strix inclui base de conhecimento com pontuação CVSS e classificação OWASP — [GitHub usestrix/strix](https://github.com/usestrix/strix)
- DefectDojo mantém definições de status (active, verified, false positive, out of scope, risk accepted, mitigated) usadas no ciclo de triagem — [finding status definitions](https://docs.defectdojo.com/triage_findings/findings_workflows/finding_status_definitions/)

### Inferences
- Conteúdo mínimo por achado (recomendação minha): ID/fingerprint estável; produto, release/commit, ambiente; endpoint (método + path-template), parâmetro; contas/papéis usados (atacante/vítima) sem segredos; par requisição/resposta bruto e comando `curl` reproduzível com placeholders de token; resultado esperado vs. observado; impacto em termos de negócio (em healthtech: exposição de dado pessoal sensível de saúde — LGPD); classe (OWASP API Top 10 + CWE); severidade (CVSS ou OWASP Risk Rating) marcada como "proposta pelo agente" até triagem; remediação concreta para Spring; status de verificação (confirmado por replay determinístico / hipótese).
- Jira: criar ticket somente após triagem humana (status Verified no DefectDojo) e apenas acima de um limiar de severidade; um ticket por fingerprint; reaparecimento comenta/reabre o mesmo ticket em vez de criar outro. Isso pode ser feito via integração Jira do DefectDojo ou REST direto, guardando a chave do ticket junto ao fingerprint.

### Gaps
- Não pesquisei nesta sessão a doc da integração Jira do DefectDojo, o esquema "Generic Findings Import" (JSON) nem o formato JSON do ZAP — sem fonte para detalhes.
- Não encontrei estudo sobre o que desenvolvedores consideram relatório útil; as recomendações acima são prática comum sem citação.

---

## 9. Métricas de valor para a gestão

### Takeaway
A comparação mais defensável é custo por achado válido e frequência de cobertura contra pentest externo: referências públicas vão de ~US$ 4.000 por teste de AI pentest comercial e US$ 5.000–30.000 por pentest tradicional de web/API, contra dezenas de dólares de LLM por execução própria (mais o tempo do QA, que é o custo dominante).

### Cited Findings
- AI pentest comercial: US$ 4.000 por aplicação (Aikido Standard; XBOW citado no mesmo valor) — [help.aikido.dev](https://help.aikido.dev/pentests/pentest-pricing.md); [Shannon benchmark](https://github.com/KeygraphHQ/shannon/blob/main/docs/shannon-xbow-aikido-benchmark.md)
- Custo por achado válido derivável do benchmark (uma execução, um alvo): Shannon/Opus 5 US$ 115 / 23 TP ≈ US$ 5 por TP; Shannon/DeepSeek US$ 6,10 / 18 TP ≈ US$ 0,34; Aikido US$ 4.000 / 32 ≈ US$ 125; XBOW US$ 4.000 / 7 ≈ US$ 571 (divisões minhas sobre números do fornecedor; exclui custo humano de triagem) — [Shannon benchmark](https://github.com/KeygraphHQ/shannon/blob/main/docs/shannon-xbow-aikido-benchmark.md)
- Precisão observada no mesmo benchmark: 23/24 (Opus 5), 18/18, 10/10 — [Shannon benchmark](https://github.com/KeygraphHQ/shannon/blob/main/docs/shannon-xbow-aikido-benchmark.md)
- Pentest tradicional (USD, guias internacionais): aplicação web US$ 5.000–30.000; API US$ 6.000–30.000; web+API+cloud para startup Series A/B US$ 15.000–35.000 — [startupdefense.io](https://www.startupdefense.io/pt-br/blog/quanto-custa-um-pentest); [deepstrike.io](https://deepstrike.io/blog/custo-do-teste-de-intrusao)
- Brasil (fonte fraca: site de precificação para freelancers, 2026): R$ 5.000–40.000 por projeto; app web simples até 10 endpoints R$ 5.000–12.000; aplicação + API + autenticação R$ 10.000–25.000 — [freelasemcrise.com.br](https://www.freelasemcrise.com.br/quanto-cobrar/pentest-teste-seguranca)
- Tempo até resultado: XBOW ~2 dias, Aikido <8 h, Shannon 2,4–5,4 h — [Shannon benchmark](https://github.com/KeygraphHQ/shannon/blob/main/docs/shannon-xbow-aikido-benchmark.md)

### Inferences
- Painel sugerido por produto e por release: achados válidos novos (após triagem); precisão = válidos / reportados; tempo médio de triagem por achado; custo de LLM por execução e por achado válido; cobertura = (endpoints × papéis exercitados) / (endpoints × papéis do spec); nº de replays de regressão ativos e quantos falharam; tempo entre introdução (release) e detecção; MTTR por severidade; achados que o pentest externo anual encontrou e o harness não (e vice-versa).
- O benchmark Shannon é white-box, de fornecedor e com n=1; usar apenas como ordem de grandeza, não como promessa de resultado para teste black-box de API.
- O custo real dominante para a equipe é o tempo do QA (construção, manutenção, triagem); o custo de tokens é secundário nas faixas estimadas (seção 3).
- Pentest externo continua necessário para compliance/independência; o argumento é frequência (toda release vs. anual) e detecção precoce, não substituição.

### Gaps
- Sem pesquisa de mercado brasileira confiável de preço de pentest (2026); a única fonte em R$ é fraca.
- Não pesquisei valores de bug bounty (médias por severidade em HackerOne/Bugcrowd/BugHunt) nesta sessão.
- Sem benchmark publicado de tempo de triagem por achado de agentes LLM.

---

## 10. Múltiplos produtos com auth diferente; contas e dados de teste

### Takeaway
As ferramentas de referência resolvem auth por alvo com arquivo de configuração declarativo (Shannon) ou plano YAML com contextos/usuários (ZAP AF); o Strix, pelo README, recebe credenciais em instrução livre — então a camada "config por produto + contas por papel" é justamente a cola que a equipe terá de construir.

### Cited Findings
- Shannon: arquivo de configuração por alvo com credenciais, fluxo de login, TOTP e autenticação por e-mail (`docs/configuration.md`) — [GitHub KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon)
- Strix: credenciais para teste autenticado passadas em `--instruction`; múltiplos alvos com `-t` repetido ou `--target-list`; múltiplas contas não descritas explicitamente — [GitHub usestrix/strix](https://github.com/usestrix/strix)
- ZAP Automation Framework: plano YAML com ambiente/contextos e bloco `users`; suporta todos os mecanismos de auth do ZAP; erros de nome de parâmetro em `users` geram "Unrecognised parameter" e add-ons desatualizados causam falhas em CI — [zaproxy.org AF environment](https://zaproxy.org/docs/desktop/addons/automation-framework/environment/); [zaproxy-users](https://groups.google.com/g/zaproxy-users/c/OY5m8oFjdHI)
- No benchmark, Shannon recebeu apenas a credencial de admin — ou seja, o teste publicado não exercitou matriz multi-papel — [Shannon benchmark](https://github.com/KeygraphHQ/shannon/blob/main/docs/shannon-xbow-aikido-benchmark.md)
- GitLab alerta que atividade concorrente no ambiente durante o scan degrada os resultados — relevante para dados de teste compartilhados — [docs.gitlab.com](https://docs.gitlab.com/ee/user/application_security/api_security_testing/)

### Inferences
- Padrão sugerido (meu): um diretório por produto com `target.yml` contendo: base URL do ambiente de teste, caminho/URL do OpenAPI, tipo de auth (OAuth2 password/client credentials, JWT via endpoint de login, API key, sessão), receita de obtenção de token, lista de contas por papel **e por tenant** (mínimo: 2 usuários do mesmo papel em tenants/organizações diferentes + 1 papel privilegiado + 1 não autenticado, para BOLA/BFLA), endpoints proibidos/destrutivos (denylist), orçamento e time-box, e referências a segredos (variáveis de CI/secret manager — nunca no arquivo). O mesmo arquivo gera o plano do ZAP AF e as instruções do agente.
- Contas e dados: provisionar contas por papel via script/seed idempotente antes da execução; cada execução usa um `run_id` e marca tudo que cria (prefixo em nomes, campo de observação) para limpeza; teardown por API ao final + job de limpeza periódico por tag/idade como rede de segurança; preferir reset de banco do ambiente de teste quando possível.
- Dados brasileiros sintéticos: gerar CPF/CNPJ com dígitos verificadores válidos (algoritmo módulo 11) para passar validações, nunca usar dados reais de pacientes (LGPD — dado sensível de saúde); atenção ao CNPJ alfanumérico vigente a partir de julho/2026 para novas inscrições (conhecimento geral meu, **não verificado com fonte nesta sessão**).

### Gaps
- Não verifiquei nesta sessão: formato exato do `stackhawk.yml` (auth/usuários), arquivo de configuração do Schemathesis, conteúdo de `docs/configuration.md` do Shannon, nem bibliotecas específicas de geração de CPF/CNPJ (ex.: Faker pt_BR) — sem fonte.
- Não encontrei guia publicado de gestão de contas/dados de teste específico para DAST agêntico.

---

## Resumo de confiabilidade das fontes
- **Forte (primária, lida em 2026-11-12):** preços Anthropic, OpenAI (via developers.openai.com), Gemini; READMEs de Strix e Shannon; preços Aikido pentest; preços StackHawk; docs DefectDojo (tuning de dedup).
- **Média (fornecedor, interessada):** benchmark Shannon vs Aikido/XBOW (n=1 por modelo, white-box, alvo único, comparadores citados de estudo Doyensec que não li diretamente).
- **Fraca (agregadores/blogs/concorrentes):** preços de XBOW, Escape, Pynt, Akto, 42Crunch; custos por scan do Strix; flags de CLI do Strix; status do Optic; preços de pentest no Brasil.
- **Sem fonte / não pesquisado:** CAI, OpenAI Agents SDK, LangGraph, servidores MCP para ZAP/Burp/nuclei, integração Jira do DefectDojo, spec SARIF (OASIS), stackhawk.yml, Schemathesis, bug bounty, esforço real de construção.
