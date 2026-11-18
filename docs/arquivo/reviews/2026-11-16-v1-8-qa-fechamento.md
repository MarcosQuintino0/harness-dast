# QA independente da retomada V1.8

Data: 2026-11-16. Revisão offline sobre a integração `3d223e0`, após o rebase da V1.8 sobre a V1.7. Esta revisão não substitui a revisão humana exigida por [CONTRIBUTING](../../CONTRIBUTING.md).

**Decisão: bloqueado para aceite integral, condicionado às provas de laboratório e aos gates finais.** Os testes independentes abaixo sustentam a concessão no motor e na fila com arquivos temporários; não demonstram o comportamento da imagem e dos volumes no Docker, nem os critérios de qualidade e previsão B. Não há defeito de segurança reproduzido que permaneça aberto nesta revisão offline. A decisão não antecipa o resultado das provas em andamento pela coordenação.

## Concessão e compatibilidade

Em `tests/unit/adapters/scope_proxy/test_authorization_acceptance.py`, a política é publicada pelo `FileProxyPolicyStore` com aprovação e perfil temporários; o motor e a fila reais usam relógios e espera controlados, sem rede. As verificações cobrem revogação depois da publicação, revogação durante a espera de taxa, substituição atômica da aprovação e do perfil, erro de leitura, persistência da recusa após restaurar o arquivo, alteração de arquivo de outro produto, prioridade da revogação sobre o recuo e parada, prazo e fim de janela durante a espera. O teste registra zero envios no fluxo simulado após a recusa; não é uma medição de tráfego do addon ou de Docker.

O contrato independente `tests/contract/test_proxy_authorization.py` confirma que a ausência de `scan.pacing` mantém `legacy`, a aprovação desse perfil continua válida e não autoriza a troca para `proxy`; uma aprovação específica de proxy é aceita. As fontes são arquivos sintéticos isolados; nenhuma aprovação humana ou segredo foi alterado.

Após integrar a correção de compatibilidade Windows, os 12 testes acima passaram em duas rodadas independentes: **12/12 e 12/12**. Ruff e mypy passaram nos dois arquivos de teste. Antes da correção, observou-se recusa intermitente sem mudança de arquivo: no Windows, `fstat` e `stat` retornaram `ctime` diferentes logo após a gravação. O defeito também apareceu na publicação da política. A correção integrada usa assinatura comum sem `ctime` no Windows, preservando as demais verificações e o hash do conteúdo; os testes de regressão do produtor cobrem discrepância de metadados e alteração com tamanho e `mtime` preservados. Não trate as rodadas anteriores que falharam como evidência verde.

## Composição e limites

O código revisado monta os diretórios da aprovação e do produto em leitura no proxy, exige vínculo para política gerenciada e solicita build do projeto principal ao subir a pilha, para não depender de imagem antiga sem a verificação. A aprovação existente usa substituição atômica; a observação do diretório permite detectar troca ou remoção do arquivo dentro dele. O caminho de produção escolhe a identidade de execução e as fontes a montar, mas sua efetividade depende do comportamento real do Docker e das permissões do host. Essas propriedades ainda precisam ser verificadas no ambiente montado; os testes offline não as provam.

As raízes dos bind mounts são pressupostas estáveis durante a vida da pilha. Substituição administrativa da própria raiz montada não está coberta. O observador trava a pilha até reiniciar quando detecta qualquer alteração do perfil, inclusive em campo livre; isso é conservador e tem custo operacional. A verificação ocorre na concessão e não interrompe conexões já concedidas. A execução real deve confirmar, inclusive, que um pedido recusado não alcança o upstream e que remoção e troca atômica dentro dos diretórios montados são observadas.

## Critérios ainda necessários para o aceite

- Provar no laboratório, com a imagem construída e os volumes efetivos, a revogação por concessão, as permissões de leitura, a recusa sem envio ao upstream e os demais controles aplicáveis. As provas T2 independentes e da captura pública com motor real, ausentes no [parecer anterior](2026-11-16-v1-8-validacao-final.md), não são substituídas por esta revisão.
- Concluir e avaliar qualidade e previsão B conforme o plano, preservando falhas, lacunas e os artefatos das rodadas. A regra 40026 é uma exclusão histórica autorizada pelo dono; não a registrar como perda nova. Essa decisão não elimina outras lacunas ou transforma ausência de evidência em passagem.
- Executar os gates finais sobre o HEAD integrado e registrar os resultados e limitações. A promoção de `init --from-letter` fica condicionada à passagem de qualidade e previsão B, conforme orientação da coordenação.

Esta revisão não executou Docker, varredura, teste de alvo ou suíte completa. As provas e os gates da coordenação devem ser referenciados por seus próprios registros, não presumidos neste parecer.
