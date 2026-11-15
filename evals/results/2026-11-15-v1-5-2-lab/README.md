# V1.5.2: provas de integração da Clínica Piloto

Data: 2026-11-15. Branch: `feat/v1-5-2-avaliacao`. Plano: [V1.5.2](../../../docs/plans/2026-11-15-plano-v1-5-2-avaliacao.md). Relatório: [versão 1.5.2](../../../docs/reviews/relatorio-v1.5.2.md).

**Integração automatizada com dados sintéticos, sem agente cego.** Estes resultados provam os mecanismos dos itens C, D e E; não dão nota à versão nem medem o efeito das skills sobre um agente.

Resultado: **44 testes passaram, 2 pulados, 0 falhas**, em **1.183,09 s (19 min 43 s)**. Os dois pulos são verificações específicas do outro modo, não ausência de Docker.

## Execução

```text
uv run pytest -q -x -m "integration and lab_fast" tests/integration/test_lab_authz.py tests/integration/test_lab_error_signals.py
```

As fixtures usam cópias descartáveis do perfil, aprovação pelo suporte de testes, credenciais e chave do ZAP aleatórias no processo. Sobem as imagens com `--build` nos dois modos e encerram cada pilha com `stack down`. Nenhum pedido ao alvo saiu de comando `hdast` ou do suporte de testes autorizado. Nenhum `hdast profile approve`, `secret set`, `secret delete` ou limpeza operacional foi executado.

## Autorização e paginação

| Medida | Vulnerável | Seguro |
| --- | --- | --- |
| Requisições do authz | 171 | 163 |
| Operações testadas por horizontal_write | 1 | 1 |
| Operações testadas por excessive_data | 17 | 16 |
| Achados de excessive_data | 1 | 0 |
| Recursos sintéticos criados | 10 | 10 |

O teste confere lista de pacientes com itens e ausência de `no_sample_data` **em `listarPacientes`**. Outras operações ainda podem não fornecer amostra. O acesso entre médicos a pacientes é compartilhado por regra do laboratório: os dois alertas no modo seguro (`authz_horizontal` em `buscarPaciente` e `authz_horizontal_write` em `atualizarPaciente`) são indicações para triagem, não novas falhas plantadas.

Os JSONs `lab-authz-*-v2.json` preservam resumos das técnicas, contagens, tempos, motivos de não teste, métodos e resultados da matriz. Não contêm senha, token nem corpo de resposta.

## Sinais da cerca

| Medida | Vulnerável | Seguro |
| --- | --- | --- |
| Requisições do ZAP | 657 | 1.233 |
| Respostas liberadas com status na janela do sinal | 250 | 508 |
| Respostas com sinal | 139 | 0 |
| Achados de sinal agrupados | 4 | 0 |
| Achados omitidos pelo teto | 0 | 0 |
| Caminhos distintos observados sob a rota de CRM | 83 | 72 |

No vulnerável, `stack_trace_java` ficou em três grupos com operação identificada: `buscarMedicoPorCrm` (10 ocorrências), `buscarMedico` (2) e `buscarPacientesPorNome` (1). As outras 126 ocorrências ficaram em um só grupo fora do contrato, sem inventar `operation_id`. Total: 139 ocorrências em quatro achados, abaixo do teto de 500.

O teste inclui uma leitura com parâmetro de caminho e resposta base válida, varredura real pelo ZAP e comparação dos grupos com a auditoria. A busca por nome produz o sinal determinístico no probe vulnerável e é pulada pelo scan porque deu erro; no seguro, tem sucesso e também é varrida. Por isso o número de operações e pedidos dos modos difere. Isto não é comparação de desempenho.

As asserções passaram para contagens, grupos, redação, ausência de segredos e pedidos dentro do escopo. O `stack down` foi executado nos encerramentos e `docker compose ls -a` devolveu lista vazia ao final.

## Limites e origem

- Primeira tentativa: 46 erros de preparação porque o build Maven falhou. Uma asserção ainda esperava quatro usuários na semente; foi atualizada para cinco, com verificação do segundo médico, sem alterar SQL de limpeza. A repetição acima passou com o build padrão e seus testes Java habilitados.
- Sem varredura completa, rodada cega nova, produto real, HTTPS ou Oracle nesta execução. A prova não amplia o que as verificações detectam por desenho.
- Saídas completas e a primeira tentativa ficam em `C:\harness-dast-artefatos\v1.5.2\`; este arquivo publica somente os resumos sanitizados. A origem e os hashes dos arquivos estão em `manifest.json`. `validation.json` registra também a medição de cobertura e a preparação offline da cópia cega.
