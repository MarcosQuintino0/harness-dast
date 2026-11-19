# Decisões de arquitetura

## Decisões essenciais

- [0001](0001-dois-planos-agente-propoe-cli-executa.md) — O agente propõe as ações e a CLI executa com as travas de segurança.
- [0004](0004-portas-e-adaptadores-em-tres-camadas.md) — As regras ficam no domínio, os casos de uso coordenam o trabalho e os adaptadores integram sistemas externos.
- [0008](0008-escopo-em-tres-camadas.md) — Três camadas independentes impõem o escopo e bloqueiam a operação quando a permissão é incerta.
- [0009](0009-segredos-por-referencia.md) — O perfil guarda referências a segredos e a CLI protege os valores nas saídas.
- [0010](0010-contrato-json-da-cli-e-codigos-de-saida.md) — A CLI fornece um formato JSON versionado e códigos de saída previsíveis.
- [0017](0017-proxy-de-escopo-com-scopeguard.md) — O proxy verifica cada requisição de saída com a mesma regra de escopo usada pela CLI.
- [0019](0019-pilha-gerenciada-politica-por-execucao-e-login-pelo-proxy.md) — A pilha gerenciada aplica ao proxy a política do perfil de cada execução e encaminha o login pela cerca.
- [0020](0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md) — A limpeza valida o SQL, exige confirmação humana e respeita um teto de linhas.
- [0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md) — A varredura parte das requisições aprendidas. O relatório identifica os achados por impressão digital e mantém a triagem separada.
- [0026](0026-cerca-com-motivo-granular-e-modo-amplo-de-caminho.md) — A cerca explica por que bloqueou uma requisição e o modo amplo só vale com autorização explícita na carta.
- [0035](0035-trava-por-pilha.md) — Uma trava exclusiva impede duas execuções de disputarem a mesma pilha.
- [0036](0036-carta-estruturada.md) — A CLI cria o perfil a partir da carta estruturada e registra a origem das permissões.
- [0037](0037-aprovacao-humana-do-escopo.md) — Uma pessoa aprova os dados que definem as proteções do perfil. Alterações nesses dados exigem nova aprovação.
- [0038](0038-authz-padrao-no-run-e-escrita-pela-carta.md) — O `run` verifica autorização por padrão em modo de leitura. Escritas exigem permissão na carta.
- [0083](0083-copia-cega-por-lista-de-permissao.md) — A cópia cega entrega apenas os arquivos permitidos para operar e mantém o gabarito fora.
- [0096](0096-bloco-attack-da-carta-liga-capacidades-v1-12.md) — Somente a carta pode ativar os controles opcionais definidos no bloco `attack`.
- [0104](0104-bloqueio-local-e-liberacao-humana-de-mutacoes.md) — Uma mutação pendente bloqueia a operação e conta afetadas. Só uma pessoa pode liberar a pendência.

## Todas as decisões

A numeração pula o 0044, que nunca foi publicado como ADR. Os números 0106 a 0109 ficam reservados para ajustes da `develop` que correm em paralelo. O ADR 0106 já consta na tabela.

| Número | Título | Estado |
| --- | --- | --- |
| 0001 | [Dois planos: o agente propõe, a CLI executa](0001-dois-planos-agente-propoe-cli-executa.md) | Aceito |
| 0002 | [Claude Code como runtime do agente](0002-claude-code-como-runtime-do-agente.md) | Aceito |
| 0003 | [Python, uv e tipagem estrita](0003-python-uv-e-tipagem-estrita.md) | Aceito |
| 0004 | [Portas e adaptadores em três camadas](0004-portas-e-adaptadores-em-tres-camadas.md) | Aceito |
| 0005 | [Perfil de produto versionado](0005-perfil-de-produto-versionado.md) | Aceito |
| 0006 | [Regras de dados declarativas](0006-regras-de-dados-declarativas.md) | Aceito |
| 0007 | [ZAP alimentado por requisições válidas](0007-zap-alimentado-por-requisicoes-validas.md) | Aceito. O mecanismo exato depende do spike do M0 e ainda não foi confirmado. |
| 0008 | [Escopo em três camadas](0008-escopo-em-tres-camadas.md) | Aceito |
| 0009 | [Segredos por referência](0009-segredos-por-referencia.md) | Aceito |
| 0010 | [Contrato JSON da CLI e códigos de saída](0010-contrato-json-da-cli-e-codigos-de-saida.md) | Aceito |
| 0011 | [Limpeza por SQL em Oracle com python-oracledb](0011-limpeza-por-sql-oracle-com-python-oracledb.md) | Aceito |
| 0012 | [Dependências `tzdata` e `pyyaml`](0012-dependencias-tzdata-e-pyyaml.md) | Aceito |
| 0013 | [Schema v1 do perfil de produto](0013-schema-v1-do-perfil-de-produto.md) | Aceito |
| 0014 | [Avaliação cega como suíte de evals](0014-avaliacao-cega-como-eval.md) | Aceito (requisito aprovado pelo dono do projeto; implementação planejada para o M6, nada existe ainda) |
| 0015 | [Portas do perfil e carregador de YAML endurecido](0015-portas-do-perfil-e-carregador-de-yaml.md) | Aceito |
| 0016 | [Leitor de OpenAPI próprio, subconjunto seguro de `pattern` e esquema de unicidade](0016-leitor-de-openapi-proprio-e-esquema-de-unicidade.md) | Aceito |
| 0017 | [Proxy de escopo com ScopeGuard](0017-proxy-de-escopo-com-scopeguard.md) | Aceito |
| 0018 | [`probe` com httpx, CSRF, critério de sucesso e trilha de execução](0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md) | Aceito |
| 0019 | [Pilha gerenciada, política do proxy por execução e login pelo proxy de escopo](0019-pilha-gerenciada-politica-por-execucao-e-login-pelo-proxy.md) | Aceito |
| 0020 | [Limpeza: portão de SQL, confirmação humana e teto de linhas](0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md) | Aceito |
| 0021 | [Esquema aditivo do perfil para o alvo piloto: vários níveis, conta por operação, orçamento de login, token vencido e códigos de erro](0021-esquema-aditivo-do-perfil-para-o-alvo-piloto.md) | Aceito |
| 0022 | [`scan` e `report`: varredura por requisição aprendida, achado com fingerprint e triagem separada](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md) | Aceito |
| 0023 | [Verificação do `scan` no ZAP real: CSRF durante a varredura, tráfego medido no proxy e regras desligadas](0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md) | Aceito |
| 0024 | [`hdast run`: etapas encadeadas em um processo, `run.json`, trava de emergência e Oracle na pilha](0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md) | Aceito |
| 0025 | [Limpeza: confirmação só em terminal, amarração por coluna real e demais mudanças de contrato do QA M2 a M5](0025-limpeza-confirmacao-so-em-terminal-e-correcoes-do-qa-m2-m5.md) | Aceito |
| 0026 | [A cerca enxerga melhor (motivo granular) e ganha um modo amplo de caminho](0026-cerca-com-motivo-granular-e-modo-amplo-de-caminho.md) | Proposto |
| 0027 | [Teste de autorização entre contas: comando `authz`, estágio opcional do `run` e artefatos novos](0027-teste-de-autorizacao-entre-contas.md) | Aceito |
| 0028 | [Facilitar o uso: `hdast doctor`, `probe.setup_path`, mensagem do `allow_local`, `init` sem `cleanup/` e prazo da pilha separado do da execução](0028-facilitar-o-uso-doctor-setup-path-allow-local-init-e-prazo-da-pilha.md) | Aceito |
| 0029 | [Relatório agrupado pela causa, página `report.html` e skill de um pedido só](0029-relatorio-agrupado-pagina-html-e-skill-de-um-pedido-so.md) | Aceito |
| 0030 | [Cofre de credenciais do sistema operacional (`secret_ref: keyring:NOME`) e o comando `hdast secret`](0030-cofre-de-credenciais-do-sistema-keyring.md) | Aceito |
| 0031 | [Medição da execução: `metrics.json` e o tempo por regra do ZAP](0031-medicao-da-execucao-metrics-json-e-tempo-por-regra-do-zap.md) | Aceito |
| 0032 | [Painel da execução: páginas HTML estáticas por teste](0032-painel-da-execucao.md) | Proposto |
| 0033 | [Diário de comandos por produto](0033-diario-de-comandos.md) | Proposto |
| 0034 | [Índices do painel (produtos e histórico) e a página ao vivo](0034-indices-do-painel-e-pagina-ao-vivo.md) | Proposto |
| 0035 | [Trava exclusiva por pilha](0035-trava-por-pilha.md) | Proposto |
| 0036 | [Carta de autorização estruturada (`carta.yml`) e `hdast init --from-letter`](0036-carta-estruturada.md) | Proposto |
| 0037 | [Aprovação humana do escopo: impressão digital dos blocos de proteção e `hdast profile approve`](0037-aprovacao-humana-do-escopo.md) | Proposto |
| 0038 | [Teste de autorização ligado por padrão no `run` e escrita só com a carta](0038-authz-padrao-no-run-e-escrita-pela-carta.md) | Proposto |
| 0039 | [Teste de autorização: pedido sem login e token adulterado](0039-pedido-sem-login-e-token-adulterado.md) | Proposto |
| 0040 | [Atribuição em massa: candidatos de campo proibido tirados do OpenAPI e extensão para `POST`](0040-candidatos-de-campo-proibido-do-openapi.md) | Proposto |
| 0041 | [Tabela "quem pode o quê" (`authz.access_matrix`) e verificação `access_matrix`](0041-tabela-quem-pode-o-que.md) | Proposto |
| 0042 | [Teste de autorização: escrita em recurso de outra conta e identificador fora do caminho](0042-escrita-em-recurso-de-outra-conta-e-id-fora-do-caminho.md) | Proposto |
| 0043 | [Defeitos achados no laboratório da V1.4: conexão do proxy de escopo e campo que a entrada já aceita](0043-defeitos-do-laboratorio-da-v1-4-proxy-e-campo-ja-aceito.md) | Proposto |
| 0045 | [Sinais passivos de erro interno](0045-sinais-passivos-de-erro-interno.md) | Proposto |
| 0046 | [Cobertura de operações com HTTP 404](0046-cobertura-de-operacoes-com-404.md) | Proposto |
| 0047 | [Validação offline de exemplos OpenAPI](0047-validacao-offline-de-exemplos-openapi.md) | Proposto |
| 0048 | [Multipart sintético offline](0048-multipart-funcional-offline.md) | Proposto |
| 0049 | [Sinais de erro interno vistos pela cerca](0049-sinais-de-erro-interno-na-cerca.md) | Proposto |
| 0050 | [Varrer operações que deram "não encontrado" (`scan.include_outcomes`)](0050-varrer-operacoes-que-deram-nao-encontrado.md) | Proposto |
| 0051 | [Valores que o esquema proíbe: teste negativo de validação de entrada](0051-valores-que-o-esquema-proibe.md) | Proposto |
| 0052 | [Envio de arquivo (`multipart/form-data`) no `probe` e no `scan`](0052-multipart-no-probe-e-no-scan.md) | Proposto |
| 0053 | [caso e régua da avaliação V1.5.2](0053-avaliacao-v1-5-2.md) | Proposto |
| 0054 | [Paginação inicial e conta par no laboratório](0054-paginacao-e-conta-par-do-laboratorio.md) | Proposto |
| 0055 | [Agrupar sinais pela operação do contrato](0055-agrupar-sinais-por-operacao.md) | Proposto |
| 0056 | [Dicas de encadeamento e contas pares](0056-dicas-de-encadeamento-e-contas-pares.md) | Proposto |
| 0057 | [Papéis que compartilham recursos entre contas](0057-papeis-compartilhados.md) | Proposto |
| 0058 | [Recusa esperada na operação de login](0058-recusa-esperada-login.md) | Proposto |
| 0059 | [Diagnóstico de conflitos e dependências bloqueadas](0059-diagnostico-conflitos.md) | Proposto |
| 0060 | [não pontuar verificações de achados sem evidência](0060-regua-sem-vacuidade.md) | Proposto |
| 0061 | [espera local por execução](0061-espera-de-execucao.md) | Proposto |
| 0062 | [Leitura da atribuição em massa pela conta escritora](0062-leitura-atribuicao-massa-conta-escritora.md) | Proposto |
| 0063 | [Verificação CORS em leituras provadas](0063-verificacao-cors.md) | Proposto |
| 0064 | [Par automático entre contas do mesmo papel](0064-par-automatico-entre-contas.md) | Proposto |
| 0065 | [Conferência de triagem de todas as origens](0065-triagem-de-todas-as-origens.md) | Proposto |
| 0066 | [concessão real e medição do proxy](0066-concessao-real-e-medicao-do-proxy.md) | proposta para V1.7, sem prova em laboratório. |
| 0067 | [Ritmo único e medição do executor](0067-ritmo-unico-e-medicao-do-executor.md) | Proposto |
| 0068 | [declaração consultiva de tecnologias](0068-tecnologias-consultivas.md) | proposta |
| 0069 | [estratégia e limites da prova de desempenho](0069-estrategia-e-limites-da-prova-de-desempenho.md) | proposta para V1.7, sem alegação de prova concluída |
| 0070 | [Envelope autorizado](0070-envelope-autorizado.md) | Proposto |
| 0071 | [Estratégia versionada](0071-estrategia-versionada.md) | Proposto |
| 0072 | [Compilação e prévia sem tráfego](0072-compilacao-sem-trafego.md) | Proposto |
| 0073 | [Aprovação e classificação das alterações](0073-aprovacao-estrategia.md) | Proposto |
| 0074 | [Migração explícita e compatibilidade](0074-migracao-estrategia.md) | Proposto |
| 0075 | [Ritmo proxy em perfis novos, condicionado à prova](0075-ritmo-proxy-em-perfis-novos.md) | Proposto |
| 0076 | [Conhecimento de produto e invalidação seletiva](0076-conhecimento-e-invalidacao.md) | Proposto |
| 0077 | [Diário de intenções de mutação](0077-diario-mutacoes.md) | Proposto |
| 0078 | [prova do par criado e limite de atribuição em massa](0078-prova-par-massa.md) | Proposto |
| 0079 | [canal de conhecimento para estudo de reutilização](0079-exportacao-conhecimento-estudo.md) | Proposto |
| 0080 | [diário de mutação nos estágios ativos](0080-diario-estagios.md) | Proposto |
| 0081 | [Pilha desatualizada: `STACK_STALE` antes do primeiro pedido](0081-pilha-desatualizada.md) | Parcialmente substituído pelo ADR 0106 |
| 0082 | [Leitura de dono no teste horizontal](0082-leitura-de-dono-no-teste-horizontal.md) | Proposto |
| 0083 | [Cópia cega por lista de permissão](0083-copia-cega-por-lista-de-permissao.md) | Proposto |
| 0084 | [Localização da apresentação do painel e do relatório](0084-localizacao-da-apresentacao.md) | Proposto |
| 0085 | [Verificação aditiva de achados](0085-verificacao-de-achados.md) | Proposto |
| 0086 | [Registro de confirmação humana de achados](0086-confirmacao-humana-de-achados.md) | Proposto |
| 0087 | [Reprodução controlada de achados](0087-reproducao-controlada-de-achados.md) | Proposto |
| 0088 | [Apresentação e calibração da verificação](0088-apresentacao-e-calibracao-de-verificacao.md) | Proposto |
| 0089 | [Critério privado de acerto da triagem](0089-criterio-privado-triagem.md) | Proposto |
| 0090 | [Recibo de semente e interrupção da confirmação](0090-vinculo-semente-confirmacao.md) | Proposto |
| 0091 | [Observações passivas de confirmação](0091-observacoes-passivas-de-confirmacao.md) | Proposto |
| 0092 | [Operação de cabeçalho na Clínica Piloto](0092-operacao-de-cabecalho-na-clinica-piloto.md) | Proposto |
| 0093 | [Diagnóstico sanitizado da vigia do proxy](0093-diagnostico-sanitizado-da-vigia.md) | Parcialmente substituído pelo ADR 0106 |
| 0094 | [crAPI na pilha gerenciada](0094-crapi-na-pilha.md) | Proposto |
| 0095 | [Retorno OAST isolado no laboratório](0095-retorno-oast-isolado.md) | Proposto |
| 0096 | [Bloco attack da carta liga as capacidades da V1.12](0096-bloco-attack-da-carta-liga-capacidades-v1-12.md) | Proposto |
| 0097 | [Injeção em cabeçalhos e cookies](0097-injecao-em-cabecalhos-e-cookies.md) | Proposto |
| 0098 | [Chave HMAC fraca de JWT no `authz`](0098-chave-hmac-fraca-de-jwt-no-authz.md) | Proposto |
| 0099 | [OAST na varredura do ZAP](0099-oast-na-varredura.md) | Parcialmente substituído pelo [ADR 0105](0105-lab-oast-bridge-and-verifiability.md) |
| 0100 | [SSRF guiado pelo contrato](0100-ssrf-guiado-pelo-contrato.md) | Proposto |
| 0101 | [Limite de consumo: tamanho de página enorme e tentativas repetidas](0101-limite-de-consumo.md) | Proposto |
| 0102 | [Inventário: versões irmãs não documentadas e documentação exposta](0102-inventario-de-versoes-e-documentacao.md) | Proposto |
| 0103 | [Regras alpha e beta selecionadas na imagem do ZAP](0103-regras-alpha-selecionadas-na-imagem-do-zap.md) | Proposto |
| 0104 | [Bloqueio local e liberação humana de mutações](0104-bloqueio-local-e-liberacao-humana-de-mutacoes.md) | Proposto |
| 0105 | [Ponte OAST na pilha do laboratório e verificabilidade do retorno](0105-lab-oast-bridge-and-verifiability.md) | Proposto |
| 0106 | [Vigia do proxy reverifica o retrato velho em vez de travar](0106-vigia-reverifica-retrato-velho.md) | Proposto |
| 0110 | [Reestruturação da documentação, licença MIT e congelamento de extras](0110-reestruturacao-documentacao-licenca-e-extras.md) | Proposto |
| 0111 | [Hook PreToolUse como segunda camada das permissões do Claude Code](0111-hook-pretooluse-segunda-camada.md) | Proposto |
| 0112 | [`hdast retestar` e `run --only`](0112-retestar-e-run-only.md) | Proposto |
| 0113 | [Imagens publicadas e conferência de versão da cerca](0113-imagens-publicadas-e-conferencia-de-versao.md) | Proposto |
| 0114 | [Padrões mínimos da carta e o comando humano `hdast setup`](0114-padroes-minimos-da-carta-e-setup.md) | Proposto |
| 0115 | [Demonstração local com `hdast demo`](0115-hdast-demo.md) | Proposto |
| 0116 | [Núcleo de integração, provas de versão e seleção por área](0116-niveis-do-laboratorio.md) | Proposto |
| 0117 | [Reuso de imagens no laboratório](0117-reuso-de-imagens-no-laboratorio.md) | Proposto |
| 0118 | [Laboratório em máquinas efêmeras do GitHub](0118-laboratorio-em-maquinas-efemeras-do-github.md) | Proposto |
| 0119 | [O hdast é distribuído como plugin do Claude Code, publicado por tag](0119-hdast-como-plugin-do-claude-code.md) | Aceito |
| 0121 | [Digests empacotados e build só no clone de desenvolvimento](0121-digests-empacotados-e-build-so-no-clone.md) | Proposto |
