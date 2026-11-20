# ADR 0054: Paginação inicial e conta par no laboratório

Estado: Proposto. Data: 2026-11-15.

## Contexto

O sorteio de paginação pode alcançar uma página vazia, impedindo a comparação dos itens com o esquema. O laboratório precisava de dois médicos para exercitar a escrita entre contas de mesmo papel.

## Decisão

Na montagem de parâmetros inteiros de consulta, nomes reconhecíveis de página ou deslocamento com mínimo explícito 0 ou 1 recebem esse mínimo. Nomes reconhecíveis de tamanho com máximo explícito recebem 10 quando válido, ou o valor positivo válido mais próximo, respeitados os limites abertos ou fechados. Sem esses indícios ou candidato válido, continua a geração anterior. Valores encadeados e regras explícitas têm precedência; enum mantém seu tratamento anterior. Não se infere paginação de campos de corpo, caminho ou cabeçalho.

A Clínica Piloto recebe uma segunda conta médica associada ao médico já semeado. Sua configuração usa referências a variáveis próprias e a conta não adiciona falha plantada. O perfil roteia a leitura e a atualização do mesmo paciente ao primeiro médico para que o teste possa comparar com o segundo. A permissão de atendimento compartilhado entre médicos pode produzir indicações de leitura e escrita horizontal que exigem avaliação humana, inclusive no modo seguro. Os testes funcionais verificam essa permissão nos dois modos; nenhuma operação é marcada pública para contornar o teste.

## Consequências

A escolha é determinística e limitada pelo esquema, mas nomes ambíguos podem ser interpretados como paginação; uma regra de dados pode substituir essa escolha. O modelo de esquema ainda não representa multipleOf. A demonstração real requer os testes de integração do laboratório; unitários não substituem essa prova.
