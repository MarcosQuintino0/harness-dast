# Registro de decisões arquiteturais (ADR)

Um ADR (Architecture Decision Record) registra **uma decisão por arquivo**: contexto, decisão, alternativas e consequências. Serve para que ninguém precise adivinhar por que o projeto é como é.

## Índice

| ADR | Título | Status | Data | Origem |
| --- | --- | --- | --- | --- |
| [0001](0001-dois-planos-agente-propoe-cli-executa.md) | Dois planos: o agente propõe, a CLI executa | Aceito | 2026-11-13 | AD-01 |
| [0002](0002-claude-code-como-runtime-do-agente.md) | Claude Code como runtime do agente | Aceito | 2026-11-13 | AD-02 |
| [0003](0003-python-uv-e-tipagem-estrita.md) | Python, uv e tipagem estrita | Aceito | 2026-11-13 | AD-03, P-06, P-07, P-13 |
| [0004](0004-portas-e-adaptadores-em-tres-camadas.md) | Portas e adaptadores em três camadas | Aceito | 2026-11-13 | AD-04, AD-09 |
| [0005](0005-perfil-de-produto-versionado.md) | Perfil de produto versionado | Aceito | 2026-11-13 | AD-05, P-04 |
| [0006](0006-regras-de-dados-declarativas.md) | Regras de dados declarativas | Aceito | 2026-11-13 | AD-06, P-02, P-12 |
| [0007](0007-zap-alimentado-por-requisicoes-validas.md) | ZAP alimentado por requisições válidas | Aceito (mecanismo confirmado no spike; veja a nota de 2026-11-14 no ADR) | 2026-11-13 | AD-07 |
| [0008](0008-escopo-em-tres-camadas.md) | Escopo em três camadas | Aceito | 2026-11-13 | AD-11, P-03 |
| [0009](0009-segredos-por-referencia.md) | Segredos por referência | Aceito | 2026-11-13 | AD-12 |
| [0010](0010-contrato-json-da-cli-e-codigos-de-saida.md) | Contrato JSON da CLI e códigos de saída | Aceito | 2026-11-13 | AD-08 |
| [0011](0011-limpeza-por-sql-oracle-com-python-oracledb.md) | Limpeza por SQL em Oracle com python-oracledb | Aceito | 2026-11-13 | AD-13, P-05 |
| [0012](0012-dependencias-tzdata-e-pyyaml.md) | Dependências `tzdata` e `pyyaml` | Aceito | 2026-11-13 | QA A-11 |
| [0013](0013-schema-v1-do-perfil-de-produto.md) | Schema v1 do perfil de produto | Aceito | 2026-11-13 | QA A-01, A-02, A-07, A-11, A-13; detalha o 0005 |
| [0014](0014-avaliacao-cega-como-eval.md) | Avaliação cega como suíte de evals | Aceito (implementado no M6; seis rodadas cegas em 2026-11-13) | 2026-11-13 | Requisito do dono do projeto |
| [0015](0015-portas-do-perfil-e-carregador-de-yaml.md) | Portas do perfil e carregador de YAML endurecido | Aceito | 2026-11-13 | M2 (segunda metade); detalha 0004, 0005 e 0012 |
| [0016](0016-leitor-de-openapi-proprio-e-esquema-de-unicidade.md) | Leitor de OpenAPI próprio, subconjunto seguro de `pattern` e esquema de unicidade | Aceito | 2026-11-13 | M3; detalha 0006 e 0007; P-12 |
| [0017](0017-proxy-de-escopo-com-scopeguard.md) | Proxy de escopo com ScopeGuard | Aceito | 2026-11-13 | Spike M0 (Q4, Q6, Q7); QA A-08, A-18; detalha o 0008 |
| [0018](0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md) | `probe` com httpx, CSRF, critério de sucesso e trilha de execução | Aceito | 2026-11-13 | M3; spike M0 (Q1 a Q3, Q5, Q7); detalha os 0007, 0009 e 0010 |
| [0019](0019-pilha-gerenciada-politica-por-execucao-e-login-pelo-proxy.md) | Pilha gerenciada, política do proxy por execução e login pelo proxy de escopo | Aceito | 2026-11-13 | Integração do `probe` com o ZAP real; detalha 0008, 0017 e 0018 |
| [0020](0020-limpeza-portao-de-sql-confirmacao-humana-e-teto-de-linhas.md) | Limpeza: portão de SQL, confirmação humana e teto de linhas | Aceito | 2026-11-13 | M5 (`hdast cleanup`); detalha os 0009, 0010 e 0011 |
| [0021](0021-esquema-aditivo-do-perfil-para-o-alvo-piloto.md) | Esquema aditivo do perfil para o alvo piloto | Aceito | 2026-11-13 | Verificação do `probe` na Clínica Piloto; substitui a seção 4 do 0016 (um nível) |
| [0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md) | `scan` e `report`: varredura por requisição aprendida, achado com fingerprint e triagem separada | Aceito | 2026-11-13 | M4; spike M0 (Q3 a Q7); detalha 0001, 0008, 0009, 0010, 0017 e 0018 |
| [0023](0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md) | Verificação do `scan` no ZAP real: CSRF durante a varredura, tráfego medido no proxy e regras desligadas | Aceito | 2026-11-13 | Verificação de M4 contra o ZAP 2.17 real; corrige pontos do 0022 |
| [0024](0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md) | `hdast run`: etapas encadeadas, `run.json`, trava de emergência e Oracle na pilha | Aceito | 2026-11-13 | M5; detalha 0010, 0019, 0020 e 0022 |
| [0025](0025-limpeza-confirmacao-so-em-terminal-e-correcoes-do-qa-m2-m5.md) | Limpeza: confirmação só em terminal, amarração por coluna real e demais mudanças do QA M2 a M5 | Aceito | 2026-11-13 | QA M2 a M5; altera 0020, 0022 e 0024 |
| [0026](0026-cerca-com-motivo-granular-e-modo-amplo-de-caminho.md) | A cerca enxerga melhor (motivo granular) e ganha um modo amplo de caminho | Proposto | 2026-11-13 | Medição em três varreduras reais; complementa 0008 e 0024 |
| [0027](0027-teste-de-autorizacao-entre-contas.md) | Teste de autorização entre contas (`hdast authz`) | Aceito | 2026-11-13 | Lacuna medida na avaliação cega; estende 0007, 0018 e 0022 |
| [0028](0028-facilitar-o-uso-doctor-setup-path-allow-local-init-e-prazo-da-pilha.md) | Facilitar o uso: `hdast doctor`, `probe.setup_path`, mensagem do `allow_local`, `init` sem `cleanup/` e prazo da pilha | Aceito | 2026-11-13 | Rodadas cegas de 2026-11-13; altera 0010, 0013, 0017 e 0019 |
| [0029](0029-relatorio-agrupado-pagina-html-e-skill-de-um-pedido-so.md) | Relatório agrupado pela causa, página `report.html` e skill de um pedido só | Aceito | 2026-11-13 | Rodadas cegas de 2026-11-13 |
| [0030](0030-cofre-de-credenciais-do-sistema-keyring.md) | Cofre de credenciais do sistema operacional (`secret_ref: keyring:NOME`) e o comando `hdast secret` | Aceito | 2026-11-13 | Dependência nova `keyring` |
| [0031](0031-medicao-da-execucao-metrics-json-e-tempo-por-regra-do-zap.md) | Medição da execução: `metrics.json` e o tempo por regra do ZAP | Aceito | 2026-11-14 | Artefato novo; usa os arquivos do 0024 |
| [0032](0032-painel-da-execucao.md) | Painel da execução: páginas HTML estáticas por teste, `hdast panel` e a porta `PanelFiles` | Proposto | 2026-11-14 | Desenho final do painel aprovado pelo dono; estende o 0029 e usa os arquivos dos 0024 e 0031 |
| [0033](0033-diario-de-comandos.md) | Diário de comandos por produto | Proposto | 2026-11-14 | Dado da aba Terminal do painel (0032) |
| [0034](0034-indices-do-painel-e-pagina-ao-vivo.md) | Índices do painel (produtos e histórico) e a página ao vivo | Proposto | 2026-11-14 | Completa o 0032; portas `PanelIndexFiles`, `RunLive` e `ScanLive` |
| [0035](0035-trava-por-pilha.md) | Trava exclusiva por pilha (`STACK_BUSY`, saída 8) | Proposto | 2026-11-14 | Revisão do consultor; duas execuções na mesma pilha se corrompiam |
| [0036](0036-carta-estruturada.md) | Carta de autorização estruturada (`carta.yml`) e `hdast init --from-letter` | Proposto | 2026-11-14 | O agente deixa de escrever os blocos de proteção do perfil |
| [0037](0037-aprovacao-humana-do-escopo.md) | Aprovação humana do escopo (`hdast profile approve`, `SCOPE_NOT_APPROVED`) | Proposto | 2026-11-14 | Completa o 0036; só pessoa aprova, como no 0030 |
| [0038](0038-authz-padrao-no-run-e-escrita-pela-carta.md) | `authz` por padrão no `run` (só leitura) e escrita só pela carta (`authz.allow_writes`) | Proposto | 2026-11-14 | Rodada cega sem `--authz` perdeu as falhas de autorização |
| [0039](0039-pedido-sem-login-e-token-adulterado.md) | Pedido sem login e token adulterado (`anonymous_access`, `tampered_token`) | Proposto | 2026-11-14 | Revisão do consultor (Tema 1) |
| [0040](0040-candidatos-de-campo-proibido-do-openapi.md) | Candidatos de campo proibido tirados do OpenAPI e atribuição em massa em `POST` | Proposto | 2026-11-14 | Lista fixa de quatro nomes achava pouco |
| [0041](0041-tabela-quem-pode-o-que.md) | Tabela "quem pode o quê" (`authz.access_matrix`, `--draft-matrix`) | Proposto | 2026-11-14 | Papel menor usando função de papel maior não tinha prova |
| [0042](0042-escrita-em-recurso-de-outra-conta-e-id-fora-do-caminho.md) | Escrita em recurso de outra conta (`horizontal_write`) e identificador na consulta | Proposto | 2026-11-14 | O BOLA só testava leitura com id no caminho |
| [0043](0043-defeitos-do-laboratorio-da-v1-4-proxy-e-campo-ja-aceito.md) | Defeitos do laboratório da V1.4: conexão do proxy e campo que a entrada já aceita | Proposto | 2026-11-14 | Pedidos sem sessão estouravam o tempo; falso positivo de `valor` |
| [0045](0045-sinais-passivos-de-erro-interno.md) | Sinais passivos de erro interno nas evidências redigidas | Proposto | 2026-11-14 | Relatório da V1.5 |
| [0046](0046-cobertura-de-operacoes-com-404.md) | Cobertura de operações sem varredura que responderam HTTP 404 | Proposto | 2026-11-14 | Relatório da V1.5 |
| [0047](0047-validacao-offline-de-exemplos-openapi.md) | Validação offline de exemplos do OpenAPI | Proposto | 2026-11-14 | Inspeção da V1.5 |
| [0048](0048-multipart-funcional-offline.md) | Detecção de multipart e prova sintética em memória | Proposto | 2026-11-14 | Inspeção da V1.5 |
| [0049](0049-sinais-de-erro-interno-na-cerca.md) | Sinais de erro interno vistos pela cerca de escopo | Proposto | 2026-11-14 | Complemento da V1.5 |
| [0050](0050-varrer-operacoes-que-deram-nao-encontrado.md) | Varrer as operações que deram "não encontrado" (`scan.include_outcomes`) | Proposto | 2026-11-14 | Complemento da V1.5 |
| [0051](0051-valores-que-o-esquema-proibe.md) | Valores que o esquema proíbe (`hdast negative`) | Proposto | 2026-11-14 | Complemento da V1.5 |
| [0052](0052-multipart-no-probe-e-no-scan.md) | `multipart` no `probe` e no `scan` | Proposto | 2026-11-14 | Complemento da V1.5 |
| [0053](0053-avaliacao-v1-5-2.md) | Carta, régua e gabarito histórico da avaliação | Proposto | 2026-11-15 | V1.5.2 |
| [0054](0054-paginacao-e-conta-par-do-laboratorio.md) | Paginação inicial e conta par no laboratório | Proposto | 2026-11-15 | V1.5.2 |
| [0055](0055-agrupar-sinais-por-operacao.md) | Agrupar sinais por operação do contrato | Proposto | 2026-11-15 | V1.5.2 |
| [0056](0056-dicas-de-encadeamento-e-contas-pares.md) | Dicas de encadeamento e contas pares | Proposto | 2026-11-15 | V1.5.2 |
| [0057](0057-papeis-compartilhados.md) | Papéis que compartilham recursos | Proposto | 2026-11-15 | V1.5.3 |
| [0058](0058-recusa-esperada-login.md) | Recusa esperada do login e alcance separado do sucesso | Proposto | 2026-11-15 | V1.5.4 |
| [0059](0059-diagnostico-conflitos.md) | Diagnóstico de conflitos e dependências bloqueadas | Proposto | 2026-11-15 | V1.5.4 |
| [0060](0060-regua-sem-vacuidade.md) | Régua de triagem sem pontos por vacuidade | Proposto | 2026-11-15 | V1.5.4 |
| [0061](0061-espera-de-execucao.md) | Espera de execução | Proposto | 2026-11-15 | V1.5.5 |
| [0062](0062-leitura-atribuicao-massa-conta-escritora.md) | Leitura de atribuição em massa pela conta escritora | Proposto | 2026-11-15 | V1.5.5 |
| [0063](0063-verificacao-cors.md) | Verificação CORS | Proposto | 2026-11-15 | V1.5.5 |
| [0064](0064-par-automatico-entre-contas.md) | Par automático entre contas | Proposto | 2026-11-15 | V1.5.5 |
| [0065](0065-triagem-de-todas-as-origens.md) | Triagem de todas as origens | Proposto | 2026-11-15 | V1.5.5 |
| [0066](0066-concessao-real-e-medicao-do-proxy.md) | Concessão real e medição do proxy | Proposto | 2026-11-16 | V1.7 |
| [0067](0067-ritmo-unico-e-medicao-do-executor.md) | Ritmo único e medição do executor | Proposto | 2026-11-16 | V1.7 |
| [0068](0068-tecnologias-consultivas.md) | Declaração consultiva de tecnologias | Proposto | 2026-11-16 | V1.7 |
| [0069](0069-estrategia-e-limites-da-prova-de-desempenho.md) | Estratégia e limites da prova de desempenho | Proposto | 2026-11-16 | V1.7 |

Os ADRs 0012 a 0014 nasceram da [revisão de QA](../reviews/2026-11-13-qa-m1-m2.md) e de um requisito novo do dono do projeto, não do documento de fundação.

A numeração dos ADRs não coincide com a dos cartões AD-xx do documento de fundação. Duas decisões desse documento não viraram ADR próprio e estão documentadas em outro lugar: AD-10 (cobertura como alarme, em [../testing.md](../testing.md)) e AD-14 (revisão em equipe de uma pessoa, em [../../CONTRIBUTING.md](../../CONTRIBUTING.md)). AD-09 (composição e `Protocol`) está dentro do ADR 0004.

## Contratos da V1.8

Bloco independente da V1.7; as decisões seguem **Propostas** até a revisão e a integração humanas.

| ADR | Contrato |
| --- | --- |
| [0070](0070-envelope-autorizado.md) | Envelope derivado do perfil e vinculado à aprovação |
| [0071](0071-estrategia-versionada.md) | Estratégia versionada e escolha neutra de cobertura |
| [0072](0072-compilacao-sem-trafego.md) | Prévia local e plano concreto imutável |
| [0073](0073-aprovacao-estrategia.md) | Classes de alteração e limites da revalidação |
| [0074](0074-migracao-estrategia.md) | Migração explícita, cópia e compatibilidade |
| [0075](0075-ritmo-proxy-em-perfis-novos.md) | Ritmo proxy em perfis novos, condicionado à prova | Proposto | 2026-11-16 | Retomada V1.8; complementa 0067 |

## Quando escrever um ADR

- Dependência nova.
- Porta nova.
- Mudança de contrato: envelope JSON, schema do perfil, códigos de saída, formato do achado.
- Mudança de fronteira ou de camada.
- Resultado de um spike que muda um rumo.
- Qualquer decisão que alguém, daqui a seis meses, perguntaria "por que fizemos assim?".

## Ciclo de vida

1. **Proposto**: rascunho em pull request, a partir de [template.md](template.md).
2. **Aceito**: mesclado na `main`. A partir daí o ADR é **imutável**: não se edita contexto, decisão nem consequências.
3. **Substituído por NNNN**: para mudar de rumo, escreva um ADR **novo** que referencie o antigo. No antigo, a única alteração permitida é trocar o status para "Substituído por NNNN" e acrescentar o link.

Correções de digitação e de links são permitidas.

**Exceção que valeu até o primeiro pull request** (#1, juntado em 2026-11-13). "Aceito" passa a valer quando o ADR é commitado na `main`. Enquanto nenhum ADR tinha sido commitado, o [ADR 0010](0010-contrato-json-da-cli-e-codigos-de-saida.md) foi emendado no lugar, com uma seção "Histórico", e os ADRs [0005](0005-perfil-de-produto-versionado.md), [0008](0008-escopo-em-tres-camadas.md) e [0009](0009-segredos-por-referencia.md) receberam uma nota de estado. Desde o primeiro pull request a exceção não existe mais: mudança posterior entra como seção datada no fim do ADR (veja os ADRs 0033 e 0034). Nome de arquivo: `NNNN-titulo-em-minusculas-com-hifens.md`, numeração sequencial sem reaproveitar números.
