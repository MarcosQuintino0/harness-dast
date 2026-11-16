# QA independente V1.9: exportação e fronteiras do diário

Data: 2026-11-16. Revisão offline da integração com `84e9c13`, `7fba85c` e `dda0c0c`, anterior às correções em andamento.

`tests/unit/evals/test_v19_independent_export.py` reproduziu vazamento no pacote exportado: comentário YAML contendo marcador sintético no formato Bearer, não presente no lacre, foi preservado em `knowledge.yml` por `export_reuse`. O modelo fechado é validado, mas o conteúdo original é gravado; a busca de segredos conhecidos não elimina segredos arbitrários em comentários. A preparação da segunda rodada reconstrói YAML, mas isso não corrige a exposição anterior no pacote. O teste exige rejeição ou remoção, sem ditar solução. O responsável informou correção em andamento; ainda não revisada aqui.

A integração revisada grava pendências de probe em `mutations/` e authz em `authz-mutations/`. Assim, uma pendência em uma fase não bloqueia por si uma escrita equivalente na outra. O responsável informou unificação em andamento; falta testar os caminhos combinados após integração. O diário guarda classe `unknown`, não um valor anterior restaurável; a garantia de durabilidade frente a perda de energia não é demonstrada pelo `fsync` do arquivo isolado.

O conhecimento vincula as categorias às fontes e recusa uso ativo com dependência alterada; `effect` permanece proposta e não é habilitada pelo loader. A dupla leitura em `probe` reduz corridas, mas não prova ausência de troca ABA entre leituras e materialização. O teste de dois processos usa alvos e motor falsos e os mesmos documentos em disco; não demonstra a segunda rodada cega nem ausência de retrabalho em APIs reais. A invalidação é conservadora: categoria stale pode bloquear a carga inteira, sem significar uso automático de entrada stale.

O teste independente da exportação falhou sobre o commit revisado; Ruff passou. Não executei Docker, alvo, estudo cego ou suíte geral. As provas dirigidas posteriores devem indicar o commit integrado, preservar o resultado anterior e não substituir a avaliação humana.
