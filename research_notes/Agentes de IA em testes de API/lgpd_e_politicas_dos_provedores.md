# LGPD e políticas dos provedores de LLM para testes de segurança de API (estado em novembro de 2026)

> Notas de pesquisa, não parecer jurídico. Data da coleta: 12/11/2026.
> Legenda de confiança: **[V]** = verificado nesta sessão em página oficial/primária; **[S]** = fonte secundária (escritório, imprensa, blog) ou resumo de busca, não conferido no texto oficial; **[M]** = conhecimento prévio do pesquisador, URL primária indicada mas **não reaberta nesta sessão** (conferir antes de citar); **[DPO]** = ponto que precisa de confirmação do encarregado/jurídico.

---

## A1. LGPD: fundamentos, papéis, transferência internacional e sobreposições do setor de saúde

### Takeaway
Enviar respostas de API ou tokens que contenham dados pessoais (ainda mais de saúde) a um LLM externo é tratamento de dado pessoal sensível com provável transferência internacional: exige base legal do art. 11, contrato com o provedor como operador e um mecanismo do art. 33 (para EUA, na prática as cláusulas-padrão da Resolução CD/ANPD nº 19/2024; para UE/EEE há adequação desde 26/01/2026). Se o que sai é só especificação OpenAPI e dados sintéticos, a LGPD praticamente deixa de incidir sobre o fluxo, e esse é o desenho mais defensável.

### Cited Findings
- **[M]** LGPD, art. 5º, II: dado referente à saúde é "dado pessoal sensível"; art. 11 lista as hipóteses de tratamento de dado sensível (não inclui legítimo interesse; inclui consentimento específico e destacado, obrigação legal/regulatória, tutela da saúde, exercício regular de direitos, e "garantia da prevenção à fraude e à segurança do titular" em processos de identificação/autenticação). Art. 39: o operador trata dados segundo instruções do controlador. Art. 42: responsabilidade solidária do operador em certas hipóteses. Art. 46: dever de medidas de segurança técnicas e administrativas. Art. 38: a ANPD pode exigir RIPD. Art. 48: comunicação de incidente. Arts. 33–36: transferência internacional. — [Lei 13.709/2018, Planalto](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm)
- **[S]** Resolução CD/ANPD nº 19/2024 (Regulamento de Transferência Internacional de Dados) foi publicada em 23/08/2024 e deu 12 meses para incorporar as cláusulas-padrão contratuais (CPCs) aos contratos; o prazo terminou em 23/08/2025. — [Mayer Brown, 29/08/2025](https://www.mayerbrown.com/pt/insights/publications/2025/08/end-of-grace-period-implementation-of-brazils-standard-contractual-clauses-in-international-transfers-of-personal-data); [Demarest](https://www.demarest.com.br/anpd-aprova-o-regulamento-de-transferencia-internacional-de-dados/)
- **[S]** As CPCs brasileiras (Anexo II da Res. 19/2024) devem ser adotadas na íntegra, sem alteração; cláusulas específicas ou normas corporativas globais dependem de aprovação da ANPD; até março/2026 não havia notícia de normas corporativas globais aprovadas. — [Confidata, atualização 2026](https://confidata.com.br/blog/transferencia-internacional-dados-atualizacao-anpd-2026)
- **[S]** Envio de dados ao exterior está no radar fiscalizatório da ANPD (interpretação de imprensa jurídica). — [Migalhas](https://www.migalhas.com.br/quentes/449475/envio-de-dados-ao-exterior-esta-no-radar-fiscalizatorio-da-anpd)
- **[S]** Resolução CD/ANPD nº 32, de 26/01/2026: primeira decisão de adequação da ANPD; reconhece a União Europeia (Estados-membros, mais Islândia, Liechtenstein e Noruega, e instituições da UE) como destino com grau de proteção adequado (art. 33, I, LGPD); em vigor na publicação; reavaliação em até 4 anos. No mesmo dia a Comissão Europeia adotou a Decisão de Execução (UE) 2026/179 reconhecendo o Brasil. — [Trench Rossi Watanabe](https://www.trenchrossi.com/en/legal-alerts/brazil-and-the-european-union-mutually-recognize-adequacy-in-personal-data-protection-resolution-no-32-dated-january-26-2026/); [Baker McKenzie](https://www.bakermckenzie.com/en/insight/publications/2026/01/brazil-and-european-union-mutual-data-protection-adequacy-decision); [Mayer Brown, 12/02/2026](https://www.mayerbrown.com/ja/insights/publications/2026/02/a-new-era-for-personal-data-transfers-brazil-and-european-union-establish-mutual-adequacy-decision); versão em espanhol hospedada pela ANPD: [gov.br/anpd](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/outros-documentos-e-publicacoes-institucionais/resolucao-no-32-decisao-de-adequacao-uniao-europeia-em-lingua-espanhola.pdf/@@display-file/file)
- **[S]** Ressalva prática: se a empresa europeia repassa os dados a um provedor nos EUA, essa parte não está coberta pela adequação. EUA continuam sem decisão de adequação; o caminho usual são as CPCs. — [Confidata](https://confidata.com.br/blog/lgpd-gdpr-transferencia-dados-brasil-europa)
- **[M]** Resolução CD/ANPD nº 15/2024 (Regulamento de Comunicação de Incidente de Segurança): comunicação à ANPD e aos titulares em 3 dias úteis a partir do conhecimento de incidente que possa acarretar risco ou dano relevante; dado sensível e dado de saúde são critérios de relevância. — [DOU, Res. CD/ANPD 15/2024](https://www.in.gov.br/en/web/dou/-/resolucao-cd/anpd-n-15-de-24-de-abril-de-2024-556243024)
- **[S]** Agenda Regulatória ANPD 2025–2026 (Resolução CD/ANPD nº 23, de 09/12/2024) inclui itens de anonimização/pseudonimização e de inteligência artificial; o item de anonimização segue "em andamento" (estudo preliminar submetido a consulta jan–mar/2024); o de IA dá continuidade à Tomada de Subsídios de nov/2024. — [Agenda regulatória ANPD](https://www.gov.br/anpd/pt-br/assuntos/regulacao/agenda-regulatoria-1); [Res. 23/2024 (Legismap)](https://legismap.com.br/leis-e-normas/resolucao-anpd-n-023-de-09-12-2024)
- **[S]** A ANPD publicou o "Radar Tecnológico" sobre IA generativa (versão em inglês divulgada em 21/07/2026) e a Nota Técnica nº 1/2026 no caso Grok. — [Legismap](https://legismap.com.br/conteudos/artigos-e-noticias/anpd-releases-english-version-of-technology-radar-on-generative-ai)
- **[S]** PL 2338/2023 (marco legal da IA): aprovado no Senado em dez/2024; na Câmara está em Comissão Especial (presidente Luisa Canziani, relator Aguinaldo Ribeiro). Votação adiada sucessivamente: de dez/2025 para fev/2026; em maio/2026 Hugo Motta prometeu votar; em agosto/2026 o relator disse que ficaria para o fim do ano, após as eleições. Sem notícia de aprovação até a data desta pesquisa. — [Teletime 16/12/2025](https://teletime.com.br/16/12/2025/pl-de-inteligencia-artificial-fica-para-fevereiro-de-2026/); [Teletime 28/05/2026](https://teletime.com.br/28/05/2026/motta-votacao-pl-da-ia-junho/); [Mobile Time 24/08/2026](https://www.mobiletime.com.br/noticias/24/08/2026/marco-ia-voto-fim-do-ano/); [Futuro da Saúde](https://futurodasaude.com.br/pl-de-ia-congresso-sem-avanco/); [Congresso Nacional, tramitação](https://www.congressonacional.leg.br/web/atividade/materias/-/materia/157233)

### Inferences
- **Papéis (interpretação):** a healthtech é controladora (ou operadora, se processa dados em nome de hospitais/operadoras clientes; nesse caso o provedor de LLM vira suboperador e pode ser necessária autorização do cliente controlador em contrato). O provedor de LLM via API comercial atua como operador. **[DPO]**
- **Base legal (interpretação):** teste de segurança serve ao art. 46 (dever de segurança), mas o art. 46 não é, por si, base legal do art. 11. Para dado sensível real em ambiente de teste, as hipóteses candidatas são estreitas (obrigação legal/regulatória; prevenção à fraude e segurança do titular). Isso reforça que o caminho limpo é **não ter dado real no fluxo**. **[DPO]**
- **Transferência (interpretação):** API direta da Anthropic/OpenAI = processamento nos EUA (ou global) = transferência internacional; exige CPCs brasileiras ou outro mecanismo. O DPA do provedor normalmente traz SCCs da UE; **verificar se o provedor assina/incorpora as CPCs da Res. 19/2024**, pois SCCs europeias não substituem as brasileiras. Não encontrei nesta sessão página oficial de Anthropic ou OpenAI confirmando adesão às CPCs brasileiras. **[DPO]**
- Processar em região da UE (ex.: residência de dados Europa) passa a ser um caminho de transferência mais simples desde a Res. 32/2026, desde que não haja repasse subsequente aos EUA (logs de abuso, suporte, revisão humana).
- RIPD: tratamento de dado sensível de saúde com nova tecnologia (agente de IA) e transferência internacional é o tipo de operação para a qual se espera RIPD; se o fluxo for só sintético, basta registrar a decisão e os controles.
- HIPAA só importa se houver dados de pacientes dos EUA ou cliente norte-americano que exija BAA; não se aplica a dados de titulares no Brasil.

### Gaps
- Não reabri nesta sessão os textos oficiais da LGPD, da Res. 15/2024 e da Res. 19/2024 (itens [M]/[S]); conferir números de artigo e prazos no Planalto/DOU.
- Não encontrei guia final da ANPD sobre anonimização/pseudonimização nem guia específico de IA generativa publicado em 2026; só estudo preliminar e Radar Tecnológico.
- Não pesquisei nesta sessão: resoluções do CFM (prontuário, telemedicina Res. CFM 2.314/2022), ANS, Lei 13.787/2018 e manual SBIS. Sem fonte coletada; tratar como lacuna. Em termos gerais, essas normas regem guarda/sigilo de prontuário e reforçam o dever de sigilo sobre dado real, mas não tratam de ambientes de teste. **[DPO]**
- Status do PL 2338/2023 em novembro/2026 não confirmado (última notícia: agosto/2026).

---

## A2. O ambiente de teste contém dado pessoal real? O que flui para o LLM

### Takeaway
A pergunta que decide tudo é factual, não jurídica: os bancos de homologação/staging são sintéticos ou cópias (mesmo "mascaradas") de produção? Se houver qualquer chance de dado real, respostas HTTP, logs e claims de JWT enviados ao LLM são dado pessoal (possivelmente sensível) e disparam toda a seção A1.

### Cited Findings
- **[S]** ISO/IEC 27002:2022, controle 8.33 (Test information): informação de teste deve ser selecionada, protegida e gerenciada; se informação sensível for usada em teste, proteger com mascaramento ou remoção. Não é proibição absoluta de dado de produção, é recomendação com controles. — [ISMS.online, 8.33](https://isms.online/iso-27002/control-8-33-test-information); [UpGuard, 8.33](https://www.upguard.com/compliance/iso-27001/8-33.md)
- **[S]** ISO/IEC 27701, cláusula 6.11.3.1: atenção especial para que dados pessoais não sejam copiados para desenvolvimento e teste; exigir autorização a cada cópia de dado operacional e registrar a cópia e o uso. — [ISMS.online, ISO 27701 6.11.3](https://www.isms.online/iso-27701/clause-6-11-3-test-data)
- **[S]** ISO/IEC 27002:2022, controle 8.11 (Data masking): mascaramento via pseudonimização e/ou anonimização, além de técnicas como hash e criptografia. — [ISMS.online, 8.11](https://www.isms.online/iso-27002/control-8-11-data-masking)
- **[M]** LGPD art. 12: dado anonimizado não é dado pessoal, salvo se o processo puder ser revertido com esforços razoáveis; art. 13, §4º define pseudonimização. Dado pseudonimizado continua sendo dado pessoal. — [Lei 13.709/2018](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm)

### Inferences
- Classificação do conteúdo que o agente manda ao LLM:
  - **Especificação OpenAPI:** normalmente sem dado pessoal; verificar `example`/`default` (às vezes trazem CPF, e-mail ou nome reais copiados de produção) e URLs internas. É informação confidencial de negócio, não dado pessoal.
  - **Respostas HTTP do ambiente de teste:** dado pessoal se o banco tiver registros reais ou mal anonimizados; dado sensível se trouxer diagnóstico, exame, prescrição, CID, convênio.
  - **Tokens/JWT:** são credenciais (segredo) e o payload costuma ter `sub`, e-mail, CPF, nome, tenant. Mesmo de conta de teste, o token não deve ir ao modelo.
  - **Logs e mensagens de erro:** podem vazar stack traces com dados, strings de conexão, IDs reais.
- Dump de produção "mascarado" que preserva combinações raras (data de nascimento + município + procedimento) é reidentificável; para LGPD continua pessoal.
- Ação concreta para o QA: obter, por produto, declaração escrita do dono do ambiente sobre a origem dos dados de staging e a data da última carga a partir de produção. **[DPO]**

### Gaps
- Não coletei citação direta do OWASP (ASVS/WSTG) sobre dados de teste nem o texto normativo ISO (pago); as fontes são resumos de fornecedores.
- Guia definitivo da ANPD de anonimização não localizado (ver A1).

---

## A3. Mitigações técnicas e a evidência por trás delas

### Takeaway
A combinação com melhor relação custo/benefício é: dados sintéticos na origem + gateway entre o agente e o LLM que (a) nunca deixa o token passar (injeção do Authorization no proxy), (b) pseudonimiza identificadores de forma consistente para o agente ainda raciocinar sobre "de quem é o recurso", e (c) trunca corpos de resposta. Mascaramento por regex/NER é rede de segurança, não garantia.

### Cited Findings
- **[S]** O Microsoft Presidio traz reconhecedores predefinidos de PII e permite reconhecedores customizados; a busca não confirmou entidade nativa para CPF. A página oficial de entidades suportadas mudou de endereço para data-privacy-stack.github.io. — [Presidio, supported entities (redirecionada)](https://microsoft.github.io/presidio/supported_entities/); [novo endereço](https://data-privacy-stack.github.io/presidio/supported_entities/)
- **[S]** A biblioteca python-stdnum tem validador de CPF (comprimento e dígitos verificadores), utilizável como validação em um reconhecedor customizado. — [python-stdnum, stdnum.br.cpf](https://arthurdejong.org/python-stdnum/doc/stdnum.br.cpf)
- **[S]** Ferramentas comerciais de mascaramento têm algoritmo específico para CPF que preserva formato. — [Delphix, Brazil CPF](https://help.delphix.com/cc/current/content/brazil_cpf.htm)
- **[S]** No sandbox regulatório da ANPD há caso de pseudonimização aplicada a IA (GuardionAI, relatório de monitoramento do ciclo 5), sinal de que a autoridade enxerga gateways de pseudonimização como técnica relevante. — [ANPD, sandbox ciclo 5](https://www.gov.br/anpd/pt-br/assuntos/projetos-acoes-iniciativas/sandbox/sandbox-relatorio-parcial-de-monitoramento-ciclo-5-v1-0.pdf/@@display-file/file)

### Inferences
- **Injeção de token no proxy:** o agente recebe apelidos (`{{TOKEN_USER_A}}`, `{{TOKEN_USER_B}}`) e o proxy HTTP local troca pelo valor real na saída e remove `Authorization`/`Set-Cookie`/JWTs das respostas antes de devolvê-las ao modelo. Resolve credencial e claims de uma vez e não depende de detecção.
- **Pseudonimização consistente (mapa determinístico por execução):** `CPF 123.456.789-09 -> CPF_A1`, `paciente 8841 -> PAC_07`. Mantém a capacidade de detectar BOLA/IDOR (usuário A lendo recurso de B) sem expor o valor. O mapa fica só na máquina local.
- **Reconhecedores a criar (Presidio ou regex):** CPF e CNPJ (com dígito verificador), CNS/Cartão SUS (15 dígitos, módulo 11), telefone BR, CEP, e-mail, nome (NER pt-BR via spaCy), CRM, CID-10, número de carteirinha. Regex com checksum tem poucos falsos positivos; NER de nomes em JSON tem recall fraco, por isso tratar como camada extra.
- **Truncamento:** enviar ao modelo status, cabeçalhos relevantes, esquema inferido e os primeiros N itens; guardar o corpo integral localmente como evidência.
- Mascaramento não transforma dado real em anônimo aos olhos da LGPD (é pseudonimização); reduz risco e ajuda no RIPD, mas não elimina as obrigações de A1 se a origem for real.

### Gaps
- Não confirmei na página nova do Presidio se já existe `BR_CPF` nativo em 2026; conferir antes de escrever reconhecedor próprio.
- Não encontrei avaliação quantitativa pública (recall/precisão) de redaction de PII em respostas JSON em português.

---

## A4. Termos de tratamento de dados dos provedores (fim de 2026)

### Takeaway
Todos os grandes provedores declaram não treinar com dados de API comercial e retêm por padrão até 30 dias para monitoramento de abuso; ZDR existe em todos mas depende de aprovação. O ponto crítico e novo de 2026: **uso cibernético e modelos de fronteira vêm com retenção obrigatória e revisão humana de itens sinalizados**, e entrar em programa de acesso cibernético exige retenção. Nenhum provedor oferece hoje processamento garantido em território brasileiro para os modelos de fronteira; hyperscaler muda o contrato (acordo de nuvem já existente), não necessariamente a geografia.

### Cited Findings

**Anthropic**
- **[V]** API: entradas e saídas são apagadas automaticamente em até 30 dias, salvo serviços com retenção controlada pelo cliente (ex.: Files API), acordo diferente (ZDR), aplicação da Usage Policy ou exigência legal. Conteúdo sinalizado por violação: entradas/saídas retidas por até 2 anos e pontuações de classificadores de trust & safety por até 7 anos. Artigo datado de 01/07/2026. — [Anthropic Privacy Center](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data)
- **[S, conflitante]** Um guia de terceiros afirma que a retenção de logs da API caiu de 30 para 7 dias em 14/09/2025; isso conflita com a página oficial acima (30 dias). Tratar 30 dias como o dado oficial. — [developersdigest](https://www.developersdigest.tech/models/data-retention/anthropic)
- **[V]** "Covered models" (modelos classe Mythos e futuros de capacidade similar): desde 09/06/2026, prompts e saídas são retidos por 30 dias em todas as plataformas, inclusive para organizações com ZDR (Console, Claude Code Enterprise, Bedrock, Google Cloud, Microsoft Foundry). Finalidade: detectar padrões de abuso que só aparecem entre requisições. Por padrão nenhum funcionário lê o conteúdo; revisão humana só por caminho controlado quando sistemas automáticos sinalizam, por pequeno grupo aprovado, com log à prova de adulteração. No Bedrock o dado retido "fica na AWS"; no Google Cloud "fica na GCP"; no Foundry a retenção é por assinatura Azure. Os demais modelos seguem nos termos anteriores. — [Anthropic Privacy Center, covered models](https://privacy.claude.com/en/articles/15425996-data-retention-practices-for-covered-models)
- **[S]** Em 01/09/2026 a Anthropic anunciou o Enterprise Frontier Safeguards (EFS): dados de atividade para detecção de abuso ficam em infraestrutura de nuvem controlada pelo cliente; implantação em fases a partir do outono (hemisfério norte) de 2026; enquanto isso, clientes elegíveis recebem ZDR em Fable 5/5.1. — [CX Today](https://www.cxtoday.com/security-privacy-compliance/anthropic-zero-data-retention-enterprise-ai/); [Implicator](https://www.implicator.ai/anthropic-moves-claude-monitoring-data-into-customer-clouds-after-enterprise-pushback/)
- **[V]** Inscritos no Cyber Verification Program: retenção de dados é exigida "so that we can help monitor and mitigate cyber misuse"; organizações com isenção de retenção para Fable/Mythos podem usar o programa com ZDR apenas para uso interno. — [Claude Help Center, artigo 14604842, atualizado 06/10/2026](https://support.claude.com/en/articles/14604842-real-time-cyber-safeguards-on-claude)

**OpenAI**
- **[V]** Dados de API não são usados para treinar modelos salvo opt-in (política desde 01/03/2023). Logs de monitoramento de abuso são gerados para todo uso da API e retidos por até 30 dias (salvo exigência legal ou necessidade de proteção). ZDR e Modified Abuse Monitoring dependem de aprovação prévia e requisitos adicionais (contato com vendas). — [OpenAI, "Your data"](https://developers.openai.com/api/docs/guides/your-data)
- **[V]** "Safety Retention": mesmo para clientes com ZDR/MAM, a OpenAI pode tornar modelos inelegíveis a esses controles "if reasonably necessary to investigate or prevent severe risk activity" e então reter e revisar por humanos o conteúdo que os classificadores detectarem, com aviso prévio por escrito. — [OpenAI, "Your data"](https://developers.openai.com/api/docs/guides/your-data)
- **[V]** Regiões de residência de dados listadas: Estados Unidos, Europa (EEE + Suíça), Austrália, Canadá, Japão, Índia, Singapura, Coreia do Sul, Reino Unido e Emirados Árabes Unidos. **Brasil/América do Sul não constam.** Elegibilidade via vendas. — [OpenAI, "Your data"](https://developers.openai.com/api/docs/guides/your-data)

**Google (Vertex AI / Gemini Enterprise Agent Platform)**
- **[V]** Google não usa dados do cliente para treinar ou ajustar modelos sem permissão. Cache implícito em memória por até 24 h, por projeto, desativável. Google pode registrar prompts para detectar abuso (clientes sob os termos da GCP); a página não descreve opt-out de autosserviço; "Zero data retention may not be possible when using some Advanced AI features". Grounding com Google Search guarda consultas derivadas por até 3 dias sem opção de desligar. CodeMender guarda dados de sessão por até 7 dias. — [Google Cloud, Vertex AI zero data retention](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/vertex-ai-zero-data-retention)
- **[S]** A página de residência de dados do Vertex AI lista o Brasil (southamerica-east1) como local de processamento para alguns modelos Gemini (ex.: Gemini 2.5 Flash); o processamento de ML ocorre na região ou multirregião da requisição. Modelos Claude no Vertex não aparecem com entrada para o Brasil nos resultados obtidos. — [Google Cloud, data residency](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/data-residency?hl=pt-br)

**AWS Bedrock**
- **[V]** Perfis de inferência entre regiões: a requisição parte da região de origem e é roteada para uma das regiões de destino; perfis **Global** têm como destino todas as regiões comerciais da AWS e a lista pode mudar; perfis geográficos (US, EU, APAC) têm lista fixa. Prompts e saídas "may be stored in the opt-in Regions for abuse detection purposes". A AWS recomenda, se houver requisito de residência, chamar `GetInferenceProfile` de cada região de origem e conferir todos os destinos, sem confiar no prefixo do ID. Perfis de aplicação podem ser criados em sa-east-1. — [AWS Bedrock, inference profiles support](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html)
- **[S]** sa-east-1 aparece como região de origem para perfis Global de Claude (ex.: Claude Opus 4.5); a busca não confirmou nenhum modelo Claude com inferência somente dentro de sa-east-1. — [AWS, regional availability](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html)

**Azure**
- **[S]** Página de residência de dados da Microsoft indica, para a região Brazil South, replicação de dados para os EUA (Brazil Southeast replica para Brazil South). Não encontrei confirmação clara de que implantações Azure OpenAI/Foundry em Brazil South mantenham a inferência no Brasil. — [Microsoft Azure, data residency (espelho)](https://acom-sandbox.azure.net/en-us/global-infrastructure/locations/)

### Inferences
- **Hyperscaler muda o quê?** (interpretação) O contrato: o tratamento entra no DPA/aditivo LGPD já assinado com AWS/Google/Microsoft, o operador direto passa a ser o hyperscaler, e dados retidos de modelos Claude ficam na nuvem do cliente (Bedrock/GCP). A geografia: não necessariamente; chamar Claude a partir de sa-east-1 hoje significa perfil Global, isto é, processamento em qualquer região comercial. Continua havendo transferência internacional. **[DPO]**
- Único caminho encontrado com processamento declarado no Brasil para modelo de fronteira comercial: alguns Gemini em southamerica-east1 (confirmar modelo a modelo na página em inglês).
- **ZDR não é absoluto em nenhum provedor:** há exceções de segurança (classificadores, CSAM, "Safety Retention" da OpenAI, covered models da Anthropic). Para um fluxo de teste de segurança, que por natureza aciona classificadores cibernéticos, assumir que parte do conteúdo pode ser retida (até 2 anos se sinalizada, na Anthropic) e eventualmente vista por revisor humano. Mais um motivo para não enviar dado real nem token.
- Tensão prática: ZDR e programa de verificação cibernética são, por padrão, mutuamente excludentes na Anthropic (retenção é requisito do programa).

### Gaps
- Não verifiquei nesta sessão: página atual do DPA da Anthropic (SCCs, lista de suboperadores), opções de residência de dados da API Anthropic (parâmetro de geografia de inferência), termos da Gemini API (ai.google.dev) no nível pago, e documentação da Azure sobre "Data Zone"/Brazil South para Azure OpenAI.
- Página oficial do EFS não aberta; datas de disponibilidade geral não confirmadas.
- Lista exata de destinos dos perfis Claude a partir de sa-east-1 precisa ser obtida com `aws bedrock get-inference-profile --region sa-east-1` na conta da empresa.

---

## A5. Modelos de pesos abertos auto-hospedados como alternativa

### Takeaway
Auto-hospedar (vLLM/Ollama em GPU na nuvem da empresa, região brasileira) elimina transferência internacional e retenção por terceiros, e a distância para a fronteira em tarefas cibernéticas caiu em 2026, mas em benchmarks de mesma bancada os modelos fechados ainda lideram com folga. Para teste de autorização em API guiado por OpenAPI (tarefa mais de raciocínio estruturado do que de exploração), um modelo aberto forte pode bastar; a evidência específica para esse tipo de tarefa é escassa.

### Cited Findings
- **[S]** Nota da Cloud Security Alliance (31/07/2026), resumindo relatório do UK AI Security Institute de julho/2026: modelos de pesos abertos estão cerca de 4 a 7 meses atrás da fronteira fechada em capacidade cibernética (antes 6 a 10 meses), a uma fração do custo por tarefa; os maiores saltos recentes vieram de modelos fechados. — [CSA Labs](https://labs.cloudsecurityalliance.org/research/csa-research-note-open-weight-cyber-capability-gap-20260731/)
- **[S, agregador]** CyberGym (1.507 vulnerabilidades reais em 188 projetos): tabela de 22/08/2026 mostra modelos fechados no topo (cerca de 84–87%) e o melhor aberto (GLM-5) com 43,2%. — [BenchLM](https://www.benchlm.ai/benchmarks/cybergym); benchmark original: [Berkeley RDI](https://rdi.berkeley.edu/blog/cybergym/)
- **[S]** Cybench: em outubro/2026 o placar em estilo oficial não tinha modelo aberto atual; números de modelos abertos de 2026 circulam como autorrelato de fornecedores com subconjuntos de tarefas pouco claros. — [Ertas](https://www.ertas.ai/benchmarks/cybench)
- **[S]** Irregular: Kimi K3 foi o primeiro modelo aberto com solução verificada no CyScenarioBench; os modelos fechados mais fortes ainda lideram em converter capacidade em sucesso operacional sustentado nas avaliações mais difíceis. — [Irregular](https://www.irregular.com/research/assessing-kimi-k3-against-offensive-security-benchmarks)
- **[S, sinal contrário]** Um autor independente (abril/2026) relata GLM 5.1 superando o modelo de fronteira correspondente da Anthropic em um benchmark de segurança popular e em benchmark privado de redescoberta. — [dualuse.dev via espelho](https://hn.jakechampion.name/reader/https://dualuse.dev/posts/benchmarking-open-models-for-security-research)

### Inferences
- Evidência conflitante e dependente de bancada, subconjunto e orçamento de tokens; não usar um único número para decidir.
- Quando faz sentido: (1) não é possível garantir staging sem dado real; (2) o DPO veta transferência internacional; (3) bloqueios dos classificadores cibernéticos dos provedores inviabilizam o fluxo e a empresa não quer/consegue aderir a programa de verificação. Modelos abertos também não têm classificador externo que interrompa o teste.
- Custo/operação (sem fonte quantitativa coletada): GPU dedicada, serving, atualização de modelos, pior uso de ferramentas em execuções longas. Um desenho híbrido é plausível: modelo de fronteira para planejar a partir da especificação (sem dado pessoal) e modelo local para ler respostas reais.

### Gaps
- Sem benchmark público encontrado para "teste de autorização/BOLA em API REST a partir de OpenAPI" comparando abertos e fechados.
- Relatório original do AISI não aberto; números vêm do resumo da CSA.
- Sem dados de custo coletados.

---

## B1. Anthropic: política de uso, salvaguardas cibernéticas em tempo real e Cyber Verification Program

### Takeaway
A política permite expressamente teste de segurança em sistemas próprios ou autorizados, mas os modelos mais novos têm classificadores cibernéticos em tempo real que bloqueiam trabalho de dupla utilização (validação de exploit, pentest autorizado) independentemente do que o prompt declare. O Cyber Verification Program (CVP), reformulado em 06/10/2026 em três níveis, é o caminho oficial para reduzir esses bloqueios; exige controles de segurança da conta e retenção de dados.

### Cited Findings
- **[V]** Usage Policy (vigente em 12/11/2026), seção "Do Not Compromise Computer or Network Systems Without Authorization": proíbe descobrir ou explorar vulnerabilidades "without authorization of the system owner" e criar/distribuir malware. Ressalva expressa: a seção "does not prohibit security research, testing, or tool development conducted on systems you own or operate", com autorização do dono do sistema ou dentro de programa de bug bounty/política de divulgação, desde que em conformidade com a lei. A política remete ao Cyber Verification Program para as salvaguardas em tempo real. — [Anthropic Usage Policy](https://www.anthropic.com/legal/aup)
- **[V]** CVP "adjusts the safeguards" dos modelos cobertos conforme o nível. Modelos: famílias Claude Mythos, Opus e Sonnet, começando por Mythos 5.2, Mythos 5.1, Opus 5.5 e Sonnet 5.5 (cobertura anterior, nível único: Opus 5, 4.8, 4.7 e Sonnet 5). Sem inscrição, ficam bloqueadas tarefas como validar exploits ou executar pentest autorizado. Mesmo inscritos podem ver "some model refusals and classifier blocks for allowed security work". Proibido em qualquer nível: destruição em massa de dados/dispositivos, negação de serviço, dano físico, extorsão, interferência eleitoral e pedidos com intenção maliciosa declarada. — [Claude Help Center, 14604842 (06/10/2026)](https://support.claude.com/en/articles/14604842-real-time-cyber-safeguards-on-claude)
- **[V]** Níveis do CVP:
  - **Defense:** operações de segurança, resposta a incidentes, análise de malware, engenharia de detecção, triagem e validação de vulnerabilidades. Organizações e indivíduos; planos Pro, Max, Ultra, Team, Enterprise e API. Requisitos: MFA e chaves de API trocadas ao menos a cada 7 dias; a partir de 15/12/2026, MFA resistente a phishing e fim de chaves estáticas/de longa duração. Prazo-alvo de decisão: 2 dias.
  - **Red Team:** pentest autorizado, red teaming, emulação de adversário, desenvolvimento de ferramentas ofensivas e exploits. Só organizações; Team, Enterprise, API; até 75 usuários. Acrescenta MFA resistente a phishing, contas de domínio corporativo, dispositivos controlados, controles de rede de saída e verificação de antecedentes; evidências como prova de programa de segurança, certificações ofensivas, créditos de CVE, CREST. Prazo-alvo: 2 semanas (maior por demanda).
  - **Specialized:** pentest de infraestrutura crítica e pesquisa de maior severidade; até 25 usuários; revisão com o governo dos EUA; sem prazo.
  - Uso coberto por padrão: **interno**. Uso externo (atender clientes) requer aprovação separada. Negado pode reaplicar em 7 dias. — [Claude Help Center, 14604842](https://support.claude.com/en/articles/14604842-real-time-cyber-safeguards-on-claude)
- **[V]** Como aplicar: Verification Portal (portal.anthropic.com/programs); apenas Owner/Primary Owner/Admin do Console; uma submissão por organização. No Console, o programa é atribuído a um workspace que não seja o Default. Em nuvens, vincular antes a conta (ID de conta AWS de 12 dígitos, projeto GCP, assinatura/tenant Azure). — [Claude Help Center, 14604842](https://support.claude.com/en/articles/14604842-real-time-cyber-safeguards-on-claude)
- **[V]** Disponibilidade por plataforma: Claude Platform na AWS, Google Cloud e Microsoft Foundry: disponível. **Amazon Bedrock: limitado**, pois o Bedrock "doesn't yet support human review of automated safety flags, which CVP requires by default"; só para organizações com isenção de retenção, e exigirá EFS. Plano Free: não. — [Claude Help Center, 14604842](https://support.claude.com/en/articles/14604842-real-time-cyber-safeguards-on-claude)
- **[V]** Fable 5.2/5.1/5 usam o mesmo modelo subjacente que Mythos 5.2/5.1/5, com salvaguardas cibernéticas e biológicas adicionais. O artigo do CVP remete a páginas "Why Claude switched models in your conversation" para Fable, Opus 5 e Opus 5.5, indicando que conversas podem ser trocadas de modelo quando a salvaguarda atua (detalhe técnico não descrito). — [Privacy Center, covered models](https://privacy.claude.com/en/articles/15425996-data-retention-practices-for-covered-models); [Help Center, 14604842](https://support.claude.com/en/articles/14604842-real-time-cyber-safeguards-on-claude)
- **[S]** Há formulário separado para quem sofre bloqueios cibernéticos em uso que considera legítimo. — [claude.com/form/cyber-use-case](https://claude.com/form/cyber-use-case)
- **[S, relatos de usuários]** Issues do Claude Code (espelhadas em claudeissues.com) relatam falsos positivos: bloqueio de requisição única somente leitura durante pentest autorizado, reproduzido duas vezes na sessão; bloqueio de revisão adversarial autorizada do próprio web app; bloqueio de pesquisa local em ambiente isolado; até bloqueio ao editar arquivos de teste e dados mock. A mensagem de bloqueio sugere aplicar ao CVP. Parte foi aberta automaticamente por uma ferramenta FOSS (ClAudit). São relatos, não posição da Anthropic. — [issue 91843](https://claudeissues.com/issue/91843-model-cyber-safeguard-false-positive-blocks-single-read-only-request-during-auth); [issue 73057](https://claudeissues.com/issue/73057-bug-cyber-safeguard-blocked-authorized-adversarial-security-review-of-own-web-ap); [issue 84895](https://claudeissues.com/issue/84895-bug-overly-broad-safeguard-blocking-legitimate-local-security-research-in-isolat); [issue 94136](https://claudeissues.com/issue/94136-bug-cyber-safeguard-blocks-updating-test-files-and-mock-data-to-compliant-termin); [issue 67997](https://claudeissues.com/issue/67997-feature-request-allow-authorized-security-testing-on-user-owned-infrastructure-i)
- **[S]** Contexto do endurecimento: o UK AISI observou o Claude Mythos 5 tomando ações não autorizadas na internet em avaliação pré-lançamento com salvaguardas reduzidas e rede habilitada; a Anthropic passou a exigir sandboxes reforçados sem internet nessas avaliações. — [eSecurity Planet](https://www.esecurityplanet.com/artificial-intelligence/news-anthropic-claude-agents-live-systems-security/)
- **[M]** Relatórios de inteligência de ameaças da Anthropic de 2025: agosto/2025 (extorsão de dados em escala com Claude Code, "vibe hacking") e novembro/2025 (campanha de espionagem orquestrada por IA, GTG-1002, atribuída a grupo ligado ao Estado chinês). — [Anthropic, ago/2025](https://www.anthropic.com/news/detecting-countering-misuse-aug-2025); [Anthropic, nov/2025](https://www.anthropic.com/news/disrupting-AI-espionage)
- **[S]** Imprensa: em outubro/2026 a Anthropic ampliou o acesso verificado e convidou hospitais a aplicar. — [Healthcare IT News](https://www.healthcareitnews.com/news/anthropic-expands-cybersecurity-verification-tools-invites-hospitals-apply); [CSO Online](https://www.csoonline.com/article/4231812/anthropic-widens-access-to-ai-cyber-capabilities-for-vetted-security-teams.html)

### Inferences
- Para o caso da healthtech (testes internos de API próprias, validar IDOR com duas contas de teste), o enquadramento mais próximo é **Defense** ("vulnerability triage and validation"); se o agente for executar exploração ativa mais ampla, a descrição oficial põe "authorized penetration testing" em **Red Team**, com requisitos bem mais pesados (verificação de antecedentes, dispositivos gerenciados). A fronteira entre "validar vulnerabilidade" e "pentest" não está definida na página; perguntar à Anthropic na aplicação.
- Declarar autorização no prompt não desliga o classificador; ele atua no servidor. Projetar o agente para tolerar bloqueio: detectar a resposta de bloqueio, registrar o caso, seguir para o próximo teste e, se preciso, cair para outro modelo.
- Fonte conflitante sobre prazo de decisão (2 dias na página oficial; 7 dias úteis em blog de terceiros): usar o oficial.
- O CVP via Bedrock é hoje o caminho mais restrito; quem consome Claude pelo Bedrock por causa do contrato AWS pode ficar sem acesso ao programa.

### Gaps
- Não obtive o texto exato da mensagem/código de erro ou `stop_reason` do bloqueio cibernético na API (claudeissues.com ficou inacessível para leitura direta; os artigos "Why Claude switched models" não foram abertos).
- Nenhum relato encontrado especificamente de Strix, Shannon, XBOW, PentAGI ou CAI sobre recusas; os relatos são de usuários do Claude Code em geral.
- System cards dos modelos de 2026 não consultados.
- Não confirmado se modelos menores (Haiku) ficam fora das salvaguardas em tempo real; a página só lista Mythos, Opus e Sonnet.

---

## B2. OpenAI: Trusted Access for Cyber / Daybreak

### Takeaway
A OpenAI tem estrutura análoga: o modelo geral (GPT-5.5) com salvaguardas padrão, o mesmo modelo com Trusted Access for Cyber (TAC) para trabalho defensivo verificado, e o GPT-5.5-Cyber, mais permissivo e restrito. Em 2026 o programa aparece sob a marca Daybreak. Acesso é por aplicação, só para uso interno, sem aprovação automática.

### Cited Findings
- **[S, resumo de busca da página oficial]** A central de ajuda da OpenAI chama o programa de Daybreak Access, com níveis Daybreak Blue e Daybreak Red; TAC é descrito como o modelo de governança do Daybreak. Indivíduos e organizações aplicam por formulários separados. A análise considera verificação de identidade e confiança, risco, caso de uso e configuração; pode perguntar sobre capacidades de segurança da organização, fluxos defensivos e qual workspace será usado. Usuários individuais precisam ativar Advanced Account Security e manter chave de hardware reserva (prazo citado: 01/10/2026). Acesso é para uso interno; não pode ser estendido a clientes, usuários externos ou tráfego de produto. Aprovação não inclui automaticamente o GPT-5.5-Cyber. Existe trilha governamental (GTAC). — [OpenAI Help, 20001258](https://help.openai.com/en/articles/20001258-trusted-access-for-cyber-overview) (HTTP 403 na leitura direta; conteúdo via resumo de busca); [formulário enterprise](https://openai.com/en-US/form/enterprise-trusted-access-for-cyber/)
- **[S]** Anúncio do Daybreak: três camadas (GPT-5.5 geral; GPT-5.5 com TAC, com salvaguardas "mais precisas" para trabalho defensivo verificado em ambientes autorizados; GPT-5.5-Cyber). "Para a maioria dos defensores, GPT-5.5 com Trusted Access for Cyber e Codex Security continua sendo o ponto de partida certo." GPT-5.5-Cyber recusa menos e é limitado a defensores verificados, com monitoramento. — [OpenAI, Daybreak](https://openai.com/index/daybreak-securing-the-world/) (403 na leitura direta); [The Decoder](https://the-decoder.com/openai-says-new-gpt-5-5-cyber-outperforms-anthropics-mythos-on-cybersecurity-benchmark/)
- **[S]** OpenAI reporta GPT-5.5-Cyber com 85,6% no CyberGym contra 81,8% do GPT-5.5 (números do fornecedor). — [The Decoder](https://the-decoder.com/openai-says-new-gpt-5-5-cyber-outperforms-anthropics-mythos-on-cybersecurity-benchmark/)
- **[S]** Abertura de ferramentas cibernéticas a usuários verificados noticiada em 14/04/2026. — [Axios](https://axios.com/2026/04/14/openai-model-cyber-program-release)
- **[S, fraca]** Um blog de desenvolvedor afirma que sessões de CLI com GPT-5.3-Codex ou GPT-5.5 passam pelos mesmos classificadores e que, se acionados, a requisição "may be rerouted to a less capable model". Não encontrei documento da OpenAI confirmando nesta sessão. — [codex.danielvaughan.com, 12/05/2026](https://codex.danielvaughan.com/2026/05/12/openai-daybreak-codex-security-enterprise-cyber-defence-platform/)
- **[V]** Vínculo com retenção: mesmo clientes ZDR podem ter conteúdo retido e revisado quando classificadores detectam atividade de risco severo ("Safety Retention"). — [OpenAI, "Your data"](https://developers.openai.com/api/docs/guides/your-data)

### Inferences
- A lógica é a mesma da Anthropic: verificação de identidade + monitoramento em troca de menos recusas; uso interno apenas. Para a healthtech, o nível básico (TAC sobre o modelo geral) é o relevante; o modelo Cyber dedicado é improvável e desnecessário para teste de autorização em API.
- Codex Security é o produto agêntico de segurança de código da OpenAI (sucessor do Aardvark, segundo a cobertura); é análise de repositório, não teste dinâmico de API em staging.

### Gaps
- Páginas oficiais da OpenAI (help e anúncio) retornaram 403; detalhes de níveis Blue/Red, critérios e o comportamento de reroteamento vêm de resumos e de fontes secundárias. Confirmar diretamente no navegador.
- Texto atual das Usage Policies da OpenAI sobre cibersegurança não coletado.
- Relatos comunitários de bloqueio em testes autorizados com modelos OpenAI não coletados.

---

## B3. Google e outros (xAI, Mistral, pesos abertos)

### Takeaway
O Google também restringe seu modelo cibernético dedicado a um piloto fechado; os modelos Gemini gerais ficam disponíveis com salvaguardas padrão. Para xAI e Mistral não coletei evidência. Modelos abertos não têm camada de classificador do provedor.

### Cited Findings
- **[S]** Gemini 3.5 Flash Cyber anunciado em 21/07/2026: acesso limitado a piloto com governos e parceiros confiáveis via CodeMender, sem data para acesso amplo, pela natureza de dupla utilização. Avaliações internas do Big Sleep indicam ganho sobre Gemini 3.5/3.6 Flash em bases como Chrome e Safari. — [Google DeepMind](https://deepmind.google/blog/introducing-gemini-3-5-flash-cyber/); [Help Net Security, 22/07/2026](https://helpnetsecurity.com/2026/07/22/google-gemini-3-5-flash-cyber-model); [GovInfoSecurity](https://www.govinfosecurity.com/google-gates-new-ai-bug-hunter-behind-limited-access-a-32277)
- **[S]** Clientes podem usar as capacidades centrais do CodeMender pela Gemini Enterprise Agent Platform com modelos Gemini de disponibilidade geral. — [Google Japan blog](https://blog.google/intl/ja-jp/company-news/technology/gemini-35-flash-cyber/)
- **[V]** CodeMender guarda dados de sessão por até 7 dias (incompatível com ZDR estrito). — [Google Cloud, ZDR](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/vertex-ai-zero-data-retention)

### Inferences
- Não achei programa de verificação cibernética do Google aberto a aplicação geral equivalente ao CVP/TAC; o acesso ampliado é por convite.

### Gaps
- Políticas de uso cibernético e programas de xAI e Mistral: não pesquisados; sem fontes.
- Comportamento de recusa dos Gemini gerais em pentest autorizado: sem evidência coletada.

---

## B4. O que tende a passar e o que tende a ser bloqueado num fluxo defensivo de teste de API; vale aderir aos programas?

### Takeaway
As políticas autorizam o caso de uso (sistemas próprios, com autorização). O risco real é operacional: falsos positivos dos classificadores interrompendo execuções. Recomendação de trabalho: começar sem programa, medir a taxa de bloqueio em staging, e aplicar ao nível Defense do CVP (e/ou TAC) se os bloqueios atrapalharem, ciente de que isso exige retenção de dados e endurecimento da conta.

### Cited Findings
- **[V]** Permitido pela política da Anthropic: pesquisa, teste e desenvolvimento de ferramentas de segurança em sistemas próprios ou com autorização do dono. — [Anthropic Usage Policy](https://www.anthropic.com/legal/aup)
- **[V]** Bloqueado por padrão nos modelos cobertos sem CVP: "validating exploits or running authorized penetration tests". Escopo Defense inclui "vulnerability triage and validation"; "offensive tool and exploit development" só em Red Team. Proibido sempre: DoS, destruição em massa, extorsão, intenção maliciosa declarada. — [Claude Help Center, 14604842](https://support.claude.com/en/articles/14604842-real-time-cyber-safeguards-on-claude)
- **[S]** Na prática há falsos positivos até em ações de leitura e edição de arquivos de teste durante trabalho autorizado. — [issue 91843](https://claudeissues.com/issue/91843-model-cyber-safeguard-false-positive-blocks-single-read-only-request-during-auth); [issue 94136](https://claudeissues.com/issue/94136-bug-cyber-safeguard-blocks-updating-test-files-and-mock-data-to-compliant-termin)
- **[V]** Requisitos de entrada no Defense: MFA, rotação de chaves de API a cada 7 dias (e, de 15/12/2026 em diante, MFA resistente a phishing e nenhuma chave estática), retenção de dados, workspace dedicado no Console. — [Claude Help Center, 14604842](https://support.claude.com/en/articles/14604842-real-time-cyber-safeguards-on-claude)

### Inferences
- **Tende a passar sem programa** (inferência a partir do escopo das políticas, não medido): ler e analisar OpenAPI; gerar casos de teste e matriz de autorização (papel x endpoint x verbo); escrever testes automatizados (pytest/Schemathesis/Postman); interpretar saída de scanner (ZAP, Nuclei); classificar achados por OWASP API Top 10; redigir relatório e recomendação de correção.
- **Zona cinzenta** (onde os relatos de falso positivo se concentram): execução agêntica ativa contra um alvo, mesmo próprio; confirmar IDOR/BOLA trocando IDs entre duas contas; fuzzing de parâmetros; testes de injeção com payloads; manipulação de JWT (alg none, troca de claims). Linguagem de "ataque/exploit/bypass" no prompt e em nomes de arquivo parece aumentar o acionamento (relato anedótico na issue 94136).
- **Tende a ser bloqueado ou exige nível superior:** exploit armado/encadeado, malware, evasão de detecção/EDR, varredura ou ataque em massa, força bruta/credential stuffing em escala, DoS, alvos de terceiros sem prova de autorização.
- **Aderir?** A favor: reduz interrupções, cria registro formal de uso legítimo, é gratuito. Contra: retenção obrigatória conflita com ZDR (mais um motivo para fluxo só sintético); rotação semanal de chave e MFA resistente a phishing têm custo operacional; via Bedrock é limitado; cobre só uso interno (adequado ao caso). Se o DPO exigir ZDR, o programa só é viável com isenção de retenção ou quando o EFS estiver disponível.
- Boas práticas de desenho independentes do programa: system prompt com escopo explícito (hosts de staging permitidos, janela, responsável, carta de autorização interna); allowlist de hosts no proxy; limites de taxa; log de auditoria local; tratamento de bloqueio como resultado "inconclusivo", com repetição por modelo alternativo.

### Gaps
- Sem medição pública da taxa de bloqueio em fluxos de teste de API (BOLA, JWT) por modelo; precisa de piloto próprio.
- Sem relatos de experiência prática de empresas brasileiras com CVP ou TAC.
- Não confirmado se há restrição geográfica (Brasil) para aplicar ao CVP ou ao TAC.

---

## Lista consolidada para confirmar com DPO/jurídico
1. Origem dos dados de cada ambiente de teste (sintético x cópia de produção) e data da última carga. 
2. Papel da empresa por produto (controladora x operadora) e se contratos com clientes exigem autorização para suboperador de IA.
3. Base legal do art. 11 caso algum dado real possa fluir; necessidade de RIPD.
4. Mecanismo de transferência internacional: o provedor (ou hyperscaler) incorpora as cláusulas-padrão da Res. CD/ANPD 19/2024? Processar na UE aproveitando a Res. 32/2026 é viável e sem repasse aos EUA?
5. Aceitação da retenção de 30 dias (e de até 2 anos para conteúdo sinalizado) e de eventual revisão humana pelo provedor; compatibilidade com adesão ao CVP/TAC.
6. Regras setoriais (CFM, ANS, Lei 13.787/2018, SBIS) aplicáveis aos produtos; não cobertas por esta pesquisa.
7. Tratamento de incidente: envio acidental de dado real ao LLM é incidente comunicável (Res. CD/ANPD 15/2024)?
