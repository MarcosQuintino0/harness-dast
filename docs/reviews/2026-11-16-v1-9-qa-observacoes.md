# QA independente: recibos e snapshot anterior

Data: 2026-11-16. Base `4758f8a`, revisão offline com falsos e diário de arquivo real em diretório temporário. Não toca alvo nem Docker.

O teste independente confirmou, dentro do handler antes da escrita, que a intenção e o estado observado estavam persistidos e que o corpo enviado não foi copiado. Porém, ao simular PUT 500, a intenção permanece pendente e a checagem é inconclusiva, mas não há alerta `possible_unrestored_change`, embora o servidor possa ter alterado o recurso antes de devolver erro. A falha exige alerta; não é prova de que a alteração ocorreu. Responsável avisado e correção em andamento. O teste permanece falhando até ela ser integrada.

Seis testes de captura recusaram recibos com conta desconhecida, índice, gerador ou operação divergentes e execução ou hash incompatíveis, sem gravar documento capturado. São dublês comportamentais de artefatos que não provam autenticidade criptográfica contra substituição maliciosa de todos os arquivos. Os testes anteriores do produto cobrem uso do binding e da regra e restrição da receita aos candidatos e leitura provados. A captura de estado anterior é uma projeção limitada; não substitui restauração automática nem garante durabilidade de metadados em perda de energia.

Na base revisada, seis testes de observação passaram; o teste de snapshot falhou pelo alerta ausente. Ruff e mypy passaram nos dois arquivos. T2/T4 e rodada cega não foram executados nesta revisão.

## Releitura de efeito: três falsos positivos reproduzidos

Na mesma base `4758f8a`, testes comportamentais independentes reproduziram três achados incorretos: PUT com leitura constante 10 e eco 11; PUT com leitura já 11 antes e depois; e POST que armazena 0 mas responde eco 5, com GET posterior 0. A receita já existente permitia comparar o eco ou interpretar estado anterior como efeito novo. Os testes preservam a leitura efetiva e exigem nenhum achado ou efeito. São três falhas além da ausência do aviso no PUT 500; o autor prepara correção. Ruff e mypy dirigidos passaram.
