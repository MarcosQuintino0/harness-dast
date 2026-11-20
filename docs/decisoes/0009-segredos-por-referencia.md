# 0009. Segredos por referência

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** AD-12

## Contexto

Tudo que o agente lê vai para o provedor de IA. Tokens costumam carregar e-mail, CPF e identificador de cliente. Colocar credenciais na instrução do agente, como o Strix documenta, expõe o segredo ao modelo e ao histórico.

## Decisão

Vamos guardar no perfil só referências a segredos (`secret_ref: env:NOME`). A CLI resolve o valor, obtém o token e o entrega ao ZAP. As saídas para o agente usam apelidos de conta (`user_a`). O valor vem de variável de ambiente ou de um `.env` ignorado pelo git. As permissões do Claude Code negam a leitura de `.env`.

Um redator central remove cabeçalhos de autenticação, valores de segredos conhecidos e padrões como JWT e CPF antes de qualquer gravação ou saída ao agente. Mensagens de erro nunca incluem valor de segredo nem corpo bruto de resposta.

## Alternativas consideradas

- **Credenciais na instrução do agente.** Simples, mas expõe o segredo ao modelo e ao histórico.

## Consequências

- O agente nunca vê credencial.
- A porta `SecretProvider` tem uma implementação por variável de ambiente na V1; um cofre de segredos no CI fica para depois.
- A forma de entregar o token ao ZAP e de renová-lo em varreduras longas **não está decidida**: depende do spike do M0 (P-10, [ADR 0007](0007-zap-alimentado-por-requisicoes-validas.md)).
- A permissão que nega a leitura de `.env` é barreira de conveniência. O formato exato das regras de permissão precisa ser conferido na documentação do Claude Code ao escrever o arquivo (M6).
- A redação de logs faz parte da fundação do M1; resolução de `secret_ref` e autenticação são do M3. Nota de estado de 2026-11-13: o formato `secret_ref` (`env:NOME`) já é validado pelo domínio (`domain/secret_ref.py`), e a redação cobre chaves, valores registrados, JWT, CPF, exceções, objetos, conjuntos, bytes e pares de cabeçalho.

## Nota de 2026-11-14 (estado; o texto da decisão não mudou)

A entrega do token ao ZAP, que este ADR deixava para o spike do M0, ficou decidida nos ADRs [0018](0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md) e [0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md) (regras do Replacer instaladas pela CLI) e verificada contra o ZAP real. O formato `keyring:NOME` foi acrescentado pelo [ADR 0030](0030-cofre-de-credenciais-do-sistema-keyring.md).
