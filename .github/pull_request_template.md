## O que muda e por quê

<!-- Um pull request, um assunto. Acima de ~400 linhas alteradas, divida. -->

## Roteiro de revisão (autorrevisão)

- [ ] A mudança respeita as camadas e não cria dependência nova sem ADR.
- [ ] Não há regra de negócio em adaptador ou na CLI.
- [ ] Os testes validam comportamento e casos negativos, não só exercitam linhas.
- [ ] Toda entrada externa é validada na fronteira.
- [ ] Nenhum segredo ou dado pessoal pode chegar a log, erro ou saída para o agente.
- [ ] A mudança não amplia escopo, limites ou o que a limpeza apaga.
- [ ] Nomes, tamanho de função e comentários seguem a seção 5 do documento de fundação técnica.
- [ ] Documentação e contrato atualizados.

## Definition of Done

- [ ] Atende ao critério de aceite do item, demonstrado contra o lab quando aplicável.
- [ ] Critérios de "suficientemente testado" cumpridos.
- [ ] Todos os gates do CI verdes, sem exceção nova não justificada.
- [ ] Sem código morto, `TODO` órfão ou `type: ignore` sem explicação.
- [ ] Documentação afetada atualizada; ADR escrito se a mudança pedir.
- [ ] `CHANGELOG.md` atualizado.
- [ ] Revisão concluída (autorrevisão, revisão por IA e, em escopo, segredos, limpeza e permissões do agente, revisão humana via CODEOWNERS).
