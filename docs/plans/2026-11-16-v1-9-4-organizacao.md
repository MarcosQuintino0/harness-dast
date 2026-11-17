# V1.9.4: organização do repositório

Data: 2026-11-16. Estado: **implementado na branch, aguardando revisão e integração**.
Não é fechamento de release: pacote permanece 1.9.3 e as entradas estão em `Unreleased`.
O [roadmap](../roadmap.md#estado-atual) é o estado vigente; histórico somente no CHANGELOG.

## Entrega e critérios de aceite

| Fase/item | O que foi feito | Critério de aceite e prova |
| --- | --- | --- |
| 1. Estado e versão | Histórico retirado das instruções, estado consolidado no roadmap, pacote/lock 1.9.3, entradas apontam para o roadmap | Contrato falha com versão divergente ou versão atual no README/arquitetura; regras e limites preservados |
| 1. Navegação | docs/README por intenção, mapa de destinos e índice de planos | Links relativos e âncoras conferidos pelo contrato; estado explícito de cada plano |
| 1. Limpeza | Guia humano, referência técnica e política separados | Conteúdo e limites preservados, links válidos, nenhuma mudança na execução |
| 1. Gates e projetos locais | Seis gates obrigatórios em CONTRIBUTING; projetos locais ignorados | Mesmos comandos nas regras comuns; verificador não percorre projetos independentes |
| 2. Regras e skills | AGENTS canônico, CLAUDE importa, cinco skills de uso e cinco dev-* em fonte única | Contratos de descoberta, prefixo e propósito; travas de operação preservadas; validador das cinco skills passou |
| 2. Cópia cega | Lista de permissão, exclusões finas, manifesto e AGENTS protegido | Contratos recusam raízes novas, projetos locais, dev-skills, histórico, roadmap, pesquisa e testes; cinco skills de uso e instruções sem histórico permanecem |
| 2. Comparação | ADR 0083 proposto e protocolo atualizados | Contexto menor é declarado nas novas rodadas, sem alterar formato dos casos/resultados antigos |
| 2. Pesquisa/retenção | Sete arquivos movidos por git mv; índice; tamanhos recontados e limite documental de 10 MiB por nova rodada | Nomes e conteúdo preservados, links corrigidos; nenhum resultado apagado |
| 3. Apresentação | ADR 0084 proposto compara alternativas e recomenda migração futura | Nenhum HTML/CSS muda de camada; regras e modelos semânticos continuam no domínio |
| 3. panel | domain/panel e testes espelhados, prefixos retirados | Golden, paridade de tokens, escape/CSP, links e suíte existentes preservados; seis gates antes do commit |
| 3. authz | domain/authz e application/authz, incluindo owner_*, testes e falsos | Nenhuma assinatura ou regra alterada; mesma seleção de contas, limites e lacunas; seis gates antes do commit |
| 3. ports | 47 declarações em 12 módulos por consumidor, compartilhadas em common_ports | Comparação AST confirmou classes, assinaturas e docstrings idênticas; tipagem, falsos e contratos existentes verdes |
| 3. report | domain/report e testes/apoio espelhados | Golden, formatos e envelope preservados; seis gates antes do commit |
| 3. Mapa | domain/application mapeados por assunto com contagens disjuntas e destino de código novo | Inventário confere com o código; somas excluem __init__.py explicitamente |
| 3. CI | Windows unitário/contrato, timeouts, imagens explícitas e saída 5 recusada | Configuração YAML inspecionada localmente; execução real do CI pendente |
| 3. Registro | Plano, índice, roadmap e CHANGELOG Unreleased | Sem seção 1.9.4 e sem carimbo antecipado; relatório de evidência com commits/gates |

## Movimentações

- `panel`: domain=29, tests_domain=24.
- `authz`: domain=35, tests_domain=26, application=17, tests_application=21, fakes=3.
- `report`: domain=16, tests_domain=13.

Os arquivos foram movidos com `git mv`; `__init__.py` são novos, sem reexportações de compatibilidade.
As portas foram redistribuídas sem mover apresentação para adaptadores nem mudar contratos públicos da CLI.
O wheel 1.9.3 foi construído localmente: contém os 426 arquivos Python, incluindo os novos pacotes e portas, e exclui os caminhos antigos conferidos.

## Fora do escopo e limites

- Nenhum Docker, stack, alvo, limpeza, piloto real, varredura completa ou rodada cega executado.
  O laboratório estava reservado a outra sessão; o briefing limita esta entrega aos degraus 1 e 2.
- CI não foi executado de verdade. A preparação de imagens e o job Windows precisam de prova no GitHub Actions.
- ADRs 0083 e 0084 continuam propostos; não aceitar ADR por conta própria.
- Sem push, troca de branch, reescrita de histórico ou --no-verify. Um commit por fase/agrupamento, somente após seis gates verdes.
- Não foram lidos segredos nem alterados casos ou resultados históricos. `translate-app/`, `sites/`, checkout principal e outras worktrees ficaram fora do trabalho.

## Intercorrências de validação

Os launchers locais de pytest/mypy/import-linter/vulture inicialmente recusaram execução com
`uv trampoline failed to canonicalize script path`; os pacotes foram reinstalados somente na .venv desta worktree.
No recorte do painel, a lista exata de leitores de path_mode ainda citava o arquivo antigo: o destino foi corrigido,
sem permitir leitores adicionais, e a repetição passou. Duas chamadas de recorte de autorização apontaram nomes de
arquivos inexistentes e não coletaram testes; o recorte corrigido passou 1.018 testes e a suíte inteira também passou.
Essas falhas de ambiente/seleção não foram tratadas como provas verdes nem exigiram afrouxar contratos ou testes.

## Riscos e revisão prioritária

Conferir primeiro a fronteira da cópia cega e seu manifesto: menor contexto muda a comparação histórica.
Depois, revisar imports/nomes de authz (especialmente owner_*), portas comuns e os golden de painel/relatório.
Conferir o tamanho da integração no runner e as imagens necessárias antes do primeiro disparo manual do CI.
As referências de regras em ADRs aceitos e relatórios datados são históricas; a fonte canônica atual é AGENTS.
