-- =============================================================================
-- Usuario de banco SO da limpeza (`hdast cleanup`) da Clinica Piloto, no Oracle Free do lab.
-- Rode como SYSTEM (DBA do ambiente de TESTES), por exemplo com SQLcl ou SQL*Plus:
--   sql system/<senha>@127.0.0.1:21521/FREEPDB1 @create-cleanup-user.sql <senha-da-limpeza>
-- A senha da limpeza e PILOT_ORACLE_CLEANUP_PASSWORD (gerada por `hdast stack up --oracle` e
-- guardada so no estado local da pilha; ou defina a variavel antes de subir).
--
-- Minimo privilegio (docs/como-funciona/operacao/cleanup.md): entrar, ler e apagar nas cinco tabelas de teste.
-- Nada de INSERT, UPDATE, DROP, TRUNCATE, papeis (DBA, RESOURCE, CONNECT) nem outros esquemas.
-- SELECT e necessario: no Oracle 23ai um DELETE com WHERE sem SELECT na tabela da ORA-41900.
-- =============================================================================
CREATE USER HDAST_LIMPEZA IDENTIFIED BY "&1";
GRANT CREATE SESSION TO HDAST_LIMPEZA;
GRANT SELECT, DELETE ON CLINICA.RECEITA TO HDAST_LIMPEZA;
GRANT SELECT, DELETE ON CLINICA.CONSULTA TO HDAST_LIMPEZA;
GRANT SELECT, DELETE ON CLINICA.PACIENTE TO HDAST_LIMPEZA;
GRANT SELECT, DELETE ON CLINICA.MEDICO TO HDAST_LIMPEZA;
GRANT SELECT, DELETE ON CLINICA.CONVENIO TO HDAST_LIMPEZA;
