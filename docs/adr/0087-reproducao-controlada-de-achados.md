# 0087. Reprodução controlada de achados

- **Status:** Proposto
- **Data:** 2026-11-16
- **Origem:** fase C da V1.11, `docs/plans/2026-11-17-v1-11-verificacao-de-achados.md`

## Contexto

A classificação offline do ADR 0085 não reproduz o efeito no alvo. Uma reprodução precisa de controles comparáveis e de autorização vigente, sem tratar uma resposta externa como instrução ou transformar severidade em decisão automática. O contrato do `verification.json` é aditivo e não altera `findings.json`, status ou severidade.

## Decisão

Vamos propor `hdast confirm <produto> --run <run_id> [--finding <fingerprint>] [--max N]`, que acrescenta resultados ao envelope da fase A e preserva entradas não selecionadas. O teto é de 30 achados por execução, com altos e médios primeiro, e 12 pedidos por achado, incluídas repetições. `--max` só reduz o teto. Logins e renovação de sessão devem ser contados separadamente e respeitar os limites globais existentes.

A seleção e as regras de comparação pertencem ao domínio; a aplicação coordena as portas; adaptadores traduzem artefatos; a CLI compõe. A confirmação só poderá usar sementes validadas de `exchanges.json`/`probe` vinculadas por método e operação a entradas de `scan.json` que comprovem varredura iniciada, em execução e produto coerentes, cujo outcome continue autorizado no perfil. Texto de ataque e URL de alerta recebidos do alvo nunca são reenviados. Perfil aprovado e pilha atual são rechecados, com exclusão mútua da pilha; todo envio passa por `OperationDispatcher`, `GuardedSender`, `RunGate`, `approve`/`ScopeGuard`, limitação de taxa, janela, prazo e parada existentes. Na dúvida, não há envio.

Vamos recusar `DELETE` sempre e demais métodos de escrita enquanto não houver prova da autorização exata daquela operação e passagem pelo diário de mutações existente. A recusa não cria permissão nem modifica o perfil. Sem oráculo benigno seguro para travessia de caminho, o resultado será `not_verifiable`.

As receitas são fixas, pequenas e acompanhadas de controle: SQL booleano com condições verdadeira e falsa; SQL por tempo com medições repetidas da variação natural; reflexão de marcador único não codificado em resposta HTML comparada a controle inofensivo; arquivo inofensivo conhecido comparado a nome inexistente para travessia; detalhe de erro repetido comparado à entrada válida. Cabeçalhos e CORS usam evidência guardada, sem novo tráfego. Achados `authz_*` só recebem `reproduced` quando uma comparação guardada válida sustenta o resultado.

Na primeira implementação, somente GET com um parâmetro de consulta inequívoco é repetido; a entrada do scan precisa ter identificador e ao menos um pedido contabilizado. Nenhuma escrita é repetida. SQL por tempo é limitado ao PostgreSQL; outros bancos não são cobertos. A travessia é `not_verifiable` porque não há contrato que forneça arquivo benigno e conteúdo esperado. Em autorização, a confirmação guardada se restringe às comparações horizontal e vertical com contas distintas e dois status de sucesso. Os demais casos permanecem sem confirmação. O resultado guarda apenas status e duração resumidos, sem corpo; a auditoria contabiliza sessão separadamente dos pedidos das receitas.

Resposta igual isoladamente não demonstra falso positivo de SQL; status igual não implica corpo igual, HTTP 500 não prova SQL e marcador refletido em HTML não prova execução JavaScript. Atraso exige repetição e separação da variação natural. Erro de rede, instabilidade ou orçamento insuficiente geram `inconclusive`, com motivo seguro e persistência parcial. Falha de escopo ou de pilha impede envio ao alvo. Nenhum erro externo bruto ou resposta integral é persistido; evidência limitada passa pela redação existente, incluindo segredos da execução.

## Alternativas consideradas

- Reenviar a URL ou carga do alerta: rejeitado porque são dados externos, podem ampliar o escopo e não garantem um controle.
- Declarar falso positivo quando respostas são iguais: rejeitado porque a receita pode ser inadequada ou a resposta pode mascarar diferenças.
- Permitir escrita pela existência de uma flag nova: rejeitado porque a autorização precisa derivar da carta e do perfil já aprovados, além do diário de mutações.
- Executar comandos ou ler arquivos sensíveis para obter prova: rejeitado; não é necessário para QA defensivo.

## Consequências e aceites verificáveis

A confirmação poderá ser inconclusiva mesmo diante de vulnerabilidade real. As receitas não fornecem probabilidades e exigem calibração no laboratório antes de qualquer taxa de acerto. Testes com cliente falso e artefatos reais temporários devem cobrir efeito, ausência de efeito, instabilidade, falhas e entradas inválidas, ausentes e malformadas; os contratos da CLI devem cobrir limites, escopo, parada, pilha desatualizada e produto divergente. O fechamento exige também prova dirigida no laboratório, fora do limite desta frente. Este ADR permanece proposto; os testes sem alvo real não substituem a prova dirigida no laboratório.

