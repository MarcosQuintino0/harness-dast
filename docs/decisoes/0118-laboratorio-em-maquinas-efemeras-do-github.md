# 0118. Laboratório em máquinas efêmeras do GitHub

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** T6 da redução do tempo do `lab_fast`. Complementa o [ADR 0117](0117-reuso-de-imagens-no-laboratorio.md).

## Contexto

Construir imagens e manter pilhas de laboratório consome recursos do computador de desenvolvimento. Máquinas efêmeras permitem reservar recursos para a prova e descartar a pilha ao fim da execução. O ciclo diário continua usando `lab_round --nivel changed` localmente.

## Decisão

Vamos admitir máquinas efêmeras do GitHub Actions e do Codespaces para as provas de desenvolvimento. As únicas aplicações admitidas são Clínica Piloto, VAmPI e crAPI em contêineres com dados sintéticos. Produtos reais ficam fora desse ambiente. Quando houver OAST no laboratório, vale somente o emissor interno, com o tráfego de OAST contido na própria máquina.

Os workflows de laboratório usam `permissions: contents: read` e dispensam segredos do repositório. Os disparos permitidos são execução manual e eventos de PR com o rótulo `lab`. A execução em `push` fica vedada. O dono configura **Require approval for all external contributors** em **Settings → Actions → General** para exigir aprovação nos workflows dos PRs externos. [Configuração no GitHub](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#controlling-changes-from-forks-to-workflows-in-public-repositories)

O workflow inicial executa o benchmark da cerca com política sintética, sem enviar pedidos ao alvo. Cada execução tem um caminho de trava temporário, sufixo próprio de pilha e prazo. O JUnit, os tempos e os diagnósticos sanitizados da vigia ficam disponíveis por três dias.

## Alternativas consideradas

- Concentrar as provas no computador de desenvolvimento. O trabalho concorrente continuaria disputando os mesmos recursos.
- Usar máquinas persistentes do time. Isso exigiria provisionamento, manutenção e isolamento dos dados entre rodadas.

## Consequências

A máquina do desenvolvedor fica livre durante o benchmark remoto. O primeiro build depende da disponibilidade do runner e do download de imagens e dependências de build. A aprovação de PRs de fora depende de configuração administrativa do repositório.

## Aceites verificáveis

- `lab.yml` tem prazo, leitura de `contents` e disparos manual ou por PR rotulado.
- A seleção de `lab_round` é fixa para o benchmark da cerca.
- Uma execução em pilha produz JUnit, tempos da subida, medições da cerca e, quando coletado, o diagnóstico da vigia. O resumo sinaliza falha, rodada sem resultado ou benchmark pulado.
