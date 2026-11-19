# 0118. Laboratório em máquinas efêmeras do GitHub

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** T6 da redução do tempo do `lab_fast`. Complementa o [ADR 0117](0117-reuso-de-imagens-no-laboratorio.md).

## Contexto

Construir imagens e manter pilhas de laboratório consome recursos do computador de desenvolvimento. Máquinas efêmeras permitem reservar recursos para a prova e descartar a pilha ao fim da execução. O ciclo diário continua usando `lab_round --nivel changed` localmente.

## Decisão

Vamos admitir máquinas efêmeras do GitHub Actions e do Codespaces para as provas de desenvolvimento. As únicas aplicações admitidas são Clínica Piloto, VAmPI e crAPI em contêineres com dados sintéticos. Produtos reais ficam fora desse ambiente. Quando houver OAST no laboratório, vale somente o emissor interno, com o tráfego de OAST contido na própria máquina.

Os workflows de laboratório usam `permissions: contents: read` e dispensam segredos do repositório. Os disparos permitidos são execução manual e eventos de PR com o rótulo `lab`. A execução em `push` fica vedada. O dono configura **Require approval for all external contributors** em **Settings → Actions → General** para exigir aprovação nos workflows dos PRs externos. [Configuração no GitHub](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#controlling-changes-from-forks-to-workflows-in-public-repositories)

O workflow `lab.yml` cobre o núcleo (`lab_fast`), as provas (`lab_prova`), a regressão dirigida e a carga, escolhidos pelo input `nivel` (`fast`, `prova`, `regressao`, `carga` ou `tudo`); o PR com o rótulo `lab` roda `fast`. O job `planejar` monta a matriz de pedaços (arquivo e modo) pelo `lab_round --pedacos-json`. O job `imagens` constrói uma vez as imagens do checkout e as passa às outras máquinas pelo `actions/cache`, nunca como artefato; a chave e a identidade das imagens vêm do hash dos arquivos que os Dockerfiles copiam, e o reuso exige essa identidade nas três imagens. Cada pedaço roda numa máquina própria, com no máximo 20 ao mesmo tempo, trava num caminho temporário, sufixo próprio de pilha e prazo. O job `resumo` junta os JUnits e os `estado.json` e falha se faltar artefato, JUnit ou estado, se o job do pedaço não terminar em `success`, se um pedaço não tiver teste aprovado ou se `needs.pedaco.result` não for `success`. A concorrência é por ref, evento e nível, e rótulos que não sejam `lab` não cancelam rodadas válidas. O JUnit, os tempos e os diagnósticos sanitizados da vigia ficam disponíveis por três dias. A carga mantém o benchmark da cerca, que não envia pedidos ao alvo, e soma a matriz V1.7.

## Alternativas consideradas

- Concentrar as provas no computador de desenvolvimento. O trabalho concorrente continuaria disputando os mesmos recursos.
- Usar máquinas persistentes do time. Isso exigiria provisionamento, manutenção e isolamento dos dados entre rodadas.

## Consequências

A máquina do desenvolvedor fica livre durante o benchmark remoto. O primeiro build depende da disponibilidade do runner e do download de imagens e dependências de build. A aprovação de PRs de fora depende de configuração administrativa do repositório.

## Aceites verificáveis

- `lab.yml` não tem gatilho de `push`, usa `permissions: contents: read`, não referencia segredos, tem `timeout-minutes` em todo job, `concurrency` por ref com cancelamento e `persist-credentials: false` em todo checkout. O teste de contrato confere isso.
- A matriz vem do `lab_round --pedacos-json`, e a soma dos pedaços de cada arquivo seleciona exatamente os testes do arquivo.
- Imagens só passam pelo cache. Cada pedaço carrega a tag esperada, confere a identidade `inputs-<hash>` das três imagens e não reconstrói nada se ela bater.
- Uma execução no GitHub, em cada nível, produz um artefato por pedaço com JUnit, métricas e, quando coletado, o diagnóstico da vigia. O resumo sinaliza falha, pedaço sem resultado ou rodada sem teste aprovado.
- A execução real mede o tempo do build frio, a memória do crAPI nas máquinas de 16 GB e o tempo de espera do nível `fast`.
