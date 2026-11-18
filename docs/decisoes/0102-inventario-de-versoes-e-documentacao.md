# 0102. Inventário: versões irmãs não documentadas e documentação exposta

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** F8 da V1.12 ([plano](../plans/2026-11-17-v1-12-mais-achados.md)); [ADR 0096](0096-bloco-attack-da-carta-liga-capacidades-v1-12.md) (`extra_checks.inventory`); [ADR 0100](0100-ssrf-guiado-pelo-contrato.md) (padrão de checagem própria da CLI)

## Contexto

Gestão imprópria de inventário (OWASP API9) é achar o que existe e ninguém documentou: uma versão antiga da API que segue no ar sem as correções da atual, ou a documentação (Swagger, OpenAPI) aberta a quem chama. O contrato do produto só lista o que o time quis documentar, então só o alvo responde. A chave `extra_checks.inventory` já existe (ADR 0096) e só a carta a liga.

## Decisão

Vamos acrescentar ao `scan`, **só com `extra_checks.inventory: true`**, um inventário de pedidos `GET`, depois das varreduras do ZAP e só se ela terminou normalmente. Cada pedido sai pelo mesmo caminho do `negative` e do SSRF guiado (`NegativeSender` sobre `OperationDispatcher` e `GuardedSender`; auditoria com o prefixo `inventory:`): cerca, `deny_paths`, métodos, taxa, janela, prazo, trava e diário. **Se a cerca não permite um caminho, ele não é enviado nem forçado**: vai para `skipped` com o motivo `not_verifiable_by_fence`. O planejamento fica em `domain/inventory_checks.py`.

**(a) Versões irmãs.** Para cada modelo de caminho do contrato com um segmento de versão `v<N>` (só o inteiro; `v4.0` não vale), a CLI troca o número por `N-1`, `N+1` e `N-2` (no máximo três, ao menos `v1`) e pula as versões que o contrato já documenta. Modelo com parâmetro de caminho usa o alvo concreto de um pedido do `probe` da mesma operação; sem ele, `needs_example`. Antes das irmãs, um **controle** (`v999`) mostra como o alvo responde a um caminho que não existe (resposta curinga de SPA, `401` geral de gateway). A irmã **existe** quando responde diferente do controle e não é `404` nem `410`; resposta igual à do controle é `inconclusive` (o alvo responde igual a qualquer caminho). Sem o controle permitido pela cerca, a família não é testada. Achado: severidade **baixa** se a irmã respondeu `2xx`, **informativa** nos demais códigos (`401`, `403`, `405`: a rota existe, protegida ou com outro método). CWE 1059; confiança média.

**(b) Documentação exposta.** Uma lista **pequena e fixa** de 16 caminhos (`/openapi.json`, `/openapi.yaml`, `/swagger.json`, `/swagger.yaml`, `/swagger`, `/swagger-ui`, `/swagger-ui.html`, `/swagger/index.html`, `/docs`, `/redoc`, `/api-docs`, `/v2/api-docs`, `/v3/api-docs`, `/api/openapi.json`, `/api/swagger.json`, `/api/docs`), relativos à URL base, que o contrato não documente. Só vale `200` com marca de documentação no começo do corpo (`"openapi"`, `"swagger"`, `swagger-ui`, `redoc`...): resposta curinga de SPA sem marca não conta. Achado: **baixo** se é a especificação, **informativo** se é só a interface. CWE 200; confiança alta.

**Teto rígido (domínio):** 40 pedidos por execução, no máximo 6 famílias de irmãs (cada uma com 1 controle e até 3 irmãs); o excedente vira `budget_exceeded`. Só `GET`. O corpo da resposta não é gravado. Os achados são alertas no formato do ZAP (`hdast-inventory-sibling` e `hdast-inventory-docs`) anexados ao fluxo normal, como nos ADR 0100 e 0101 (irmãs e documentação não têm operação no `probe`: viram achados `unresolved` do caminho). `scan.json` ganha `inventory` (teto, enviados, resultado por caminho, pulos, nota) com padrão nulo.

## Alternativas consideradas

- **Procurar versões por força bruta de caminhos.** Descartado: a lista é derivada do contrato e curta; descobrir rotas é o trabalho do ZAP (spider), que a carta pode usar à parte.
- **Contar qualquer resposta diferente de `404`.** Descartado: um alvo com `401` geral ou curinga de SPA gera falso positivo em tudo. O controle `v999` custa um pedido por família e resolve os dois.
- **Pedir a documentação sem a cerca.** Descartado sem discussão: o inventário nunca amplia o escopo; quem quiser ver a documentação inclui o caminho na carta.
- **Documentação em severidade média.** Descartado: em ambiente de teste a documentação costuma ser intencional; baixo e informativo pedem decisão do dono sem alarmar.

## Consequências

- Com o escopo da carta estrito (lista fechada de caminhos, como o `crapi-foco`), quase todo o inventário vira `not_verifiable_by_fence`. É o comportamento certo: o resumo mostra o que a cerca impediu, e a carta pode incluir os `GET` dos caminhos irmãos e da documentação para o inventário valer.
- Cada execução com a chave manda até 40 `GET` a mais; desligada, nenhum.
- Prova no laboratório (2026-11-17, `tests/integration/test_v112_rate_inventory.py`): crAPI (`2026-11-17T17-32-00Z-crapi-338a`), 21 pedidos: sem versão irmã (v1 e v4 de `check-otp` deram 404, igual ao controle) e sem documentação (as 16 rotas respondem 200 sem marca, a SPA do `crapi-web`: não conta); as irmãs de `posts/recent` ficaram `not_verifiable_by_fence`. Clínica Piloto no modo seguro (`2026-11-17T17-39-33Z-clinica-piloto-b907`): 1 achado baixo, `/v3/api-docs` exposto (já no escopo do perfil), 4 pedidos, o resto `not_verifiable_by_fence`. Sem as chaves, zero linhas `inventory:`.
- Falso negativo: versão irmã com formato fora de `v<N>` e documentação em caminho fora da lista; versão que responde igual ao controle (`inconclusive`). Falso positivo: gateway que responde diferente por motivo alheio à versão; por isso a confiança é média e a severidade é baixa.
