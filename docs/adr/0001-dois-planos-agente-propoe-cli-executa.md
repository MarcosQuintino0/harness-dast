# 0001. Dois planos: o agente propõe, a CLI executa

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** AD-01

## Contexto

Um agente de IA pode ler um Swagger e configurar um teste de segurança, mas não é determinístico: varia entre execuções, pode errar e pode ser enganado por texto vindo da API testada. Incidentes públicos de 2026 mostram que instrução em prompt não basta para manter um agente dentro do escopo. Um prompt também não tem teste unitário.

## Decisão

Vamos separar dois planos.

- O **agente** (Claude Code) só age sobre o alvo chamando comandos `hdast`. Ele escreve arquivos de perfil e interpreta a saída dos comandos.
- A **CLI** `hdast` concentra toda regra, validação e trava, em código determinístico e testado.

O agente nunca fala HTTP com o alvo, nunca vê segredo e nunca decide escopo.

## Alternativas consideradas

- **Dar ao agente shell e `curl` livres.** Mais flexível, mas sem nenhuma garantia de escopo. Descartada.
- **Colocar a lógica nas skills em Markdown.** Rápido de começar, mas impossível de testar. Descartada.

## Consequências

- Mais código na CLI no início.
- Se o agente errar ou for enganado por uma resposta da API, o dano fica limitado ao que a CLI permite.
- Trocar de agente, ou rodar sem agente no CI, vira questão de configuração e não de reescrita.
- Skills ficam finas: se uma skill precisar de lógica, a lógica vira comando.
- Todos os demais ADRs dependem deste.
