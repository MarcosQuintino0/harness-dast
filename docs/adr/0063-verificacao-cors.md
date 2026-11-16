# 0063. Verificação CORS em leituras provadas

- **Status:** Proposto
- **Data:** 2026-11-15

## Decisão

O estágio `authz` testa CORS por padrão, com `--check cors` e `disabled_checks` como nas demais verificações. Repete GETs alcançados pelo `probe` com a mesma conta, pela cerca e pelo despachante existente, sujeitos a janela, prazo, taxa, interrupção e autorização. O cabeçalho `Origin` é uma origem HTTPS sob `.invalid`, gerada a partir do identificador da execução. Não há envio ao domínio dessa origem. `authz.cors_max_requests` limita o número de GETs: padrão 5, entre 0 e 10. O valor diferente do padrão integra a aprovação do perfil.

Cabeçalhos duplicados são combinados pelo cliente e não correspondem a uma origem válida. Apenas sucesso HTTP é conclusivo. A origem refletida exatamente e `Access-Control-Allow-Credentials: true` produz achado alto; `Access-Control-Allow-Origin: *` sem credenciais produz achado baixo. `*` com `true` não dá acesso com credenciais no navegador e não é tratado como essa falha. As demais respostas não geram achado. O resultado agrega uma ocorrência por classe de política e produto, com fingerprint independente da operação, preservando a primeira operação como evidência. A classificação é CWE-942, OWASP API8:2023 Security Misconfiguration. O achado exige triagem, pois seu impacto depende dos dados e do uso da API.

## Limites

Uma amostra pequena não prova a política de todas as operações, métodos ou origens. Não testa preflight, origens específicas de confiança nem explora conteúdo. Erros, recusas e ausência de respostas são inconclusivos. Não prova que o navegador tenha uma sessão ou que a resposta contenha dados sensíveis. As políticas podem variar por caminho; a agregação mostra apenas a primeira evidência de cada classe.
