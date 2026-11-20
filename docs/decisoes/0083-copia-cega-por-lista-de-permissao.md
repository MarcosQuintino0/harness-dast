# 0083. Cópia cega por lista de permissão

- **Status:** Proposto
- **Data:** 2026-11-16
- **Origem:** V1.9.4, isolamento da avaliação

## Contexto

Copiar tudo salvo exclusões deixa pastas novas entrarem sem revisão. Histórico de versões nas instruções,
CHANGELOG, roadmap e pesquisa pode revelar resultados de laboratório ao agente avaliado.

## Decisão

Permitir explicitamente as raízes de `evals/runner/exclusions.py`, mantendo exclusões finas por caso e por caminho.
Entregar código, recursos de build, modelo de produto, infraestrutura local, documentação operacional,
AGENTS/CLAUDE sem histórico e as cinco skills de uso. Excluir todas as skills `dev-*` e qualquer raiz desconhecida.
Não entregar `tests/`: a CLI roda por `uv run hdast` sem eles, e suas fixtures e expectativas conhecem o laboratório.
CHANGELOG, roadmap, pesquisa, planos, reviews e os ADRs sobre a avaliação não entram.
Não copiar links simbólicos, caches ou arquivos locais de segredos.

Gravar `sealed/workspace-manifest.json` com política, raízes e contagem de arquivos copiados, antes das entradas
entregues pelo caso e arquivos gerados. Manter os casos e o formato dos resultados existentes.
Proteger `AGENTS.md` contra adulteração na rodada, como já se faz com `CLAUDE.md`.

## Alternativas

- Manter lista de exclusão: exige prever toda pasta futura e falha aberta na organização.
- Entregar só wheel: impede inspeção legítima da CLI e perde recursos de template/Docker do checkout.

## Consequências e aceite

Rodadas a partir desta mudança veem menos arquivos que as antigas. Isso afeta comparação histórica:
registrar commit, política e manifesto; não atribuir diferença de resultado apenas ao modelo ou ao scanner.
Contratos provam exclusão de raízes novas, projetos locais, histórico/pesquisa/dev-skills e preservação das cinco skills
de uso e regras compartilhadas. Nenhuma rodada de laboratório é executada nesta organização.
