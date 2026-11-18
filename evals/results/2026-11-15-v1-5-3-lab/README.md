# V1.5.3: papéis compartilhados na Clínica Piloto

Data: 2026-11-15. Código e teste de integração: `0e3548b23cee2b3046ab230172c6b7dd753c7dca`. [Plano](../../../docs/arquivo/plans/2026-11-15-plano-v1-5-3-papeis-compartilhados.md) e [relatório](../../../docs/arquivo/reviews/relatorio-v1.5.3.md).

**Prova automatizada de integração, sem agente cego.** `uv run pytest -q -m "integration and lab_fast" tests/integration/test_lab_authz.py`: **33 passaram, 3 pulados**, em **863,92 s**. Os pulos são verificações específicas do outro modo, sem falta de Docker.

| Medida | Vulnerável | Seguro |
| --- | --- | --- |
| Pedidos do authz | 165 | 157 |
| Achados horizontais entre médicos | 0 | 0 |
| Achados horizontais entre pacientes | 1 | 0 |
| Total de achados altos | 3 | 0 |
| Omissões por `shared_role` (leitura / escrita) | 1 / 2 | 1 / 2 |
| Recursos sintéticos criados | 10 | 10 |

A cópia descartável do perfil declara `medico` compartilhado. `buscarPaciente`, `atualizarPaciente` e `atualizarStatusConsulta` registram `shared_role`; a escrita horizontal em `atualizarPaciente` não é enviada. No vulnerável, `buscarConsulta` continua gerando BOLA entre contas distintas do papel `paciente`. Os outros dois achados altos são exposição excessiva e atribuição em massa. No seguro não houve achado de autorização, sem exceção para médico.

As fixtures reconstruíram as imagens nos dois modos, usaram credenciais e chave do ZAP aleatórias no processo e encerraram cada pilha com `stack down`. As asserções conferiram pedidos pela cerca, ausência de DELETE, de pedidos fora do escopo, de segredos nos artefatos e de erro de transporte. Ao final, `docker compose ls -a` retornou `[]`. Nenhum `hdast profile approve`, `secret set`/`delete` ou limpeza foi executado.

Os dois JSONs `lab-authz-*-v3.json` preservam contagens, técnicas, papéis, operações, motivos e tempos, sem senha, token ou corpo de resposta. [manifest.json](manifest.json) registra origem e SHA-256; [validation.json](validation.json) registra os resultados de integração, cobertura e preparação offline. Saídas completas em `C:\harness-dast-artefatos\v1.5.3\`.

Não houve produto real, `lab_full` ou rodada cega nova, conforme o recorte do plano. O efeito das skills sobre um agente não foi medido. Os tempos dos modos não constituem comparação de desempenho.
