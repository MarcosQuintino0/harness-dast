# Complemento ao QA independente da V1.8

Data: 2026-11-16. Complementa o [parecer original](2026-11-16-v1-8-qa.md), sem alterá-lo. A revisão foi feita sem Docker nem alvo.

O vínculo de dependências agora detecta, em testes com fontes alteradas, mudanças de ambiente, autorização, conta, OpenAPI, regras de dados, fluxos, planejamento e versão simulada do motor. O teste de domínio confirmou que a configuração de limpeza, independente dessa escolha, preserva o vínculo. Na CLI real, as sete mudanças locais alteraram os respectivos resumos; a validação indicou revisão necessária e tanto a prévia quanto o carregamento para execução recusaram a escolha.

**Limite:** como a versão efetiva do motor não está disponível para o contexto de validação nesta entrega, qualquer escolha não vazia é indicada como `engine_unavailable` e recusada, inclusive com as demais fontes íntegras. Isso demonstra a falha fechada e os resumos de dependências, não uma revalidação operacional bem-sucedida de escolha com motor conhecido. O perfil legado e a estratégia sem escolhas continuam utilizáveis.

Passaram 39 testes focados de CLI e aplicação, além de `ruff check` dos arquivos de QA e `mypy` nas plataformas Windows e Linux. A versão do motor diferente foi testada no domínio, não em ZAP real. Os testes de laboratório, gates finais e validação independente de fechamento cabem à coordenação.

**Decisão mantida: corrigir.** O bloqueio registrado no parecer original permanece: a revisão de aprovação antes dos jobs e nos polls não demonstra revalidação em cada concessão do proxy entre polls. As provas de cobertura executada e detecção nas duas APIs também não são produzidas por este complemento.
