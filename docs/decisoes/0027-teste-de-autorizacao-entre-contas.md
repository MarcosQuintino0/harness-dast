# 0027. Teste de autorização entre contas: comando `authz`, estágio opcional do `run` e artefatos novos

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** lacuna medida na avaliação cega da Clínica Piloto (falhas H5, H6 e H7 do [gabarito](../../evals/answer-keys/clinica-piloto.md), que o ZAP não detecta por construção); estende os ADRs [0007](0007-zap-alimentado-por-requisicoes-validas.md), [0018](0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md) e [0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md) sem alterá-los

## Contexto

O ZAP varre uma requisição por vez, com uma identidade só. Ele não sabe de quem é um recurso, não compara respostas de contas diferentes e não conhece o esquema de resposta do produto. Por isso falhas de regra de negócio passam em branco: paciente A lendo a consulta do paciente B (BOLA/IDOR), `PUT /api/me` aceitando `role` (atribuição em massa) e listagem que devolve `senhaHash` e `notasInternas` (exposição excessiva de dados). O perfil já tem contas com papel e o `account_map`; o `probe` já faz login por conta, encadeia operações e prova quais requisições funcionam. Falta usar isso para comparar contas.

O que o `probe` grava hoje não basta: `probe.json` guarda só o modelo de caminho (nunca a URL concreta com o id) e `audit.jsonl` guarda só o caminho e os NOMES dos parâmetros de consulta. Para repetir "o mesmo pedido" com outra conta é preciso lembrar o pedido.

## Decisão

Vamos criar um estágio novo, **determinístico e sem ZAP**, que repete pedidos que o `probe` já provou funcionar. Ele é exposto de duas formas:

1. **Comando `hdast authz PRODUTO --run RUN_ID`** (flags: `--check` repetível para escolher verificações e `--dry-run` para só listar o plano; as contas vêm do perfil, nunca de uma flag). Grava `authz.json` na pasta da execução do `probe`.
2. **Estágio `authz` do `hdast run`, opcional e desligado por padrão** (`--authz`). Roda depois do `scan` e antes do `report`. Depois do `scan` porque as requisições do estágio saem pelo proxy do ZAP e não devem entrar no que o `scan` aprende; antes do `report` para entrar em `findings.json`. `run.json` passa a ter cinco estágios (`authz` fica `skipped` quando não pedido). Com `--skip-scan` o estágio também é pulado.

**Escolhemos comando e estágio, e não só um dos dois,** porque o laço de trabalho do agente é "ajusto o perfil e repito só isto" (comando solto), enquanto a rodada completa quer um único comando e um único relatório (estágio). Ambos chamam o mesmo caso de uso.

**O `probe` passa a gravar `exchanges.json`** (artefato novo, lido só pelo `authz`): para cada operação com sucesso, o método, o modelo de caminho, o alvo concreto relativo à `base_url` (caminho e consulta), a conta que enviou, o status e, só para `POST`, `PUT` e `PATCH` com corpo JSON, o corpo enviado. Nada disso é segredo: são dados sintéticos gerados pela própria ferramenta. Mesmo assim, o registro é descartado se o valor de algum segredo registrado aparecer nele, e campos de corpo com nome de segredo (senha, token, hash...) são removidos e listados em `omitted_fields`. O valor das respostas nunca é gravado. `probe.json` e `audit.jsonl` não mudam de formato.

**Bloco novo e opcional `authz` no `target.yml`** (aditivo na `schema_version` 1, como o ADR 0021): `public_operations` (operações legitimamente públicas ou compartilhadas, ignoradas por BOLA e BFLA), `role_order` (papéis do menor ao maior, necessário para BFLA), `volatile_fields` (nomes de campo ignorados na comparação, além de uma lista padrão de data e id de requisição), `vertical_methods` (métodos repetidos em BFLA; padrão `GET`, `HEAD`; nunca `DELETE`) e `mass_assignment_fields` (campos extras e valor de teste; padrão conservador `role`, `papel`, `admin`, `isAdmin`). Sem o bloco, valem os padrões.

**As quatro verificações** (cada uma é uma função pura de decisão em `domain` mais um laço de envio em `application`):

1. **Horizontal (BOLA).** Para cada `GET` com sucesso cujo caminho tem identificador, reenvia o pedido com a conta dona (linha de base) e com outra conta do MESMO papel. `2xx` com corpo equivalente (depois de tirar campos voláteis) é achado de severidade **alta**. `401`, `403`, `404` e demais `4xx` são o resultado esperado. `2xx` com corpo diferente não é achado (o recurso responde por quem pergunta). Sem conta do mesmo papel, a operação vai para `not_tested` com o motivo, nunca para "sem achado".
2. **Dado a mais.** Compara os campos da resposta de cada `GET` com sucesso com o esquema de resposta do OpenAPI. Campo fora do esquema é achado de severidade **média**, que sobe para **alta** quando o NOME indica segredo (senha, hash, token...) ou dado pessoal (cpf, e-mail...). A lista é fixa, no domínio, com teste. Só o nome e o caminho do campo vão para os artefatos, nunca o valor.
3. **Vertical (BFLA).** Para operações que uma regra explícita do `account_map` atribui a um papel maior, reenvia com uma conta de cada papel menor (segundo `role_order`). `2xx` é achado de severidade **alta**. Operações atendidas só pela `default_account` não entram: a atribuição não foi uma decisão declarada.
4. **Campo a mais (atribuição em massa).** Para `PUT` e `PATCH` com corpo JSON provado pelo `probe`, envia o mesmo corpo mais UM campo extra da lista declarada, por pedido, e confere numa leitura seguinte (um `GET` do mesmo caminho com a mesma conta, ou a própria resposta) se algum campo passou a ter o valor injetado. Cobre o caso em que o nome muda (`role` entra, `papel` muda). Se o valor mudou, tenta restaurar o valor anterior e registra se conseguiu. Achado de severidade **alta**. Nunca `DELETE`.

**Regras de segurança, todas em código:** todo pedido sai pelo mesmo caminho do `probe` (`OperationDispatcher` sobre `GuardedSender`: `ScopeGuard`, `deny_paths`, métodos do escopo, taxa, janela, prazo, trava de emergência, auditoria e orçamento de login). O estágio só repete pedidos gravados em `exchanges.json`: não inventa caminho, não troca método e não adivinha identificador. A severidade e a equivalência de resposta são decididas em `domain` (puro). O agente não altera a severidade. Contas só por apelido.

**Saídas.** `authz.json` (resultado completo: verificações com contagens e motivo de cada `not_tested`, achados). `findings.json` ganha, de forma aditiva, a seção `authz` (o mesmo conteúdo do `authz.json`), `summary.authz_by_severity`, e cada achado do ZAP ganha `technique: "zap_active_scan"`. Os achados de autorização ficam em lista própria, com `technique` (`authz_horizontal`, `authz_vertical`, `authz_excessive_data`, `authz_mass_assignment`), `origin: "authz"` e id `A-<8 hex>`; não se misturam aos do ZAP. O relatório Markdown ganha uma seção própria que diz a técnica de cada achado. O limiar `--fail-on` conta os dois tipos de achado. `NOT_TESTED_STATEMENTS` passa a dizer o que o estágio cobriu quando ele rodou.

**Código de saída do comando:** o mesmo mapeamento do `probe` para paradas (escopo 3, ferramenta externa 5, alvo 6). Achado de autorização NÃO muda o código do comando `authz` (é dado, como no `probe`); o `report` é o dono do código 1.

## Alternativas consideradas

- **Só estágio do `run`.** Obriga a rodar o `scan` (12 a 30 minutos) para testar uma regra de autorização. Descartada.
- **Só comando solto.** O relatório único e o `run.json` ficariam sem a técnica. Descartada.
- **Reconstruir os pedidos a partir do OpenAPI, das regras e da semente.** Dependeria de reproduzir o encadeamento e os valores do `probe`, e o id do recurso muda a cada execução. Descartada em favor de gravar o alvo concreto.
- **Gravar o corpo das respostas do `probe` para comparar depois.** Guardaria dado do alvo (por exemplo, `senhaHash`) em disco. Descartada: o estágio reenvia a linha de base com a conta dona e compara em memória, e só grava o veredito.
- **Misturar os achados na lista do ZAP com campos opcionais.** O modelo do achado é do ZAP (regra, alerta, evidência de requisição). Lista própria é mais honesta e deixa o `--compare` e a triagem do ZAP intactos.
- **Inferir a hierarquia de papéis.** Seria adivinhar. `role_order` é declarado; sem ele a verificação 3 diz que não pôde testar.
- **Mandar todos os campos extras num só pedido.** Um alvo que rejeita campo desconhecido derrubaria o teste inteiro. Um campo por pedido custa mais requisições e dá resultado claro.

## Consequências

- Passa a existir cobertura determinística de BOLA, BFLA, atribuição em massa e exposição excessiva, dentro do escopo e dos limites do perfil. Cada pedido repetido é uma requisição a mais (linha de base mais repetição), contada no ritmo, no prazo e no orçamento de login.
- O estágio **escreve** no alvo na verificação 4 (e na 3, se o perfil liberar escritas em `vertical_methods`): são operações que o escopo e o `probe` já autorizavam. A restauração é de melhor esforço; o `cleanup` e o reset do ambiente seguem sendo a garantia.
- Limites conhecidos, declarados no relatório: BOLA só em leituras (`GET`) com identificador no caminho; BFLA só nos métodos liberados; exposição excessiva só em respostas de `GET`; `additionalProperties` do OpenAPI não é modelado (um objeto livre não gera achado); a comparação de achados entre execuções (`--compare`) e a triagem não cobrem os achados de autorização; o `report` ainda exige `scan.json`.
- `run.json` muda (cinco estágios) e `findings.json` e `probe`-artefatos ganham campos aditivos; o contrato de teste e a documentação de referência acompanham.
- Quem editar `StageName` ou o `ProbeResult` precisa lembrar do estágio novo.
