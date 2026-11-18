# 0021. Esquema aditivo do perfil para o alvo piloto: vários níveis, conta por operação, orçamento de login, token vencido e códigos de erro

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** Verificação do `probe` contra a Clínica Piloto real (`lab/pilot/product-profile/NOTES.md`); substitui a seção 4 do [ADR 0016](0016-leitor-de-openapi-proprio-e-esquema-de-unicidade.md) e a limitação de um nível do [ADR 0006](0006-regras-de-dados-declarativas.md) (pendência P-12); detalha o [ADR 0018](0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md)
- **Nota de aceitação (2026-11-13):** aceito depois da implementação e da verificação no laboratório (ZAP 2.17 real, proxy de escopo real, VAmPI e Clínica Piloto); veja docs/reviews/2026-11-13-e2e-lab.md. O dono do projeto aprovou o desenho e pediu a conclusão do trabalho.

## Contexto

O `probe` foi escrito para o VAmPI e para alvos simulados. A Clínica Piloto (Spring Boot, JWT, XSRF, regras de validação,
unicidade e limite de login) mostrou o que o schema v1 não expressava: o encadeamento convênio, paciente, consulta e receita
tem três elos e a regra "produtor ou consumidor" o recusava; criar convênio exige admin e criar paciente exige médico, mas o
`probe` enviava tudo com a primeira conta; o alvo aceita 5 logins por minuto e conta os que falham, então um `preflight` com
quatro contas e um `probe` que renova o token travam as contas; o corpo de erro tem um `code` que classifica melhor que o status;
e nenhum gerador produz um CRM único no formato `NNNNN-UF`. Tudo isso é opcional e aditivo: o schema do perfil continua na
versão 1 e os perfis que já existem seguem válidos.

## Decisão

Vamos:

1. **Encadeamento como grafo sem ciclos.** `flows.yml` aceita uma operação que consome de uma e produz para outra. Ciclo e
   auto-referência continuam recusados, com o caminho na mensagem; a cadeia mais funda que `MAX_FLOW_DEPTH` (6 operações, constante
   nomeada em `domain/flow.py`) é recusada. O `--only` traz os produtores em qualquer nível (fecho transitivo) e uma falha no meio
   propaga `skipped_dependency` aos elos seguintes.
2. **Conta por operação.** `auth.default_account` e `auth.account_map` (regras por `operationId` e/ou padrão de caminho com
   métodos; a primeira que casa vence) escolhem a conta de cada operação. Só apelidos: o perfil é recusado se citar uma conta
   que não existe, o `probe` recusa um `operationId` inexistente e `--account` impõe uma conta a todas as operações (só reduz).
   `spec inspect` informa `operation_accounts`. O `probe` abre uma sessão por conta usada, uma vez, na partida.
3. **Orçamento de login.** `auth.login_limit.max_per_minute` vira uma janela deslizante de 60 s consultada antes de TODO POST
   de login (primeiro login, novo login por vencimento, repetição após 429, operação de login do OpenAPI). Cheia, ela espera
   (relógio e espera injetados); não falha. Cada conta faz um login por execução; um cache de tokens por processo
   (`NetworkHandle.token_cache`) evita o segundo login quando `preflight` e `probe` rodam no mesmo processo.
4. **Token vencido.** `auth.token_expired {field, value}` declara o sinal; só um 401 com ele refaz o login, no máximo uma vez
   por requisição, e o novo login gasta do orçamento. Sem o bloco, todo 401 o refaz (comportamento anterior).
5. **Códigos de erro.** `probe.error_codes {field, outcomes}` mapeia o código do corpo para classes de resultado; vale para
   respostas 4xx e 5xx, decide também se um 403 é de CSRF e, ausente ou desconhecido o código, cai na heurística por status. O
   trecho do alvo (`untrusted_target_data.excerpt`) mantém `errors[].field` e `rule` dentro do teto de 300 caracteres.
6. **Gerador `br.crm`** (`digits` de 4 a 8, padrão 7; `uf`, padrão `SP`), com a mesma unicidade dos geradores numéricos.
7. **Binds do script de limpeza** documentados em [reference/cleanup.md](../referencia/cleanup.md) (`:run_start`, `:run_id`,
   `:run_tag`, `:account_1` a `:account_N`), alinhados ao `domain/cleanup_binds.py` e ao ADR 0020; o modelo de produto e o piloto
   passam a usar esses nomes.

Medições que motivaram dois ajustes de transporte (não mudam o schema): o ZAP real fecha a conexão, em vez de devolver
`bad_api_key`, quando a chave está ausente ou errada, e o cliente HTTP deixa de reaproveitar conexões, porque contra o Spring
Boot atrás do ZAP e do proxy de escopo a terceira requisição numa conexão persistente ficava pendurada até o tempo limite.

## Alternativas consideradas

- **Mapa papel -> operações no perfil** em vez de `account_map`: exigiria que o perfil conhecesse os papéis do produto; a regra por
  operação e caminho é mais direta e o agente já conhece os `operationId`.
- **Orçamento de login compartilhado entre processos** (arquivo de estado): evitaria o 429 do `probe` logo após o `preflight`, mas
  é estado global escondido e duplica o que o `Retry-After` já resolve. Fica para quando existir `hdast run`.
- **Pedir `code` fixo (`code` no corpo)** em vez de `error_codes.field`: alvos reais usam `error.code`, `errorCode`, `type`.
- **Subir `schema_version` para 2**: desnecessário, todos os campos são opcionais e nenhum muda o sentido de um campo existente.

## Consequências

- O `probe` mede a cadeia inteira do piloto e a alcançabilidade por conta; o preço é mais logins (um por conta usada) e esperas
  pelo orçamento: `preflight` seguido de `probe` num alvo com 5 logins por minuto leva cerca de um minuto a mais.
- O código de erro declarado torna a classificação exata, mas confia no campo do alvo (dado não confiável): só escolhe entre
  classes já existentes e nunca muda severidade nem escopo.
- A operação de login do OpenAPI continua no plano e, com credenciais geradas, o alvo a recusa (`auth_error`); ela é contada à
  parte nos testes de integração.
- Os ADRs 0006 e 0016 mantêm o texto original (imutáveis); este ADR é a referência para o encadeamento em vários níveis.
