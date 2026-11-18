# 0110. Reestruturação da documentação, licença MIT e congelamento de extras

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** Pacote 1.2 + 1.3 + 1.6 e pendência P-14

## Contexto

Os guias vigentes, as decisões e os registros de versões anteriores dividiam espaço. As regras de contribuição ficavam em dois arquivos, embora o projeto seja pessoal e conduzido por agentes. A licença ainda estava pendente no P-14. O painel, a estratégia, o conhecimento reutilizável e a prévia local já existem e podem receber manutenção enquanto o trabalho se concentra no núcleo do projeto.

## Decisão

Vamos organizar a documentação conforme o [mapa de leitura](../README.md), por finalidade e público. A pasta `docs/arquivo/` guarda registros históricos. Para operar, use os guias vigentes. A cópia cega exclui o arquivo histórico.

O [índice de decisões](README.md) começa com as 17 decisões essenciais em linguagem simples e mantém um catálogo de todos os ADRs com título e estado.

O guia de contribuição separado é encerrado. As orientações de ambiente local, branches, commits e pull requests ficam na Parte A do [AGENTS.md](../../AGENTS.md#parte-a-ao-desenvolver-o-projeto).

O dono decidiu em 18/11/2026 adotar a [licença MIT](../../LICENSE), o que fecha o P-14.

Até nova decisão, o painel (`domain/panel` e módulos relacionados), a estratégia (`strategy*`), o conhecimento reutilizável (`knowledge*`, exceto `knowledge_mutation`) e o `plan` recebem apenas correções de defeitos. `knowledge_mutation` e a mutação pendente integram o núcleo de segurança e continuam evoluindo normalmente.

## Alternativas consideradas

- Manter orientações em dois arquivos exigiria sincronizar regras que os agentes já consultam no `AGENTS.md`.
- Misturar registros históricos aos guias vigentes dificultaria encontrar o procedimento atual e aumentaria o material a filtrar na cópia cega.
- Remover os extras eliminaria recursos disponíveis. Continuar adicionando funcionalidades a eles ampliaria o trabalho de manutenção. O congelamento preserva o uso atual e permite corrigir defeitos.
- Manter a licença em aberto deixaria o P-14 sem resolução após a decisão do dono.

## Consequências

A documentação tem um ponto de entrada por finalidade. O índice facilita encontrar as decisões centrais e consultar o estado registrado em cada ADR. As regras de contribuição ficam no mesmo arquivo que orienta os agentes.

A manutenção dos extras fica limitada a defeitos. O trabalho sobre o diário e o bloqueio por mutação pendente segue as regras do núcleo de segurança.
