# QA independente: classificação de falhas da suíte

Data: 2026-11-16. Análise da base `4097f39`, complementar a `qa-v1.5.5.md`. A suíte completa e suas correções pertencem ao coordenador.

- Duas expectativas em `test_authz_writes.py` ficaram desatualizadas: a verificação `cors` acrescenta uma linha à ordem de verificações e ao resultado sem exchanges. A atualização deve preservar as demais verificações e a asserção de ausência de escrita.
- A lista esperada de rótulos de técnica precisa incluir `authz_cors`. A tradução do comando `wait` ausente em `command_translation.py` é uma lacuna do produto no painel, não apenas uma expectativa de teste.
- A leitura da atribuição em massa passou a aceitar GET originalmente provado por outra conta e repetido pela escritora. Seu reuso também ampliou `horizontal_write`, cujo contrato anterior exige GET provado pela conta dona: a falha do teste desse contrato evidencia uma regressão funcional. O coordenador encaminhou a restauração desse filtro.
- O teste de orçamento de `horizontal_write` tem um GET para `/1` e três escritas, em `/1`, `/2` e `/3`. Após exigir o mesmo alvo concreto para confirmação, duas escritas ficam sem leitor e não atingem o teto. O teste precisa de uma leitura provada de cada alvo para voltar a exercitar o orçamento. A restrição ao mesmo alvo evita comparar recursos diferentes.

Uma execução dirigida exibiu as quatro falhas de `test_authz_writes.py` e `test_authz_plan_write.py` e foi interrompida após demora para exibir o resumo; não é contabilizada como gate. Esta classificação não substitui a suíte completa após as correções.
