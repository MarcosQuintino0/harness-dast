# QA independente: encadeamento do par automático

Data: 2026-11-15. Base examinada: `4097f39`. Complementa `qa-v1.5.5.md` após a correção motivada pelo laboratório; não substitui o reteste nas APIs do laboratório.

Na base anterior, um contrato sintético com campo de corpo encadeado enviou valor diferente do provado; com inteiro único na faixa de 1 a 100, a geração falhou antes do POST. O contador inicial de 32768 ou mais ultrapassava a capacidade do gerador para essa faixa.

Na base corrigida, foram executados **22 testes dirigidos, todos aprovados**, incluindo regressões de contador, encadeamento e colisão do autor. A prova independente usa um perfil `example`, contas `owner_a` e `peer_b` de papel `member`, contrato e alvo falsos próprios, sem `Clinic` ou `AuthzRig`. Nas variantes com inteiro único limitado a 1–100 e com texto único, o POST preservou `group_id=89`, gerou valor de `serial` diferente do pedido provado, criou um recurso e fez as leituras pelas duas contas; a configuração vulnerável gerou o achado esperado.

A prova é sintética e usa registros do probe preparados pelo teste. Ela não comprova compatibilidade de todos os contratos, nem execução nas APIs do laboratório. A leitura de logs anteriores sem contador permanece limitada pela política da implementação e exige novo probe.
