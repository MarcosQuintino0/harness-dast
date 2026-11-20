# Ferramentas clássicas (não-IA) de teste de segurança de API guiadas por OpenAPI/Swagger e como fazer benchmark

Notas de pesquisa. Data de referência: 2026-11-12. Convenções usadas em cada item:
- **[FATO]** = verificado na fonte primária citada (doc oficial, repositório, paper).
- **[FORNECEDOR]** = afirmação de quem vende o produto ou um concorrente; não verificada de forma independente.
- **[SECUNDÁRIO]** = blog/agregador/terceiro; tratar como indício.
- Datas entre parênteses são a data do documento-fonte, quando conhecida. Quando a página não mostra data, digo "sem data".
- Tudo o que está em "Inferências" é raciocínio meu, não está em fonte.

---

## 1. OWASP ZAP para APIs: o que o import OpenAPI + active scan realmente testa, automação, autenticação, scripts, controle de acesso, limites e novidades 2025–2026

### Takeaway
O ZAP importa o OpenAPI, gera UMA requisição por operação com valores default e roda sobre essas URLs as mesmas regras de injeção/misconfig que usa em sites HTML; ele não encadeia recursos (criar -> usar id) e não tem noção de dono do objeto. Autorização só é testada pelo add-on Access Control, que exige que o testador declare manualmente, por usuário e por nó de URL, o que é Allowed/Denied — ou seja, nível de função/URL (BFLA-like), não nível de objeto (BOLA). Em 2026 o ZAP ganhou um add-on MCP (alpha) e import OpenAPI opcional via LLM, mas nenhum recurso novo determinístico de BOLA.

### Cited Findings

**Import OpenAPI e valores gerados**
- [FATO] O add-on suporta definições OpenAPI/Swagger "versions 1.2, 2.0, 3.0, and 3.1"; import por menu, API (`importFile`, `importUrl`), linha de comando (`-openapifile`, `-openapiurl`, `-openapitargeturl`) e job `openapi` do Automation Framework. — [ZAP OpenAPI Support](https://www.zaproxy.org/docs/desktop/addons/openapi-support/) (sem data; consultado 2026-11)
- [FATO] A doc afirma literalmente: "Default values are used when importing OpenAPI definitions." Os defaults podem ser sobrescritos pelo add-on Form Handler (valores por nome de campo); o exemplo de valor estruturado da própria doc é `{ "id": 0, "name": "Freda" }`. — [ZAP OpenAPI Support](https://www.zaproxy.org/docs/desktop/addons/openapi-support/)
- [FATO] Limitações declaradas na doc: "Generation of XML content is currently not supported."; endpoints excluídos pelo Context não são importados; "data driven nodes" para parâmetros de path só são gerados se um Context for informado ("If no context is specified, no data driven nodes are generated."). A doc não menciona tratamento de dependência entre operações. — [ZAP OpenAPI Support](https://www.zaproxy.org/docs/desktop/addons/openapi-support/)
- [FATO] O add-on inclui uma regra ativa de script "Swagger Secret & Vulnerability Detector" (alert 100043) que procura documentação OpenAPI exposta com segredos e versões vulneráveis do Swagger UI. A v50 do add-on (jan/2026) a introduziu e a v51 a desabilitou por default por um memory leak do engine JS (Issue 9230). — [ZAP OpenAPI Support](https://www.zaproxy.org/docs/desktop/addons/openapi-support/); [ZAP 2025 Highlights and 2026 Plans, 2026-02-02](https://www.zaproxy.org/blog/2026-02-02-zap-updates-2025-highlights-2026-plans/)
- [FATO] A FAQ oficial diz que, uma vez conhecidas as URLs, o ZAP escaneia a API "in the same way as it scans HTML based web sites" e que "The problem is usually how to effectively explore the APIs." Formas recomendadas: add-on OpenAPI, GraphQL, SOAP, import de lista de URLs, import de servidor MCP, ou fazer proxy dos testes de regressão de API existentes através do ZAP. — [ZAP FAQ: How can you use ZAP to scan APIs?](https://www.zaproxy.org/faq/how-can-you-use-zap-to-scan-apis/) (sem data)

**zap-api-scan.py (scan empacotado em Docker)**
- [FATO] O script importa a definição (`-f openapi|soap|graphql`) e roda um Active Scan "tuned for performing scans against APIs", que "doesn't bother looking for things like XSSs"; adiciona dois scripts que alertam para códigos de erro HTTP de servidor e para content-types não usuais em API. Opções: `-O` (override de host), `-z` (opções ZAP), `-c/-u` (config de regras INFO/IGNORE/FAIL), `--hook` (hooks Python), `-U` usuário + `-n` context file para scan autenticado, `-S` safe mode. Exit codes 0/1/2/3. — [ZAP Docker API Scan](https://www.zaproxy.org/docs/docker/api-scan/) (sem data)
- [SECUNDÁRIO] Cabeçalho de autenticação estático via variáveis de ambiente `ZAP_AUTH_HEADER_VALUE` (valor), `ZAP_AUTH_HEADER` (nome do header) e `ZAP_AUTH_HEADER_SITE` (restringe a sites); exemplo `docker run -e ZAP_AUTH_HEADER_VALUE="Bearer ${TOKEN}" ... zap-api-scan.py -t swagger.yaml -f openapi`. — [QBurst, 2024-11](https://www.qburst.com/blog/2024/11/leveraging-owasp-zap-to-automate-authenticated-scans/). A página oficial do api-scan não menciona essas variáveis (ver Gaps).
- [SECUNDÁRIO] Relatos de usuários no grupo oficial: token Bearer via `ZAP_AUTH_HEADER_VALUE`/options.prop "ignorado", e scan de API "passando" mesmo sem autenticação configurada (isto é, scan não autenticado pode parecer limpo). Alternativa usada: regra do Replacer via `-z "-config replacer.full_list(0)..."`. — [zaproxy-users: bearer token ignored](https://groups.google.com/g/zaproxy-users/c/F_V-mHsG-5g); [zaproxy-users: Authorization headers not picked up](https://groups.google.com/g/zaproxy-users/c/ZqzDR43tu2Y)

**Automation Framework e autenticação**
- [FATO] O Automation Framework (planos YAML) tem job `openapi` e, segundo a doc, suporta todos os mecanismos de autenticação suportados pelo ZAP. — [ZAP Automation Framework](https://www.zaproxy.org/docs/automate/automation-framework/); [OpenAPI Automation Framework Support](https://www.zaproxy.org/docs/desktop/addons/openapi-support/automation/)
- [FATO] Avanços de 2025 em autenticação: Browser Based Authentication preenche formulários automaticamente, lida com login multi-tela, passos manuais e campos TOTP; novo método "Client Script Authentication" com "client-side Zest scripts" gravados/reproduzidos no browser; auto-detecção de session tokens, de URL de verificação e "logout avoidance"; Authentication Report com screenshots e tráfego. ZAP 2.17.0 saiu no fim de 2025 (de-duplicação de alertas, menos persistência em CI). — [ZAP 2025 Highlights and 2026 Plans, 2026-02-02](https://www.zaproxy.org/blog/2026-02-02-zap-updates-2025-highlights-2026-plans/)
- [FATO] Existe job de Automation Framework para o add-on Sequence Scanner (sequências de requisições gravadas). — [Sequence Scanner Automation Framework Support](https://www.zaproxy.org/docs/desktop/addons/sequence-scanner/automation/)

**Add-on Access Control Testing**
- [FATO] Funcionamento: o testador define usuários no Context e como cada um autentica; define no painel Authorization como reconhecer resposta não autorizada; explora o app (manual ou Spider); define Access Rules por usuário e por nó do site com valores Allowed / Denied / Unknown (regras herdadas do nó pai: "only 1 rule needs to be set explicitly for an entire subtree"). O ZAP então acessa cada URL como cada usuário e compara com as regras. Alertas: 10101 "Improper Authentication" e 10102 "Improper Authorization". — [ZAP Access Control Testing](https://www.zaproxy.org/docs/desktop/addons/access-control-testing/) (sem data)
- [FATO] Automação: ação de API `scan` (context ID + user IDs, opção de incluir usuário não autenticado), `writeHTMLreport`, views `getScanProgress`/`getScanStatus`; as regras precisam existir previamente (Context exportado/importado). Não roda em Safe mode. — [ZAP Access Control Testing](https://www.zaproxy.org/docs/desktop/addons/access-control-testing/)
- [FORNECEDOR] No benchmark da Escape contra o VAmPI, o plugin de access control do ZAP foi removido porque "was breaking the scan results". — [Escape DAST benchmark, 2025-12-01](https://escape.tech/blog/dast-tools-benchmark/)
- [FATO, paper brasileiro] SBSeg 2026 (UFPE), "DAST-AI: Reducing False Positives in API Security Testing via LLM-based Semantic Analysis" (de Melo e Campelo): usa como referência um baseline autenticado que simula o Access Control Scanner do ZAP em Juice Shop (68 endpoints) e VAmPI (12 endpoints); conclui que "credentials alone do not resolve the problem" e que distinguir endpoint legitimamente público de endpoint vulnerável "requires semantic context". F1 extraído do PDF: DAST-AI 0.680 (Juice Shop) / 0.923 (VAmPI); ZAP Access Control autenticado 0.628 / 0.857; baseline sintático 0.49 / 0.857. — [SBSeg 2026 PDF](https://sol.sbc.org.br/index.php/sbseg/article/download/44304/44067/). **CONFLITO**: um snippet de busca do mesmo paper citava "F1 0.80 com oráculo vs 0.28 para a referência autenticada que simula o ZAP"; e o próprio texto extraído diz que o resultado autenticado do ZAP é "identical to the unauthenticated baseline", o que não bate com 0.628 vs 0.49. Conferir os números no PDF original antes de citar.

**Novidades 2025–2026 (Checkmarx, IA, MCP)**
- [FATO] 2025 foi "the first full year in which we had 3 people working on ZAP thanks to Checkmarx". — [ZAP 2025 Highlights, 2026-02-02](https://www.zaproxy.org/blog/2026-02-02-zap-updates-2025-highlights-2026-plans/)
- [FATO] OpenAPI add-on v49 (jan/2026): "optional LLM extension for importing OpenAPI definitions" e suporte inicial a OpenAPI 3.1. A integração de IA no ZAP será "optional and opt-in". — [ZAP 2025 Highlights, 2026-02-02](https://www.zaproxy.org/blog/2026-02-02-zap-updates-2025-highlights-2026-plans/)
- [FATO] Add-on oficial "MCP Integration" anunciado em 2026-04-02, declarado "definitely an alpha release!": servidor HTTP MCP dentro do ZAP; 14 tools (`zap_version`, `zap_info`, `zap_create_context`, start/stop/status de spider, AJAX spider e active scan, `zap_get_passive_scan_status`, `zap_generate_report`), resources somente leitura (alerts, history, contexts, sites tree) e prompts `zap_baseline_scan`/`zap_full_scan`. Security key obrigatória por default; "Secure Only" ligado. **Não suporta autenticação no alvo** (planejado). — [ZAP MCP Server, 2026-04-02](https://www.zaproxy.org/blog/2026-04-02-zap-mcp-server/); [MCP Integration docs](https://www.zaproxy.org/docs/desktop/addons/mcp-integration/)
- [FATO] Em maio/2026 o ZAP passou a importar endpoints de um servidor MCP para escaneá-los como uma API. — [Scanning MCP servers with ZAP, 2026-05-21](https://www.zaproxy.org/blog/2026-05-21-scanning-mcp-servers-with-zap/)
- [FATO] Planos 2026: melhorar Client Spider, "guided scans" que gravam fluxos de negócio, integração OWASP PTK (DAST/IAST/SAST/SCA no browser). — [ZAP 2025 Highlights, 2026-02-02](https://www.zaproxy.org/blog/2026-02-02-zap-updates-2025-highlights-2026-plans/)

**Resultados medidos do ZAP em APIs vulneráveis (todos de fornecedores concorrentes)**
- [FORNECEDOR] Escape vs ZAP no VAmPI (2025-12-01): ZAP detectou só SQL Injection entre 8 categorias listadas (não detectou Mass Assignment, Rate Limiting, User/Password Enumeration, Excessive Data Exposure, Unauthorized Password Change, BOLA); ZAP enviou 3546 requisições em 4 min com "coverage" 1,90% (Escape 860 requisições, 76%). O post não mede falsos positivos. — [Escape DAST benchmark](https://escape.tech/blog/dast-tools-benchmark/)
- [FORNECEDOR] ForAllSecure (2022): no scan do VAmPI com zap-api-scan, grande parte da saída eram respostas 404 e 401. — [Mayhem for API vs ZAP](https://forallsecure.com/blog/mapi-vs-zap-the-difference)
- [FORNECEDOR] Equixly (2024-10-03): engines DAST baseados em ZAP "failed to identify any high-severity logic vulnerability" em uma API vulnerável não nomeada; "Traditional DAST engine active scanning is limited in scope and cannot detect logic vulnerabilities". Tabela de resultados é imagem; sem números por classe. — [Equixly](https://equixly.com/blog/2024/10/02/dast-api-security-testing-compare-zap)

### Inferências
- "Importar Swagger no ZAP + active scan" equivale a: 1 requisição sintática por operação com valores default + payloads de injeção em cada parâmetro. Sem Form Handler/valores reais, a maioria das operações que exigem ids existentes, enums de negócio ou campos com formato (CPF, CNS, datas) tende a parar em 400/404 na validação de entrada, e o scanner fica fuzzando a camada de validação, não a lógica.
- O add-on Access Control cobre a pergunta "o usuário X consegue alcançar a URL Y que deveria ser negada?" (BFLA/autenticação). Para virar BOLA, as URLs gravadas precisam conter ids de objetos de um usuário conhecido e a regra precisa dizer "Denied" para o outro usuário — isso é conhecimento de propriedade fornecido pelo humano, por URL concreta. O ZAP não infere dono.
- "Scripts bem escritos" (Zest/Graal JS/hooks Python) conseguem fechar parte da lacuna (login, encadear create->read, replay com segundo token), mas aí o conhecimento de negócio está no script escrito por você, não na ferramenta. Esse é o baseline honesto contra o qual o agente LLM deve ser comparado: custo de escrever/manter esses scripts vs. custo/ruído do agente.
- O MCP do ZAP em nov/2026 é um controle remoto de spider/active scan sem autenticação de alvo; não muda a capacidade de detecção.

### Gaps
- Não encontrei página oficial zaproxy.org que documente `ZAP_AUTH_HEADER*` nesta rodada (creio que exista em docs de autenticação, mas não verifiquei); a fonte citada é secundária.
- Não verifiquei em fonte primária a data/termos da ida do ZAP para a Checkmarx (lembro de set/2024, não confirmado aqui) nem o status do projeto em relação à OWASP.
- Não encontrei doc oficial listando explicitamente "ZAP não detecta BOLA". As evidências são: (a) a doc do Access Control descreve regras manuais por URL; (b) papers/fornecedores. Sem benchmark independente e revisado por pares de ZAP contra crAPI.
- Detalhes de scripting (tipos de script: authentication, session management, httpsender, active/passive rules; engines Zest, Graal.js, Python/Jython) não foram verificados nas docs nesta rodada.
- Não confirmei a lista exata de valores default gerados por tipo (string/int/data) pelo add-on OpenAPI; a doc só diz "Default values are used".

---

## 2. Schemathesis: property-based testing a partir do OpenAPI, stateful, checks, auth, avaliação acadêmica, limites

### Takeaway
Schemathesis é o baseline open-source mais forte para "500s + violações de contrato" e, na documentação atual (stable, consultada em 2026-11), já traz dois checks de segurança determinísticos: `ignored_auth` e `object_level_authorization` (BOLA de leitura, com >= 2 usuários "peers"). O check de BOLA só cobre GETs de objetos que a ferramenta conseguiu ligar a um dono; um resultado limpo não prova ausência de BOLA.

### Cited Findings
- [FATO] 15 checks embutidos: `not_a_server_error`, `status_code_conformance`, `content_type_conformance`, `response_schema_conformance`, `response_headers_conformance`, `negative_data_rejection` (modo negative/all), `positive_data_acceptance`, `missing_required_header`, `unsupported_method`, `use_after_free` (stateful), `ensure_resource_availability` (stateful), `ignored_auth`, `object_level_authorization`, `allow_header_conformance`, `max_response_time` (desligado por default). — [Schemathesis checks reference](https://schemathesis.readthedocs.io/en/stable/reference/checks/) (sem data; consultado 2026-11)
- [FATO] `ignored_auth`: detecta operações que aceitam requisições sem credenciais ou com credenciais inválidas; envia requisições extras por operação. — [Schemathesis checks reference](https://schemathesis.readthedocs.io/en/stable/reference/checks/)
- [FATO] `object_level_authorization` (BOLA): configuração = documento Web Fuzzing Commons (WFC) com >= 2 usuários (`fixedHeaders` ou `loginEndpointAuth`) + `[auth.wfc]` em `schemathesis.toml` com `peers` ("At least two users whose objects must stay private to each other"). Algoritmo: (1) propriedade — objeto é do usuário se ele o criou (create devolveu id) ou se aparece na listagem dele e não na do outro peer; (2) quando um peer lê objeto próprio com GET, a requisição é repetida como cada outro peer; **nunca repete escritas**; (3) falha = outro peer recebe 2xx com o mesmo objeto (mesmo id e mesmos valores nos campos comuns), reportado como ST402 / WFC fault 906. Antes de reportar, descarta objetos públicos (requisição sem auth devolve o mesmo corpo), valores diferentes/mascarados, ou objeto visível em listagem permitida ao outro peer. — [Schemathesis: Testing Object-Level Authorization](https://schemathesis.readthedocs.io/en/stable/guides/object-level-authorization/)
- [FATO] Limitações declaradas do check de BOLA: sem `peers` não roda; pula operações públicas (`security: []`), creates que falham, creates que não devolvem id em API sem operação de listagem, respostas sem campos declarados no schema; "a clean run covers only objects Schemathesis could link to a user" (se não ligar nenhum, não reporta nada); recursos compartilhados por design e não expostos em listagem (ex.: recursos de time) podem gerar falso positivo. — [Schemathesis: Testing Object-Level Authorization](https://schemathesis.readthedocs.io/en/stable/guides/object-level-authorization/)
- [FATO] Autenticação: `--header`, `--auth user:pass`, headers em `schemathesis.toml` com `${VAR}`; `[auth.openapi.<Scheme>]`; auth dinâmica declarativa `[auth.dynamic.openapi.<Scheme>]` (POST em endpoint de login, extrai token por JSON Pointer/header/cookie, refaz a cada 300 s); WFC multiusuário; classes Python `@schemathesis.auth()` com `refresh_interval`; **auto sign-up** (se o schema tem operação de cadastro e login que devolve token, cria conta e loga sozinho). Com WFC sem `user` fixo, escolhe identidade por operação e, em 401/403, tenta sem credenciais e depois os outros usuários. — [Schemathesis auth guide](https://schemathesis.readthedocs.io/en/stable/guides/auth/)
- [FATO] Stateful: encadeia chamadas usando OpenAPI links; os links vêm de (a) inferência automática a partir de schemas de resposta e parâmetros de path, (b) links explícitos no spec, (c) headers `Location` aprendidos em fases anteriores. Sem links, a fase stateful é pulada. Implementado sobre state machines do Hypothesis. — [Schemathesis stateful testing](https://schemathesis.readthedocs.io/en/stable/guides/stateful-testing/); [explicação](https://schemathesis.readthedocs.io/en/stable/explanations/stateful/)
- [FATO, autores da ferramenta] "Deriving Semantics-Aware Fuzzers from Web API Schemas" (Hatfield-Dodds e Dygalo, arXiv 2021-12-20): comparado com 8 fuzzers em 16 serviços open-source, Schemathesis achou de 1,4x a 4,5x mais defeitos únicos que o segundo colocado em cada alvo, foi o único a achar defeitos em 4 alvos e o único a tratar mais de dois terços dos alvos sem erro interno fatal. — [arXiv:2112.10328](https://arxiv.org/abs/2112.10328)
- [FATO, estudos independentes] Cobertura de linha média black-box (1 h): 43,01% e 14,2 erros 500 únicos em Kim et al. (ISSTA 2022, 20 serviços); 54,5% em Zhang & Arcuri (19 APIs), segundo lugar atrás do EvoMaster black-box (56,8%). — [Kim et al., arXiv:2204.08348](https://ar5iv.labs.arxiv.org/html/2204.08348); [Zhang & Arcuri, arXiv:2205.05325](https://ar5iv.labs.arxiv.org/html/2205.05325)

### Inferências
- Para um QA Java/Spring, Schemathesis é o baseline mais barato de montar: `schemathesis run` + arquivo WFC com 2 usuários já dá 500s, violações de schema, `ignored_auth` e BOLA de leitura. O que ele NÃO cobre por desenho: BOLA em escritas (PUT/PATCH/DELETE no objeto alheio), BFLA por papel, mass assignment (campos privilegiados não declarados) e fluxos de negócio.
- A qualidade do stateful depende do spec: specs gerados por springdoc sem `links` dependem da inferência automática.

### Gaps
- Não descobri em qual versão o check `object_level_authorization` e o suporte WFC entraram, nem a versão atual do Schemathesis em nov/2026 (a doc "stable" não mostra).
- Não encontrei resultados publicados do Schemathesis (com o check de BOLA) contra crAPI/VAmPI.
- Preços/funcionalidades da oferta comercial (schemathesis.io) não pesquisados.

---

## 3. RESTler (Microsoft): fuzzing stateful, dependências producer-consumer, checkers de segurança, manutenção, limites

### Takeaway
RESTler é o fuzzer stateful clássico: compila o OpenAPI numa gramática, infere dependências producer-consumer e roda checkers de lógica (use-after-free, hierarquia de recursos, namespace entre usuários). O checker tipo-BOLA (NamespaceRule) vem desligado por default e exige credenciais de um "attacker". Manutenção em 2025–2026 é mínima (commits de dependências; último commit visto em 2026-02-13).

### Cited Findings
- [FATO] Modos, em ordem: **compile** (gera gramática a partir do OpenAPI JSON/YAML), **test** (smoketest: executa cada endpoint+método uma vez para depurar setup e medir cobertura do spec), **fuzz-lean** (uma vez por endpoint com checkers default), **fuzz** (busca em largura; o README avisa que é agressivo e pode causar indisponibilidade). Todo 500 é bug; bugs são agrupados em buckets com replay log. — [microsoft/restler-fuzzer README](https://github.com/microsoft/restler-fuzzer)
- [FATO] Checkers (doc oficial): **UseAfterFree** (após DELETE bem-sucedido, tenta usar o recurso; 20x = bug); **NamespaceRule** ("off by default"; após sequência válida, repete o acesso ao recurso consumido como um usuário "attacker" não autorizado; settings `trigger_on_dynamic_objects`, `trigger_objects`); **ResourceHierarchy** (recurso filho acessível sob outro pai); **LeakageRule** (após create que falhou com 4xx, tenta acessar o recurso que não deveria existir); **InvalidDynamicObject** (troca ids válidos por inválidos); **PayloadBody** (fuzz de corpo; defaults do paper FSE 2020); **Examples** (envia cada exemplo do spec); **InvalidValues** (experimental). Checkers ficam ligados em modo fuzz e desligados em modo test, salvo configuração. A doc avisa que os checkers experimentais "are a work in progress, and may go through significant changes or be removed in the future." — [RESTler Checkers.md](https://github.com/microsoft/restler-fuzzer/blob/main/docs/user-guide/Checkers.md)
- [FATO] Crítica acadêmica ao NamespaceRule: a regra de namespace de usuário do RESTler "might be too restrictive", pois alguns usuários podem legitimamente acessar recursos de outros. — [Sahin, Zhang, Arcuri, arXiv:2604.00702, 2026-04-01](https://arxiv.org/html/2604.00702v1)
- [FATO] Manutenção: últimos commits em `main` — 2026-02-13 (bump de dependência sqlmodel), 2025-10-13 ("Improve HTTP transport stability & logging", bump dotnet-sdk, "Remove away notice"), 2025-08-21, 2025-04-10 ("Update README with away notice"), 2025-03-10. Repositório não arquivado; ~3,0k stars, 282 issues abertas, 428 commits. README ainda diz "still under active development". — [restler-fuzzer commits](https://github.com/microsoft/restler-fuzzer/commits/main/); [README](https://github.com/microsoft/restler-fuzzer)
- [FATO] Desempenho em estudos independentes: cobertura de linha média 35,44% e 15,1 erros 500 únicos (Kim et al., ISSTA 2022); 34,6% (Zhang & Arcuri, penúltimo de 7). Zhang & Arcuri observaram RESTler gerando URLs com `//`, rejeitadas com 404 por três APIs. — [Kim et al.](https://ar5iv.labs.arxiv.org/html/2204.08348); [Zhang & Arcuri](https://ar5iv.labs.arxiv.org/html/2205.05325)

### Inferências
- RESTler em nov/2026 está em modo de manutenção de fato (um commit de dependência em 9 meses, um "away notice" durante 2025). Serve como referência conceitual (producer-consumer, checkers), mas é arriscado como pilar de um baseline novo.
- NamespaceRule é o mesmo padrão determinístico "replay com token de outro usuário"; como RESTler sabe quem criou o recurso (ele próprio criou na sequência), resolve a questão de propriedade para recursos criados no fuzzing — mas não para dados pré-existentes nem para compartilhamento legítimo.

### Gaps
- A doc de checkers não explica como fornecer as credenciais do atacante (fica em settings de autenticação; não verificado).
- Não identifiquei a versão/data do último release (a página de releases veio vazia na extração).
- Sem resultados publicados de RESTler contra crAPI/VAmPI encontrados.

---

## 4. EvoMaster, CATS, Dredd, Tcases e outros fuzzers open-source; estudos acadêmicos comparativos (cobertura e causas de falha)

### Takeaway
Dois estudos independentes de 2022 convergem: fuzzers black-box guiados por OpenAPI ficam, em média, entre ~32% e ~57% de cobertura de linha em 1 hora, e a maior parte das falhas achadas está na primeira camada de validação de entrada. As causas de parada são sempre as mesmas: geração de valores válidos, dependências entre operações/estado de banco, spec incompleto/errado e autenticação não trivial. Em 2026, a linha EvoMaster adicionou oráculos automáticos de política de acesso, mas em 8 APIs vulneráveis-por-design eles acharam só 5 tipos de falha, e nenhum dos oráculos de "autorização esquecida".

### Cited Findings

**Kim, Xin, Sinha, Orso — "Automated Test Generation for REST APIs: No Time to Rest Yet" (ISSTA 2022)** — 10 ferramentas, 20 serviços, 1 h por execução. Tabela 3 (linha % / branch % / método % / erros 500 únicos):
- EvoMasterWB 52,76 / 36,08 / 52,86 / 33,3
- EvoMasterBB 45,41 / 28,21 / 47,17 / 16,4
- Schemathesis 43,01 / 25,29 / 43,65 / 14,2
- RestTestGen 40,86 / 21,15 / 42,31 / 7,7
- bBOXRT 40,23 / 22,20 / 42,48 / 9,5
- Tcases 37,16 / 16,29 / 41,47 / 18,5
- Dredd 36,04 / 13,80 / 40,59 / 6,9
- RESTler 35,44 / 12,52 / 40,03 / 15,1
- RESTest 33,86 / 18,26 / 33,99 / 7,2
- APIFuzzer 32,19 / 18,63 / 33,77 / 6,9
— [arXiv:2204.08348 (ar5iv)](https://ar5iv.labs.arxiv.org/html/2204.08348)
- [FATO] Causas apontadas: "The tools generate many invalid requests that are rejected by the services" (valores de domínio/formato); dependências entre operações — "Existing tools either do not account for such dependencies or use a simple heuristic approach, which can lead to many false positives and false negatives"; e "if the specification does not match the API implementation, the tools can produce incomplete, invalid, or even no requests at all." — [arXiv:2204.08348](https://ar5iv.labs.arxiv.org/html/2204.08348)

**Zhang & Arcuri — "Open Problems in Fuzzing RESTful APIs: A Comparison of Tools" (arXiv v2 2022-07-07; autores são do EvoMaster, viés declarado)** — 7 fuzzers, 19 APIs (13 JVM incl. 1 industrial + 6 NodeJS), 1 h x 10 repetições. Cobertura de linha média black-box:
- EvoMaster BB 56,8%; Schemathesis 54,5%; RestTestGen 45,4%; bBOXRT 41,9%; RestCT 35,4%; RESTler 34,6%; RESTest 33,6%. EvoMaster white-box 52,9% vs grey-box 45,4% (subconjunto JVM).
- "RQ1: all compared tools achieve at least 30% line coverage on average, but none goes above 60%."
- "many faults can be easily found this way with a fuzzer at the very first layer of input validation in the SUT's code".
- Problemas abertos listados: **autenticação** (token estático é fácil; login por formulário com cookies foi difícil para a maioria; endpoints de admin ficaram sem cobertura); **schemas com erros** faziam a maioria dos fuzzers abortar antes de enviar qualquer requisição; **payloads não-JSON** (form-encoded só o EvoMaster suportava); **estado de banco/dependências** (caminhos que exigem dados criados por POST anterior ou por scripts externos); **restrições de string** (token com padrão UUID de 36 chars; regex em anotações fora do schema); **schemas subespecificados** — "Dealing with underdefined schemas is a major issue with fuzzers, especially black-box ones."; **serviços externos** — "Calling external services is a problem for fuzzers."; aleatoriedade (execução única não é confiável).
— [arXiv:2205.05325 (ar5iv)](https://ar5iv.labs.arxiv.org/html/2205.05325)

**Outros estudos**
- [FATO] Estudo de 2024 em aplicação de IoT de saúde (regressão em DevOps): RESTest ~82% de cobertura (da API), EvoMaster/Schemathesis/RESTler/RestTestGen ~84%; EvoMaster gerou o maior número de falhas. (Números são cobertura de API, não de código; não comparar com os acima.) — [arXiv:2410.12547](https://arxiv.org/html/2410.12547v2)
- [FATO] Survey: "Testing RESTful APIs: A Survey" (Golmohammadi, Zhang, Arcuri, dez/2022) revisa 92 artigos. — [arXiv:2212.14604](https://arxiv.deeppaper.ai/papers/2212.14604v1)

**EvoMaster (estado 2025–2026)**
- [FATO] Tool report publicado em Automated Software Engineering vol. 32(1), junho/2025, descrevendo a versão 3.0.0; black-box e white-box (JVM) para REST, GraphQL e RPC. — [Tool report](https://research.buaa.edu.cn/en/publications/tool-report-evomasterblack-and-white-box-search-based-fuzzing-for/); [repositório](https://github.com/WebFuzzing/EvoMaster)
- [FATO] "Enhancing REST API Fuzzing with Access Policy Violation Checks and Injection Attacks" (Sahin, Zhang, Arcuri; arXiv 2026-04-01), implementado como extensão do EvoMaster. Afirma: "many fuzzers in the literature are unable to handle authentication information during the fuzzing process" e, dos poucos que tratam múltiplos usuários, "they are unable to automatically detect BOLA and BFLA related vulnerabilities". Requisitos: schema OpenAPI + "authentication information for at least two different users" (idealmente um por papel); sem especificação formal de política — regras inferidas de respostas 401/403. Oráculos: Not Recognized Authentication (205), Existence Leakage (204: 403 vs 404 revela existência), Missed Authorization Checks (206: dois de PUT/PATCH/DELETE dão 403 e o terceiro passa), Anonymous Modifications (901), Ignore Anonymous (900), Leaked Stack Traces (902), Hidden Accessible (903: endpoint fora do schema responde), mais SQLi (por tempo) e XSS. — [arXiv:2604.00702](https://arxiv.org/html/2604.00702v1)
- [FATO] Resultado em 8 APIs vulneráveis-por-design, black-box, 1 h x 10 repetições: *capital* (21 endpoints), *crapi* (44), *damn-vulnerable-rest* (21), *dvapi* (16), *dvws-node* (31), *vampi* (14), *vulnerable-rest-api* (19), *webgoat* (201). Somas médias por oráculo: F100 (HTTP 500) 56,5; F902 stack trace 28,7; F903 hidden accessible 21,0; F201 XSS 17,5; F205 6,2; F204 1,3. "In these experiments, tens of security faults were found, but only of five different kinds." **Nenhuma falha para F200, F206 (Missed Authorization), F900, F901.** Os autores admitem: "we cannot exclude the presence of some false-positives". Esta seção não compara com outras ferramentas. — [arXiv:2604.00702](https://arxiv.org/html/2604.00702v1) (somas por API calculadas pelo extrator: crapi 9,0; vampi 8,0; dvws-node 8,0 — conferir na Tabela 3 original)
- [FATO] O mesmo paper cita que o modo black-box do EvoMaster ficou em segundo lugar na competição de fuzzers black-box SBFT'26. Há também um paper ISSRE 2025 "Fuzzing for detecting access policy violations in REST APIs" (BOLA/BFLA). — [arXiv:2604.00702](https://arxiv.org/html/2604.00702v1); [ISSRE 2025](https://research.buaa.edu.cn/en/publications/fuzzing-for-detecting-access-policy-violations-in-rest-apis/)

**CATS, Dredd, Tcases**
- [FATO] Dredd e Tcases aparecem na tabela de Kim et al. acima (36,04% e 37,16% de linha). CATS é listado no README do EvoMaster entre os fuzzers REST open-source black-box existentes. — [arXiv:2204.08348](https://ar5iv.labs.arxiv.org/html/2204.08348); [EvoMaster README](https://github.com/WebFuzzing/EvoMaster)

### Inferências
- O dado mais importante para a decisão: mesmo a pesquisa de ponta em oráculos determinísticos de autorização (2026) não detectou as vulnerabilidades de autorização plantadas (BOLA/BFLA "de desafio") em crAPI/VAmPI — o que encontrou foram 500s, stack traces, endpoints ocultos e XSS. É evidência acadêmica (de quem tem interesse em mostrar que funciona) de que o teto do black-box determinístico genérico fica abaixo do BOLA de negócio.
- As causas de falha dos fuzzers (valores válidos de domínio, dependências, spec incompleto, login não trivial) são exatamente os pontos onde um agente LLM promete ajudar; são também os pontos onde um QA pode ajudar a ferramenta clássica com dicionários, exemplos no spec e scripts de seed. Um benchmark justo dá ao baseline clássico esse mesmo apoio.
- White-box EvoMaster (JVM) é relevante para um time Spring: foi o melhor nos dois estudos (52,76% / 52,9%), mas exige escrever um driver e instrumentar a aplicação.

### Gaps
- CATS: não pesquisado em fonte primária (número de fuzzers, manutenção, resultados). Dredd: status de manutenção não verificado (lembro que foi arquivado, não confirmado). Tcases: idem.
- Estudos ARAT (ARAT-RL, etc.): só vi de passagem que ARAT-RL reporta ganhos relativos sobre RESTler (119%/60%/52% mais branches/linhas/métodos — snippet de busca, não verificado na fonte).
- Não li as seções de RQ1/RQ3 nem comparações com outras ferramentas do arXiv:2604.00702.

---

## 5. DAST comercial guiado por spec: quem diz detectar BOLA/BFLA/mass assignment/lógica e como; preços

### Takeaway
Todos os fornecedores que dizem detectar BOLA/BFLA de forma não-agêntica usam o mesmo mecanismo: >= 2 identidades de teste configuradas (e, para BFLA, marcação de qual é privilegiada) + replay cruzado + heurística de comparação de resposta. O Burp Suite (Scanner/DAST) declara explicitamente que não tem checks dedicados de BOLA. Preço público é raro e as fontes de terceiros se contradizem.

### Cited Findings

**Burp Suite DAST / Burp Scanner (PortSwigger)**
- [FATO] A FAQ oficial diz que o Burp "doesn't include dedicated checks for API-specific issue classes such as broken object-level authorization"; ele roda "its standard web vulnerability checks against the discovered endpoints" e recomenda teste manual para cobertura do OWASP API Top 10. — [PortSwigger API scanning FAQ](https://portswigger.net/burp/documentation/scanner/api-scanning-faq) (sem data; consultado 2026-11)
- [FATO] Formatos: OpenAPI 3.0/3.1 (3.2 "Provisional"), Swagger 2.0, Postman v2.1.0, WSDL 1.1/1.2, GraphQL por introspecção. Auth: Basic, Bearer, API key (fixos ou dinâmicos via endpoint de token), OAuth2 Client Credentials só no Burp Suite DAST; Authorization Code não automatizável (workaround: refresh token). Valores: usa exemplos do spec; "If a parameter has no example, Burp generates one." Limites: não resolve `$ref` externos; YAML > 3 MB rejeitado; corpos só `application/json` e `x-www-form-urlencoded`; recursão de schema limitada a 4 níveis; não executa scripts Postman; sem SSE/streaming. A FAQ não fala em encadear endpoints. — [PortSwigger API scanning FAQ](https://portswigger.net/burp/documentation/scanner/api-scanning-faq)
- [SECUNDÁRIO] Texto de 2021 avaliou que o Burp ia bem em endpoints independentes e mal em APIs logicamente dependentes (delete só funciona após create). — [Medium: How good is Burp's API Scanning?](https://medium.com/burpsuite-guide/how-good-is-burps-api-scanning-558eaea8bddf)
- [SECUNDÁRIO] Burp Suite Professional ~US$ 499/usuário/ano; Burp Suite DAST é cotado por vendas (fontes de terceiros divergem: ~US$ 5.000/ano vs a partir de ~US$ 30.000/ano). — [AppSec Santa pricing guide](https://appsecsanta.com/application-security/appsec-pricing-guide) (não confirmado na página do fornecedor)

**StackHawk (HawkScan, construído sobre ZAP)**
- [FATO, doc do fornecedor] "Business Logic Testing" em três níveis: (1) plugins desligados por default: 422002 (multi-user tenancy check), 421004 (possible BOPLA), 422003 (possible BFLA); o HawkScan 6.6.0 removeu as regras 40051/40054/40055/40056 que sinalizavam autorização com identidade única; (2) multi-perfil: exige OpenAPI em `app.openApiConf`, várias contas em `authentication.profiles` (`name`, `userNamePassword`/`external`/`authScript`), admin marcado com `isPrivileged: true`, `globalParameters` (ex.: `tenantId`); testa BOLA (perfil B lê recurso descoberto pelo perfil A) e BFLA (POST/PUT/DELETE cruzados; não-privilegiado alcança função privilegiada), plugins 422004/422005; evidência prefixada por `[profile=...]`; (3) scripts customizados em JavaScript no HawkScan Testing Engine (HSTE). A doc avisa que o teste multi-perfil precisa de dados pertencentes a cada usuário de teste e recomenda rodar só em staging/teste. A doc não explica o critério exato de pass/fail e não menciona LLM. — [StackHawk Business Logic Testing docs](https://docs.stackhawk.com/hawkscan/business-logic-testing/)
- [FORNECEDOR] BLT lançado em dez/2025; "Smart Crawl" analisa o OpenAPI e gera sequências de teste; opção `fakerEnabled: true` (default false) no `openApiConf` para dados de teste. — [Help Net Security, 2025-12-16](https://www.helpnetsecurity.com/2025/12/16/stackhawk-business-logic-testing/); [StackHawk blog](https://www.stackhawk.com/blog/announcing-deeper-api-security-test-coverage)
- [SECUNDÁRIO, conflitante] Preço: uma fonte cita Pro a US$ 42/contribuidor/mês; duas páginas de 2026 citam um tier a US$ 10/usuário/mês e plano Scale sob consulta. Não confirmado na página de preços do fornecedor. — [AppSec Santa pricing guide](https://appsecsanta.com/application-security/appsec-pricing-guide); [Beagle Security](https://beaglesecurity.com/blog/article/top-stackhawk-alternatives-2026.html)
- [FORNECEDOR concorrente] No DVGA (GraphQL), StackHawk detectou 2 de 17 categorias listadas (OS Command Injection, SQLi) com 8743 requisições em 18 min; ZAP 0; Escape 12. — [Escape benchmark, 2025-12-01](https://escape.tech/blog/dast-tools-benchmark/)

**42Crunch (Audit estático do OpenAPI + Conformance/API Scan)**
- [FATO, release notes do fornecedor] Release de 2025-04-02: é possível adicionar testes de BOLA ou BFLA na configuração de scan direto pela UI; Scan v2 tem "scan playbooks" (compilam os cenários de scan) e edição de requests/cenários por diálogos em vez de JSON. — [42Crunch release 2025-04-02](https://docs.42crunch.com/latest/content/whatsnew/2025/42crunch-platform-2025-04-02.htm)
- [FATO] Licenciamento: combinação de número de APIs e número de desenvolvedores; preço customizado via marketplace Azure/contato comercial. — [Microsoft Learn: 42Crunch onboarding](https://learn.microsoft.com/en-gb/azure/defender-for-cloud/onboarding-guide-42crunch)
- [SECUNDÁRIO] G2 lista tier freemium e plano single-user a partir de US$ 15/mês — não confirmado no site do fornecedor. — [G2](https://www.g2.com/products/42crunch/reviews)

**Akto**
- [FATO, doc do fornecedor] Testes em templates YAML; "test roles" guardam tokens de atacante (fixos ou obtidos automaticamente antes de cada execução); o template "BOLA by changing auth token" faz replay da requisição original com o token do atacante; biblioteca inclui IDOR por query param, BOLA em versões antigas da API, BOLA por HTTP parameter pollution. — [Akto: BOLA by changing auth token](https://www.akto.io/test/bola-by-changing-auth-token); [Akto test role](https://docs.akto.io/api-security-testing/concepts/test-role); [Akto contexts](https://docs.akto.io/test-editor/concepts/test-yaml-syntax-detailed/contexts)

**Pynt**
- [FORNECEDOR] Roda sobre tráfego funcional (coleção Postman via `pynt newman`), executando a coleção duas vezes com dois environments para simular dois usuários. Diz cobrir 15 de 16 desafios do crAPI listados (BOLA 2/2, mass assignment 3/3, SSRF, NoSQLi, SQLi, JWT, etc.); **não cobre o desafio 7 (BFLA)**. "Coberto" = fraqueza sinalizada, não exploit completo; usou coleção modificada com APIs ausentes da oficial e uma coleção de "alinhamento" para popular dados. Sem taxa de falsos positivos, sem data. — [Pynt vs OWASP crAPI](https://docs.pynt.io/documentation/api-security-testing/benchmarks/pynt-vs-owasp-crapi); ver também [Pynt vs VAmPI](https://docs.pynt.io/documentation/api-security-testing/benchmarks/pynt-vs-vampi)

**Escape (partes não-agênticas)**
- [FORNECEDOR] No VAmPI, a própria Escape diz que BOLA e Unauthorized Password Change "need custom config" (não saem na configuração padrão); detectou 5 de 8 categorias sem customização. A doc de IDOR diz que a análise mais profunda exige ao menos dois usuários configurados. Preço: free tier + assinaturas, sem valores públicos encontrados. — [Escape benchmark](https://escape.tech/blog/dast-tools-benchmark/); [Escape BOLA docs](https://docs.escape.tech/documentation/dast/vulnerabilities/bola/)

**Outros**
- [FATO, doc do fornecedor] Wallarm (schema-based testing): BOLA e BFLA não podem ser provados com uma única identidade; o teste precisa de dois usuários autenticados, de preferência com privilégios diferentes. — [Wallarm docs](https://docs.wallarm.com/vulnerability-detection/schema-based-testing/setup/)

### Inferências
- O "estado da arte determinístico" comercial para BOLA/BFLA é: matriz de identidades + replay cruzado + diff. É replicável com Schemathesis (`peers`), Akto OSS, Autorize ou script próprio. O valor agregado pago está em orquestração, geração de sequências e triagem — não num oráculo fundamentalmente diferente.
- Os números de fornecedores vêm quase sempre sem falsos positivos e com setup favorável (coleção Postman enriquecida, dados pré-populados). Não usar como ground truth.

### Gaps
- **Não pesquisados nesta rodada**: Salt Security, Traceable/Harness, APIsec (há docs de BOLA em dev-docs-apisecapps.apisec.ai/docs/bola/ não lidas), Bright/NeuraLegion, Invicti. Nenhuma afirmação sobre eles deve ser feita a partir destas notas.
- Página do 42Crunch sobre BOLA/BOPLA/BFLA retornou 404; o mecanismo detalhado (credenciais de dois usuários, cenários, extensões `x-42c-*`) não foi verificado.
- Preços oficiais de StackHawk, Akto, Pynt, Escape, Burp Suite DAST: não confirmados em páginas dos fornecedores.
- StackHawk "OpenAPI custom variables"/dados de teste customizados: só confirmei `fakerEnabled` e `globalParameters`.

---

## 6. Testes de autorização com múltiplas contas: Autorize, AuthMatrix, Auth Analyzer, ZAP access-control; como funciona o "replay com token de outro usuário e diff"

### Takeaway
O método determinístico é simples e antigo: capturar tráfego legítimo de um usuário (com ids de objetos dele), reenviar cada requisição com as credenciais de outro usuário (e sem credenciais) e classificar a resposta. O que a ferramenta não sabe sozinha é (1) quem deveria ter acesso (propriedade/papel) e (2) como é uma resposta de "negado" nesta API — ambos têm de ser configurados pelo humano.

### Cited Findings
- [FATO] **Autorize** (extensão Burp, Python/Jython): configura-se o Cookie ou header Authorization de um usuário de baixo privilégio ("Headers defined here will be replaced if already present or added if missing"); navega-se como usuário de alto privilégio; a extensão repete cada requisição com as credenciais de baixo privilégio e, opcionalmente, sem autenticação. Classificação: "Bypassed!" (não aplicou autorização), "Enforced!", "Is enforced??? (configuration required)" (não conseguiu decidir; exige fingerprint manual). Enforcement detectors: match de corpo (string/regex), headers, content-length, resposta completa — separados para baixo privilégio e não autenticado. Filtros de interceptação (escopo, whitelist/blacklist, regex). Suporta vários usuários de baixo privilégio simultâneos. O README admite que depende de "response comparison heuristics and fingerprints", logo há falsos positivos/negativos. ~1,2k stars, 393 commits. — [Quitten/Autorize](https://github.com/Quitten/Autorize)
- [SECUNDÁRIO] **AuthMatrix** (extensão Burp): baseado em papéis; o testador marca, para cada requisição, quais papéis são autorizados e envia os cookies de cada usuário; tem "chains" para capturar tokens CSRF e reutilizá-los em requisições seguintes. — [Cyber Advisors, 2024-09-19](https://blog.cyberadvisors.com/technical-blog/blog/authorization-testing-authmatrix-part-1)
- [FATO] **ZAP Access Control**: mesma ideia com regras Allowed/Denied/Unknown por usuário e nó de URL (ver seção 1). — [ZAP Access Control Testing](https://www.zaproxy.org/docs/desktop/addons/access-control-testing/)
- [FATO] **Schemathesis `object_level_authorization`**: automatiza a parte de propriedade para objetos que ele mesmo criou/listou e descarta casos públicos com uma requisição não autenticada de controle (ver seção 2). — [Schemathesis BOLA guide](https://schemathesis.readthedocs.io/en/stable/guides/object-level-authorization/)
- [FATO] **RESTler NamespaceRule**, **Akto** ("replace auth header with attacker token"), **StackHawk** multi-perfil e **Pynt** (coleção rodada duas vezes) usam o mesmo padrão (ver seções 3 e 5). — [RESTler Checkers.md](https://github.com/microsoft/restler-fuzzer/blob/main/docs/user-guide/Checkers.md); [Akto](https://www.akto.io/test/bola-by-changing-auth-token); [StackHawk](https://docs.stackhawk.com/hawkscan/business-logic-testing/); [Pynt](https://docs.pynt.io/documentation/api-security-testing/benchmarks/pynt-vs-owasp-crapi)
- [FATO] Limite conceitual apontado pela academia: regras de namespace podem ser restritivas demais porque alguns usuários acessam legitimamente recursos de outros; e, sem contexto semântico, não se distingue endpoint público de endpoint vulnerável. — [arXiv:2604.00702](https://arxiv.org/html/2604.00702v1); [SBSeg 2026](https://sol.sbc.org.br/index.php/sbseg/article/download/44304/44067/)

### Inferências
- Configuração mínima para o replay determinístico funcionar: (a) >= 2 contas de teste do mesmo papel (BOLA horizontal) e >= 1 de papel inferior (BFLA/vertical); (b) dados pertencentes a cada conta (ids conhecidos ou criados no setup); (c) tráfego legítimo de cada conta cobrindo os endpoints (coleção Postman, testes REST Assured existentes via proxy, ou sequência gerada do spec); (d) definição de "negado" (401/403/404, ou fingerprint de corpo); (e) lista de exceções de compartilhamento legítimo (recursos públicos, de equipe, de médico<->paciente). Os itens (b), (d), (e) são conhecimento de negócio.
- Fontes típicas de erro: API que devolve 200 com corpo vazio/erro; 404 no lugar de 403; objetos compartilhados por design; escritas (PUT/DELETE) que têm efeito colateral e destroem o dado de teste; ids não previsíveis que o segundo usuário nunca veria. É aqui que um LLM pode agregar (interpretar a resposta, inferir relação de posse) — ou só adicionar custo, se o time já tem suíte REST Assured com 2 usuários.
- Para um time Java/Spring, o equivalente "sem ferramenta" é um teste parametrizado REST Assured: para cada endpoint com `{id}`, criar como usuário A e chamar como usuário B esperando 403/404. Esse é o baseline mais honesto de todos.

### Gaps
- Auth Analyzer (extensão Burp): não verificado em fonte primária; só menção superficial de que suporta formatos de token customizados.
- Status de manutenção/data do último commit de Autorize e AuthMatrix não obtidos.

---

## 7. Quais categorias do OWASP API Security Top 10 (2023) os scanners clássicos cobrem bem e quais cobrem mal

### Takeaway
Fontes primárias de fabricantes de scanner admitem a lacuna: a PortSwigger diz que o Burp não tem checks dedicados de BOLA e recomenda teste manual; a pesquisa ligada ao EvoMaster diz que fuzzers não detectam BOLA/BFLA automaticamente. As afirmações explícitas "cobre bem injeção/misconfig, cobre mal API1/API3/API5/API6" vêm sobretudo de fornecedores de alternativas (viés).

### Cited Findings
- [FATO] PortSwigger: o Burp "doesn't include dedicated checks for API-specific issue classes such as broken object-level authorization" e recomenda teste manual para o OWASP API Top 10. — [PortSwigger API scanning FAQ](https://portswigger.net/burp/documentation/scanner/api-scanning-faq)
- [FATO] Sahin/Zhang/Arcuri (2026): os poucos fuzzers que tratam múltiplos usuários "are unable to automatically detect BOLA and BFLA related vulnerabilities". — [arXiv:2604.00702](https://arxiv.org/html/2604.00702v1)
- [FATO] SBSeg 2026: detecção de BOLA exige contexto; "credentials alone do not resolve the problem". — [SBSeg 2026](https://sol.sbc.org.br/index.php/sbseg/article/download/44304/44067/)
- [FORNECEDOR] Stingrai (2026-07-01): "Automated API scanners and DAST tools reliably find injection, misconfiguration, and known-class bugs."; perdem API1 BOLA ("a scanner cannot know who owns an object"), API5 BFLA ("The scanner cannot tell which role should reach which route, so it never tries the request as the wrong role"), API3 mass assignment ("A scanner does not know which fields are privileged, so it does not know to inject them"); "The absence of BOLA findings in a scanner report is not evidence that BOLA is absent." Sem estatísticas independentes. — [Stingrai](https://www.stingrai.io/blog/api-scanners-miss-bola-idor-authorization-testing)
- [FORNECEDOR] Equixly (2024): engines DAST tradicionais "don't test for the OWASP Top 10 API Security Risks" e "fail to understand API workflows and business logic". — [Equixly](https://equixly.com/blog/2024/10/02/dast-api-security-testing-compare-zap)
- [SECUNDÁRIO] Três das cinco primeiras categorias do Top 10 de 2023 se relacionam a abuso de lógica de negócio (duas em 2019); API6 (Unrestricted Access to Sensitive Business Flows) é o fluxo funcionando como projetado, mas automatizado. — [DevOps Digest](https://www.devopsdigest.com/updated-owasp-top-10-for-api-security-underscores-the-challenge-of-mitigating-business-logic-attacks)
- [FATO] Evidência positiva do que o determinístico cobre: Schemathesis tem checks para auth ignorada, BOLA de leitura, 500s, validação negativa; EvoMaster 2026 tem oráculos para modificação anônima, stack trace vazado, endpoint oculto, SQLi por tempo e XSS; zap-api-scan cobre injeções e erros de servidor. — [Schemathesis checks](https://schemathesis.readthedocs.io/en/stable/reference/checks/); [arXiv:2604.00702](https://arxiv.org/html/2604.00702v1); [ZAP API scan](https://www.zaproxy.org/docs/docker/api-scan/)

### Inferências (mapa por categoria; síntese minha a partir das fontes acima)
| Categoria 2023 | Cobertura clássica | Por quê |
|---|---|---|
| API1 BOLA | Fraca por default; média com 2 usuários + replay (Schemathesis `peers`, Autorize, StackHawk, Akto) | Exige identidades, dados de cada dono e noção de "negado"; leitura é mais fácil que escrita |
| API2 Broken Authentication | Parcial | JWT fraco/alg none, auth ignorada, endpoint sem auth são checáveis; lógica de reset de senha/OTP (crAPI desafio 3) não |
| API3 BOPLA (mass assignment / excessive data exposure) | Fraca | Precisa saber quais campos são privilegiados/sensíveis; só heurísticas (StackHawk 421004 "possible BOPLA") |
| API4 Unrestricted Resource Consumption | Parcial | Ausência de rate limit é testável de forma grosseira; custo de negócio não |
| API5 BFLA | Fraca por default; média com matriz de papéis (`isPrivileged`, AuthMatrix, ZAP Access Control) | Exige declarar quem pode o quê |
| API6 Sensitive Business Flows | Praticamente nula | Fluxo "funciona como projetado" |
| API7 SSRF | Razoável | Payloads + callback out-of-band |
| API8 Security Misconfiguration | Boa | Headers, CORS, stack traces, verbos, TLS, swagger exposto |
| API9 Improper Inventory | Parcial | Endpoints ocultos/versões antigas via descoberta de conteúdo (ffuf), oráculo "Hidden Accessible" |
| API10 Unsafe Consumption of APIs | Fraca | Depende de terceiros/integrações |
| Injeção (SQLi/NoSQLi/command; fora do Top 10 API 2023 como item próprio) | Boa | Assinaturas e payloads; ZAP achou SQLi no VAmPI |

### Gaps
- Não consultei o texto oficial do OWASP API Security Top 10 2023 (owasp.org/API-Security) para citar a "Detectability" de cada item; a tabela acima é inferência.
- Não achei estudo independente e quantitativo (recall por categoria OWASP API) para scanners clássicos.

---

## 8. Alvos de benchmark: crAPI, VAmPI, Juice Shop, DVWS-node, vAPI, Damn Vulnerable RESTaurant, DVGA, Generic University — vulnerabilidades, spec OpenAPI, resultados publicados e como montar o scorecard

### Takeaway
crAPI (18 desafios documentados + 2 secretos) e VAmPI (9 vulnerabilidades, com chave vulnerável/seguro) são os alvos mais usados e os únicos para os quais achei resultados publicados de ferramentas; quase todos esses resultados são de fornecedores, sem falsos positivos e sem protocolo comum. Não encontrei benchmark independente que rode ZAP, Schemathesis, RESTler e um agente LLM no mesmo alvo com a mesma configuração de autenticação.

### Cited Findings

**OWASP crAPI**
- [FATO] Desafios documentados (docs/challenges.md, branch develop): **BOLA** — (1) acessar detalhes do veículo de outro usuário (id é GUID; é preciso achar onde ids vazam), (2) acessar relatórios de mecânico de outros usuários (endpoint oculto); **Broken User Authentication** — (3) resetar a senha de outro usuário (brute force de OTP/endpoints similares); **Excessive Data Exposure** — (4) vazar dados sensíveis de outros usuários, (5) vazar propriedade interna de vídeo; **Rate Limiting** — (6) DoS de camada 7 via "contact mechanic"; **BFLA** — (7) deletar vídeo de outro usuário via endpoint de admin; **Mass Assignment** — (8) obter item de graça (endpoint shadow que edita pedido), (9) aumentar saldo em US$ 1.000+, (10) alterar propriedades internas de vídeo; **SSRF** — (11) fazer o crAPI chamar www.google.com e devolver a resposta; **NoSQL Injection** — (12) cupons grátis; **SQL Injection** — (13) resgatar cupom já usado; **Unauthenticated Access** — (14) endpoint sem checagem de autenticação; **JWT** — (15) forjar JWT válido; **LLM** — (16) prompt injection no chatbot, (17) extrair credenciais de outro usuário, (18) agir em nome de outro usuário; mais 2 desafios secretos. — [crAPI challenges.md](https://raw.githubusercontent.com/OWASP/crAPI/develop/docs/challenges.md)
- [FATO] No paper EvoMaster 2026 o crapi tinha 44 endpoints no schema usado. — [arXiv:2604.00702](https://arxiv.org/html/2604.00702v1)
- [FORNECEDOR] Pynt: 15 de 16 desafios "cobertos" (falha em BFLA); ver seção 5. — [Pynt vs crAPI](https://docs.pynt.io/documentation/api-security-testing/benchmarks/pynt-vs-owasp-crapi)
- [FORNECEDOR, só snippet] Komodo Research diz que seu agente AigentX achou 24 vulnerabilidades reais no crAPI, verificadas depois por revisão de código. — [Komodo](https://www.komodosec.com/post/we-pentested-a-complex-api-application-with-aigentx-ai-agent-then-verified-the-results-with-source) (não li a página completa)
- [FATO] EvoMaster + oráculos (black-box, 1 h x 10): no conjunto de 8 APIs incluindo crapi, só 5 tipos de falha (500, XSS, existence leakage, not-recognized-auth, stack trace, hidden endpoint), nenhum "missed authorization". — [arXiv:2604.00702](https://arxiv.org/html/2604.00702v1)

**VAmPI**
- [FATO] Vulnerabilidades (README): SQLi Injection; Unauthorized Password Change; Broken Object Level Authorization; Mass Assignment; Excessive Data Exposure through debug endpoint; User and Password Enumeration; RegexDOS; Lack of Resources & Rate Limiting; JWT authentication bypass via weak signing key. Flask; spec OpenAPI em `openapi_specs/`; chave vulnerável/seguro (`vuln` em app.py; Docker `-e vulnerable=0`); validade do token `tokentimetolive` (default 60 s no Dockerfile). ~1,4k stars. — [erev0s/VAmPI](https://github.com/erev0s/VAmPI)
- [FORNECEDOR] Escape vs ZAP (2025-12-01): ZAP 1/8 categorias (SQLi); Escape 5/8 + 2 "com config customizada" (BOLA e Unauthorized Password Change); ver seção 1. — [Escape benchmark](https://escape.tech/blog/dast-tools-benchmark/)
- [FATO] SBSeg 2026 usou VAmPI (12 endpoints) e Juice Shop (68 endpoints) com F1 por método (ver seção 1, com ressalva de conflito de números). — [SBSeg 2026](https://sol.sbc.org.br/index.php/sbseg/article/download/44304/44067/)

**Damn Vulnerable RESTaurant**
- [FATO] Python FastAPI + PostgreSQL + Docker; Swagger em `http://localhost:8091/docs` e Redoc em `/redoc`; vulnerabilidades alinhadas ao OWASP API Top 10 (README não lista uma a uma); ~947 stars. — [theowni/Damn-Vulnerable-RESTaurant-API-Game](https://github.com/theowni/Damn-Vulnerable-RESTaurant-API-Game)

**DVGA (GraphQL)**
- [FORNECEDOR] 17 categorias listadas no benchmark Escape (OS Command Injection, SQLi, SSRF, batch/alias/recursion DoS, introspection, JWT forgery, stored XSS etc.) + 5 não detectadas por ninguém; Escape 12, StackHawk 2, ZAP 0. — [Escape benchmark](https://escape.tech/blog/dast-tools-benchmark/)

**DVWS-node, vAPI, Generic University, Juice Shop, outros**
- [SECUNDÁRIO] DVWS-node: inclui, entre outros, Client Side Template Injection, GraphQL Arbitrary File Write, GraphQL Batching Brute Force (lista parcial); solução no wiki do projeto. 31 endpoints no schema usado pelo paper EvoMaster. — [OWASP VWAD: dvws-node](https://vwad.owasp.org/app/dvws-node/); [arXiv:2604.00702](https://arxiv.org/html/2604.00702v1)
- [SECUNDÁRIO] vAPI ("Vulnerable Adversely Programmed Interface"): app PHP self-hosted com exercícios do OWASP API Top 10. — [PortSwigger Daily Swig](https://portswigger.net/daily-swig/introducing-vapi-an-open-source-lab-environment-to-learn-about-api-security)
- [SECUNDÁRIO] Generic University: API vulnerável em Laravel simulando portal de notas. — [Wallarm lab](https://lab.wallarm.com/how-can-deliberately-flawed-apis-help-in-mastering-api-security)
- [FATO] Outros alvos usados pela academia em 2026: *capital* (21 endpoints), *damn-vulnerable-rest* (21), *dvapi* (16), *vulnerable-rest-api* (19), *webgoat* (201). — [arXiv:2604.00702](https://arxiv.org/html/2604.00702v1)

**Metodologia de scorecard (o que as fontes sustentam)**
- [FATO] Ferramentas randomizadas variam entre execuções (diferenças de 8,3–9,1% para o EvoMaster); os autores usam 10 repetições de 1 h e dizem que execução única não é confiável. — [Zhang & Arcuri](https://ar5iv.labs.arxiv.org/html/2205.05325)
- [FATO] Mesmo oráculos automáticos de autorização precisam de revisão manual: "we cannot exclude the presence of some false-positives"; alguns achados "Hidden Accessible" eram artefato de framework. — [arXiv:2604.00702](https://arxiv.org/html/2604.00702v1)
- [FATO] VAmPI tem modo seguro (`vulnerable=0`), o que permite medir falsos positivos na mesma API. — [VAmPI](https://github.com/erev0s/VAmPI)
- [FATO] O benchmark de fornecedor mais citado (Escape) não reporta falsos positivos e removeu um plugin do concorrente; Pynt conta "coberto" quando a fraqueza é sinalizada, não quando o exploit é completo. — [Escape](https://escape.tech/blog/dast-tools-benchmark/); [Pynt](https://docs.pynt.io/documentation/api-security-testing/benchmarks/pynt-vs-owasp-crapi)
- [FATO] O próprio ZAP adotou o WAVSEP para benchmark do scanner em 2025 (web clássico, não API). — [ZAP 2025 Highlights](https://www.zaproxy.org/blog/2026-02-02-zap-updates-2025-highlights-2026-plans/)
- [FORNECEDOR] Existem benchmarks de fornecedores de agentes: Strobes (45 achados validados, zero FP, em Fider, jun/2026), YAGA (248 cenários incluindo BOLA/BFLA). Não verificados. — [Strobes](https://strobes.co/blog/ai-pentesting-business-logic-flaws/); [HackerSec YAGA](https://hackersec.com/blog/benchmark-yaga-vs-standalone-llms)
- [FATO] APIEval-20 (benchmark aberto de agentes que testam APIs) exclui explicitamente segurança (auth bypass, injeção, OWASP API Top 10) do escopo da v1. — [dev.to APIEval-20](https://dev.to/engroso/apieval-20-the-first-benchmark-that-tests-ai-agents-on-real-bug-detection-56oi)

### Inferências (proposta de scorecard; não vem de fonte única)
- Ground truth = lista de instâncias (endpoint + método + classe OWASP + pré-condição), não "desafios". Ex.: crAPI desafio 1 vira "GET /identity/api/v2/vehicle/{id}/location — BOLA — requer GUID de outro usuário vazado em /community/api/v2/community/posts". Derivar de challenges.md + writeups + código-fonte.
- Por ferramenta e por classe: TP, FP, FN -> precisão e recall; reportar separadamente (a) "sinalizou a fraqueza" e (b) "produziu evidência reproduzível" (requisição/resposta). Classificar cada FN por causa: não alcançou o endpoint (auth/dependência/valor inválido), alcançou mas sem oráculo, oráculo errou.
- Controles: mesma spec, mesmas N contas de teste e mesmos dados seed para todos; registrar esforço humano de configuração (horas) e custo (requisições, tempo, tokens/US$); >= 3–10 repetições para ferramentas randomizadas e agentes LLM; rodar também em versão "segura" (VAmPI `vulnerable=0`) para FP; incluir a própria API interna com bugs plantados, porque crAPI/VAmPI/Juice Shop estão quase certamente nos dados de treino dos LLMs (risco de contaminação — inferência minha, sem fonte).
- Linha de base em 4 degraus para isolar o valor do LLM: (0) ZAP api-scan sem ajuda; (1) ZAP/Schemathesis com auth + valores/exemplos; (2) + 2 usuários e replay (Schemathesis `peers` / Access Control / script); (3) agente LLM. A pergunta de decisão é o delta (3) - (2) por classe, dividido pelo custo.
- Expectativa a priori com base nas fontes: degrau 0–1 pega SQLi, 500s, stack traces, endpoint sem auth, JWT fraco (com regra específica); degrau 2 pega BOLA de leitura simples e parte de BFLA; ficam para humano/agente: crAPI 1 (precisa descobrir o vazamento de GUID), 2 e 7 (endpoint oculto/admin), 3 (lógica de OTP), 8–10 (mass assignment encadeado), 12–13 (injeção em campo de negócio de cupom, dependendo do valor inicial).

### Gaps
- Não confirmei o nome/caminho do arquivo OpenAPI do crAPI no repositório (sei que existe um spec em `openapi-spec/`, não verificado nesta rodada).
- Juice Shop: lista/categorias de desafios e existência de spec OpenAPI não pesquisadas (o paper SBSeg usou 68 endpoints).
- Listas completas de vulnerabilidades de DVWS-node, vAPI, Damn Vulnerable RESTaurant e Generic University não obtidas; se enviam spec OpenAPI (vAPI/Generic University/DVWS-node) não verificado.
- Nenhum resultado publicado encontrado de Schemathesis ou RESTler contra crAPI/VAmPI; nenhum estudo independente comparando agente LLM x ZAP x fuzzers no mesmo alvo.
- Não encontrei guia de praticantes descrevendo scorecard precisão/recall por classe para API; a proposta acima é inferência.

---

## 9. nuclei e ffuf: papel em teste de API e limites

### Takeaway
nuclei aceita OpenAPI/Swagger como entrada e gera requisições com placeholders por tipo, servindo para aplicar templates (CVEs conhecidos, misconfig, templates DAST de fuzzing) sobre os endpoints do spec; não tem estado, dependência entre recursos nem noção de usuário. ffuf não foi coberto por fonte nesta rodada.

### Cited Findings
- [FATO] nuclei: `nuclei -l openapi.yaml -im openapi`; `-im` aceita "list, burp, jsonl, yaml, openapi, swagger"; entradas tipo requisição HTTP "can only be specified via file using `-l` flag"; Postman precisa ser convertido para OpenAPI. Geração de requisições a partir de OpenAPI descrita a partir da v3.2.0. — [ProjectDiscovery: nuclei input formats](https://docs.projectdiscovery.io/opensource/nuclei/input-formats.md)
- [FATO] Valores: "If a parameter is of type `string` then it will use `string` as placeholder value" (análogo para outros tipos); `-ro` usa só campos obrigatórios; `-sfv` pula validação e descarta requisições com parâmetros faltando; parâmetros obrigatórios ausentes fazem o nuclei parar com erro e gerar `required_openapi_params.yaml` (uso temporário, a ser descontinuado em favor de arquivo `secret`). — [nuclei input formats](https://docs.projectdiscovery.io/opensource/nuclei/input-formats.md)
- [FATO] Auth: se o schema exige autenticação e nada é fornecido, "Nuclei will exit with missing parameters required for auth" (ex.: "missing global auth parameter: X-API-Key"); resolve-se com `-vars "X-API-Key=123"`. — [nuclei input formats](https://docs.projectdiscovery.io/opensource/nuclei/input-formats.md)
- [SECUNDÁRIO] A flag `-fuzz` foi descontinuada em favor de `-dast` para carregar templates de fuzzing. — [nuclei README](https://github.com/projectdiscovery/nuclei)

### Inferências
- Papel do nuclei no baseline: camada barata de "known-bads" (CVEs de componentes, painéis/arquivos expostos como `/.env` — que o Pynt também reporta no crAPI —, misconfig, templates DAST de SQLi/SSRF/XSS por parâmetro). Limite: valores placeholder ("string") tendem a ser rejeitados por validação; sem sequência, sem segundo usuário.
- Papel do ffuf: descoberta de conteúdo (endpoints não documentados, versões antigas `/v1/`, endpoints de admin) — relevante para API9 e para achar os "shadow endpoints" do crAPI (desafios 2, 7, 8) que não estão no spec. É força bruta com wordlist; não avalia autorização.

### Gaps
- ffuf: nenhuma fonte consultada nesta rodada; o papel descrito acima é conhecimento geral não citado.
- Não verifiquei como exatamente `-dast` interage com `-im openapi`, nem a cobertura atual dos templates DAST do nuclei, nem a versão atual do nuclei em nov/2026.
