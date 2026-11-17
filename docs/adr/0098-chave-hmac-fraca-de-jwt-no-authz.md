# 0098. Chave HMAC fraca de JWT no `authz`

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** V1.12, passo F4 (`docs/plans/2026-11-17-v1-12-mais-achados.md`); relaciona-se ao [ADR 0039](0039-pedido-sem-login-e-token-adulterado.md) e ao [ADR 0096](0096-bloco-attack-da-carta-liga-capacidades-v1-12.md)

## Contexto

O teste "token adulterado" do ADR 0039 já tenta `alg: none`, assinatura retirada e uma reivindicação a mais, mas por regra nunca assina nada nem tenta chave. Um servidor que confere a assinatura e assina com uma chave HMAC fraca (`secret`, o nome do produto) passa nesse teste, embora qualquer pessoa possa forjar uma credencial. É o desafio C15 do crAPI (JWT: `alg` none, chave fraca, `kid`/`jku`) e um item do OWASP API2.

## Decisão

Vamos estender o `tampered_token`, sem chave nova na carta, porque ele já só vale quando o `authz` está autorizado, só lê (`GET` aprovado no escopo) e só usa a conta de teste da carta:

1. **Quebra offline.** Se o token da conta dona é JWT com `alg` `HS256`, `HS384` ou `HS512`, o domínio testa a assinatura contra uma lista fixa e versionada (`WEAK_HMAC_KEYS`, versão 1, cerca de 50 palavras) mais, no máximo, 5 palavras do contexto (hoje só o nome do produto do perfil). Nenhum pedido ao alvo.
2. **Prova.** Achada a chave, e só se nenhuma variante comum foi aceita naquela operação, vai um pedido com o token re-assinado que só acrescenta a reivindicação inofensiva `hdast` (variante `weak_key`). Se aceito, vai um segundo com `exp` no passado (`weak_key_expired`: o servidor aceita token vencido). `sub`, papel e demais reivindicações nunca mudam.
3. **Teto, decidido em `domain/authz/jwt_forge.py`:** até 2 pedidos de prova por operação e até 10 operações por execução (no máximo 20 pedidos); o teto geral de 100 operações do `tampered_token` continua. A quebra roda uma vez por conta.
4. **Achado.** Mesma técnica (`authz_tampered_token`), severidade **alta** e CWE-347, como os demais achados de autenticação por token. `variants` ganha `weak_key` e `weak_key_expired`; a evidência diz que a chave está na lista fixa, sem citá-la. O texto da chave e dos tokens re-assinados é registrado no cofre de máscara antes de qualquer pedido e nunca é gravado.
5. **Fora do escopo.** `kid`, `jku`, `jwk` e confusão de algoritmo dependem de servidor externo ou de chave pública do alvo e não foram implementados. O `exp` vencido só é tentado depois de a chave ser achada, porque com a assinatura original o `exp` não pode ser alterado.

Esta decisão revoga apenas a frase do ADR 0039 que proíbe "tentar chave conhecida" no JWT; o resto do 0039 continua valendo.

## Alternativas consideradas

- **Chave nova na carta (`attack.jwt`).** Descartada: o teste não amplia escopo, métodos nem janela; apenas assina um token da própria conta, e só em `GET`. Se a pessoa dona do produto quiser desligá-lo, pode tirar o `tampered_token` de `authz.checks`.
- **Dicionário grande (rockyou etc.) offline.** Descartado: dependência e tempo sem ganho; a lista pequena cobre os casos de laboratório e de má configuração óbvia.
- **Tentar cada chave no alvo.** Descartado: seria força bruta contra o produto.
- **`kid`/`jku`.** Descartado agora (ver acima).

## Consequências

- O achado de chave fraca aparece junto dos de token adulterado, na mesma seção e na mesma impressão digital (técnica, método, caminho), sem alterar achados existentes.
- No pior caso o teste acrescenta 20 pedidos por execução; num JWT forte ou fora de HMAC, zero.
- A lista é fixa: chave fraca fora dela não é achada, e o relatório não afirma que a chave é forte.
- Palavras do contexto vêm do perfil, nunca de resposta do alvo.
