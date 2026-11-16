# QA independente: leitura unitária e marcador do par

Data: 2026-11-16. Revisão offline do commit autoral `9079fa8` aplicado localmente sobre a integração anterior; não é prova em VAmPI real.

Os testes independentes rejeitaram como esperado array vazio, com múltiplos objetos ou ID divergente. Contudo, duas leituras ambíguas geraram achado indevido: um objeto com `id` esperado e `ID` conflitante, e outro com duas chaves JSON `id` de valores diferentes. O parser escolheu um valor e descartou a ambiguidade. A leitura precisa permanecer não testada; o autor foi avisado e prepara correção. Resultado: **12 passaram, 2 falharam**, Ruff passou. As falhas permanecem nos testes, sem `xfail`.

A amostra também verificou exclusão de campo de credencial declarado no perfil, texto `readOnly`, formato e padrão, privilégio, vínculo e regra constante; escrita sem autorização não envia o POST e o marcador sintético não aparece no resultado ou na auditoria testados. A identificação de credencial que não tem metadados distinguíveis não é garantida: não se pode inferir essa classificação do nome de produto. Estes testes não demonstram ausência universal de vazamento nem se as leituras autorizadas provam inexistência global; o inventário é limitado ao que as contas observam e à semântica da API. O cenário VAmPI, modos seguro/vulnerável, permanece para as provas dirigidas da coordenação.
