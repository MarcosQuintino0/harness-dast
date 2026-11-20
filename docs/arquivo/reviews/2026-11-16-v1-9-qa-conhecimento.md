# QA independente V1.9: exportação e fronteiras do diário

Data: 2026-11-16. Revisão offline da integração com `84e9c13`, `7fba85c` e `dda0c0c`, anterior às correções em andamento.

`tests/unit/evals/test_independent_export.py` reproduziu vazamento no pacote exportado: comentário YAML contendo marcador sintético no formato Bearer, não presente no lacre, foi preservado em `knowledge.yml` por `export_reuse`. O modelo fechado é validado, mas o conteúdo original é gravado; a busca de segredos conhecidos não elimina segredos arbitrários em comentários. A preparação da segunda rodada reconstrói YAML, mas isso não corrige a exposição anterior no pacote. O teste exige rejeição ou remoção, sem ditar solução. O responsável informou correção em andamento; ainda não revisada aqui.

A integração revisada grava pendências de probe em `mutations/` e authz em `authz-mutations/`. Assim, uma pendência em uma fase não bloqueia por si uma escrita equivalente na outra. O responsável informou unificação em andamento; falta testar os caminhos combinados após integração. O diário guarda classe `unknown`, não um valor anterior restaurável; a garantia de durabilidade frente a perda de energia não é demonstrada pelo `fsync` do arquivo isolado.

O conhecimento vincula as categorias às fontes e recusa uso ativo com dependência alterada; `effect` permanece proposta e não é habilitada pelo loader. A dupla leitura em `probe` reduz corridas, mas não prova ausência de troca ABA entre leituras e materialização. O teste de dois processos usa alvos e motor falsos e os mesmos documentos em disco; não demonstra a segunda rodada cega nem ausência de retrabalho em APIs reais. A invalidação é conservadora: categoria stale pode bloquear a carga inteira, sem significar uso automático de entrada stale.

O teste independente da exportação falhou sobre o commit revisado; Ruff passou. Não executei Docker, alvo, estudo cego ou suíte geral. As provas dirigidas posteriores devem indicar o commit integrado, preservar o resultado anterior e não substituir a avaliação humana.

## Revalidação após correção de exportação

Sobre a integração `24b229d` e `6357bc5`, os três arquivos independentes de par, diário entre comandos e exportação passaram: **9/9**. Ruff e mypy dirigidos aos três arquivos também passaram. O teste de Bearer desconhecido aceita recusa ou descarte e confirma que o marcador não existe no pacote. Corrigida a assinatura do falso de diário para coincidir com o protocolo, sem alterar o teste de zero POST.

Estes resultados são T1 offline; não substituem T2/T4, comparação das classes com V1.8, prova de novidade global para 200, garantia de persistência após falta de energia nem estudo em duas rodadas cegas. As provas de laboratório e os gates gerais pertencem à coordenação; não foram reproduzidos nesta revisão.

## Revisão da falha no gate de estratégia

Na base que inclui `8f47f9e`, reproduzi a falha de `test_revogacao_apos_compilar_impede_inicio_do_job`: o falso revogava na segunda leitura da aprovação; uma nova leitura de perfil ocorria antes do ponto que o teste pretendia atingir e levantava `ScopeNotApproved` antes de qualquer job. O teste foi alterado para revogar no evento observável de aplicação da política no scanner falso, após o plano ser compilado e antes do primeiro job. A verificação exige plano materializado, política aplicada, revogação, zero jobs e resultado parcial persistido. O teste adjacente continua cobrindo revogação durante job, parada e gravação parcial. Não houve mudança no produto e este ajuste não transforma a falha anterior em passagem retroativa.

Após o ajuste, **18/18** testes de `test_strategy_acceptance.py` passaram; Ruff e mypy dirigidos ao arquivo passaram. Os **9/9** testes independentes de par, diário e exportação também passaram sobre a base com `8f47f9e`, antes deste ajuste isolado no teste de estratégia. Não rodei Docker, laboratório ou suíte geral.
