-- =============================================================================
-- Limpeza da Clinica Piloto (Oracle SQL, tambem valido em H2 modo Oracle).
-- ESCRITO POR UMA PESSOA. O agente de IA nao altera este arquivo.
--
-- Apaga somente linhas criadas, DURANTE a execucao, pelas contas de teste.
-- Linhas de semente (CREATED_BY = 'seed') e de outras contas nunca casam.
--
-- Variaveis de ligacao (todas obrigatorias, nenhuma concatenacao de texto):
--   :run_start   TIMESTAMP em UTC do inicio da execucao (a aplicacao grava CREATED_AT em UTC)
--   :account_1 .. :account_4   usernames das contas de teste (admin, medico, paciente A, paciente B)
--
-- Sem COMMIT: quem confirma e a CLI, depois do aceite de uma pessoa.
-- Ordem: filhos antes dos pais (RECEITA, CONSULTA, PACIENTE, MEDICO, CONVENIO).
-- Cada comando termina em ponto e virgula e nenhum comentario contem ponto e virgula.
-- =============================================================================

-- 1. Receitas criadas pelas contas de teste, ou penduradas em consultas que serao apagadas.
DELETE FROM RECEITA
 WHERE CREATED_AT >= :run_start
   AND (CREATED_BY IN (:account_1, :account_2, :account_3, :account_4)
        OR CONSULTA_ID IN (SELECT ID FROM CONSULTA
                            WHERE CREATED_AT >= :run_start
                              AND CREATED_BY IN (:account_1, :account_2, :account_3, :account_4)));

-- 2. Consultas criadas pelas contas de teste, ou penduradas em pacientes que serao apagados.
DELETE FROM CONSULTA
 WHERE CREATED_AT >= :run_start
   AND (CREATED_BY IN (:account_1, :account_2, :account_3, :account_4)
        OR PACIENTE_ID IN (SELECT ID FROM PACIENTE
                            WHERE CREATED_AT >= :run_start
                              AND CREATED_BY IN (:account_1, :account_2, :account_3, :account_4)));

-- 3. Pacientes criados pelas contas de teste.
DELETE FROM PACIENTE
 WHERE CREATED_AT >= :run_start
   AND CREATED_BY IN (:account_1, :account_2, :account_3, :account_4);

-- 4. Medicos criados pelas contas de teste.
DELETE FROM MEDICO
 WHERE CREATED_AT >= :run_start
   AND CREATED_BY IN (:account_1, :account_2, :account_3, :account_4);

-- 5. Convenios criados pelas contas de teste.
DELETE FROM CONVENIO
 WHERE CREATED_AT >= :run_start
   AND CREATED_BY IN (:account_1, :account_2, :account_3, :account_4);
