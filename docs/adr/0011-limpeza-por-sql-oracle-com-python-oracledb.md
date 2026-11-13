# 0011. Limpeza por SQL em Oracle com python-oracledb

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** AD-13, P-05

## Contexto

A varredura ativa do ZAP cria, altera e apaga dados em ambiente de testes compartilhado. A limpeza é a única parte do sistema que apaga dados de propósito; um erro aqui afeta outros times.

## Decisão

Vamos tratar a limpeza como hook escrito por pessoa, por execução, com confirmação.

- Cada produto tem um hook de limpeza escrito e revisado por alguém do time do produto. O agente pode sugerir rodar `hdast cleanup`, mas não escreve nem altera o hook.
- Na V1 o hook é um arquivo **SQL para Oracle** (P-05), executado com o driver **python-oracledb**, que conecta sem instalar o cliente Oracle na máquina.
- O usuário de banco da limpeza só pode apagar nas tabelas de teste.
- A CLI roda o SQL dentro de uma transação, mostra quantas linhas seriam apagadas e só confirma depois do aceite explícito de uma pessoa.
- O gerador de dados marca o que cria com o identificador da execução sempre que o campo permitir, para que a limpeza apague só o que aquela execução criou.

## Alternativas consideradas

- **Limpeza gerada pelo agente a partir do Swagger.** Arriscado.
- **Restaurar o banco inteiro.** Simples, mas derruba o trabalho de quem divide o ambiente.
- **Chamar o `sqlplus` por fora.** Exige o cliente Oracle na máquina.
- **Chamadas à API ou endpoint de reset.** Dependem do acesso que o QA tem; fora da V1 (P-05).

## Consequências

- Só Oracle na V1. Outros bancos exigem ADR novo.
- A dependência python-oracledb entra com este ADR; licença e manutenção devem ser conferidas ao adicioná-la. Ela ainda não consta em `pyproject.toml`.
- Exige que os dados criados sejam identificáveis.
- A conexão com o Oracle de testes é validada no spike do M0.
- Planejado para o M5; nada disso existe hoje.
