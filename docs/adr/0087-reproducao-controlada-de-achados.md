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

Na implementação, somente GET com um parâmetro de consulta inequívoco é repetido; a entrada do scan precisa ter identificador, ao menos um pedido e recibo da URL e conta efetivamente varridas ([ADR 0090](0090-vinculo-semente-confirmacao.md)). Execuções antigas sem recibo não geram tráfego. Nenhuma escrita é repetida. SQL por tempo é limitado ao PostgreSQL; outros bancos não são cobertos. A travessia é `not_verifiable` porque não há contrato que forneça arquivo benigno e conteúdo esperado. Comparações de autorização são avaliadas por técnica e suficiência da prova guardada, incluindo leitura posterior quando necessária; cabeçalhos usam observação direta ([ADR 0091](0091-observacoes-passivas-de-confirmacao.md)). A prova separa ataque e controle por método, receita, digest do alvo, status, tempo, tamanho e digest curto do corpo, sem conteúdo integral. A auditoria distingue sessão e receita; ambas consomem o teto total de doze por achado.

Resposta igual isoladamente não demonstra falso positivo de SQL; status igual não implica corpo igual, HTTP 500 não prova SQL e marcador refletido em HTML não prova execução JavaScript. Atraso exige repetição e separação da variação natural. Erro de rede, instabilidade ou orçamento insuficiente geram `inconclusive`, com motivo seguro e persistência parcial. Falha de escopo ou de pilha impede envio ao alvo. Nenhum erro externo bruto ou resposta integral é persistido; evidência limitada passa pela redação existente, incluindo segredos da execução.

## Alternativas consideradas

- Reenviar a URL ou carga do alerta: rejeitado porque são dados externos, podem ampliar o escopo e não garantem um controle.
- Declarar falso positivo quando respostas são iguais: rejeitado porque a receita pode ser inadequada ou a resposta pode mascarar diferenças.
- Permitir escrita pela existência de uma flag nova: rejeitado porque a autorização precisa derivar da carta e do perfil já aprovados, além do diário de mutações.
- Executar comandos ou ler arquivos sensíveis para obter prova: rejeitado; não é necessário para QA defensivo.

## Consequências e aceites verificáveis

A confirmação pode ser inconclusiva mesmo diante de vulnerabilidade real. As receitas e observações guardadas têm os limites acima e não fornecem probabilidades; qualquer taxa exige calibração no laboratório. Testes com cliente falso e artefatos temporários cobrem efeito, ausência de efeito, instabilidade, falhas, entradas inválidas, ausentes e malformadas, limites, escopo, parada, pilha desatualizada e produto divergente. Não substituem prova dirigida no laboratório, ainda pendente. Este ADR permanece proposto.
