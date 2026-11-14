# 0036. Carta de autorização estruturada (`carta.yml`) e `hdast init --from-letter`

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** revisão do consultor (Tema "uso seguro e fácil"), plano do ciclo V1.3 a V1.8. Completa o [ADR 0009](0009-segredos-por-referencia.md) (segredos só por nome) e a regra da parte B do `CLAUDE.md` (escopo, limites e autorização vêm da carta, nunca do agente)

## Contexto

Hoje a pessoa entrega a carta de autorização em texto livre e o agente de IA a lê e escreve à mão os blocos `scope`, `limits`, `scope.authorization`, `scope.windows` e `environment` do `target.yml`. A CLI impõe o perfil (cerca, limites, janela, validade), mas nada garante que o perfil é **fiel à carta**: um agente que lê errado, esquece um caminho proibido ou "ajuda" ampliando um método produz um perfil válido e mais largo que a autorização. A única defesa é a revisão humana do YAML, que é exatamente o que o fluxo tenta poupar.

Queremos que o agente nunca escreva esses blocos. Ele conduz a entrevista, transcreve as respostas da pessoa num arquivo de formato fechado e a CLI gera os blocos de forma determinística, recusando o que falta.

Restrições: falha fechada; só o que o perfil já suporta hoje; o padrão do perfil não muda; sem dependência nova; o formato cresce por adição.

## Decisão

Vamos:

1. **Artefato novo `carta.yml`** (`schema_version: 1`), uma transcrição estruturada da carta, na ordem da entrevista: `gates`, `environment`, `scope`, `authorization`, `limits`, `auth`, `attack`, `example_data`. Cada resposta é um objeto `{value, source, quote?}`:
   - `source`: `carta` (a carta assinada diz isso), `pessoa` (a pessoa respondeu na entrevista) ou `desconhecido` ("não sei" / "não está na carta"; sem `value`). Qualquer outro valor é erro de forma.
   - `quote`: frase de origem, opcional (até 300 caracteres), obrigatória só para `scope.path_mode: wide`.
   - Campo desconhecido, resposta sem `source`, valor solto no lugar da resposta e `schema_version` ausente ou diferente de 1 são recusados na leitura, com o caminho do campo e sem repetir o valor recebido.
2. **Campos (só o que o perfil suporta hoje) e mapa para o `target.yml`:**

   | Campo da carta | Obrig. | Vira no `target.yml` |
   | --- | --- | --- |
   | `product` (cabeçalho) | sim | `product`; precisa ser igual ao argumento de `hdast init` |
   | `gates.test_environment`, `gates.synthetic_data`, `gates.authorization_in_force` | sim, `true` | não vira campo: condição para gerar qualquer coisa |
   | `gates.product_owner` | sim | não vira campo; fica no `carta.yml` como registro de quem autorizou |
   | `environment.name`, `environment.base_url` | sim | `environment.name`, `environment.base_url` |
   | `environment.openapi` | sim | `openapi` |
   | `scope.allow` (lista de regras `host`, `scheme`, `port`, `allow_local`, `paths`, `methods`, validadas por `ScopeRule`) | sim | `scope.allow` |
   | `scope.deny_paths` (lista; vazia só se a pessoa respondeu "nenhum") | sim | `scope.deny_paths` |
   | `scope.path_mode` | não (padrão `strict`) | `scope.path_mode` (a CLI sempre escreve o valor); `wide` só com `source: carta` e `quote` |
   | `authorization.reference`, `authorization.valid_until` | sim | `scope.authorization.reference`, `.valid_until` |
   | `authorization.windows` (forma compacta) | sim | `scope.windows` |
   | `limits.requests_per_second`, `max_duration_minutes`, `zap_threads_per_host` | sim | `limits.*` |
   | `auth.type`, `auth.token_path` ou `auth.header_name` | sim | `auth.type`, `auth.token_path` ou `auth.header_name` |
   | `auth.login_options` | não | `auth.request_encoding`, `username_field`, `password_field`, `token_response_field`, `token_header`, `token_scheme` (ausentes mantêm o padrão do perfil) |
   | `auth.login_max_per_minute` | não | `auth.login_limit.max_per_minute` |
   | `auth.accounts` (`alias`, `role`, `secret_ref: env:NOME` ou `keyring:NOME`) | sim | `auth.accounts` |
   | `attack.strength` (`LOW`, `MEDIUM`, `HIGH`) | não | `scan.strength`; ausente: a CLI **não escreve** o bloco `scan` e vale o padrão atual do perfil (esta decisão não muda o padrão) |
   | `example_data` | não | **sem encaixe automático** (ver abaixo) |

3. **Comando.** `hdast init <produto> --from-letter <carta.yml>` lê a carta, confere e cria a pasta do produto como o `init` de hoje (modelo `products/_template`), trocando o `target.yml` do modelo pelo gerado. O `target.yml` gerado traz só `schema_version`, `product`, `environment`, `openapi`, `scope`, `limits`, `auth` e, se informada, `scan.strength`; `probe`, `cleanup`, `authz`, `auth.csrf`, `auth.account_map` e o restante continuam sendo trabalho posterior (do agente, da pessoa), nas etapas de alcançabilidade e limpeza. O comando nunca sobrescreve: produto existente é `CONFIG_ERROR` e nada é alterado (comportamento atual do `init`). `--with-cleanup` continua valendo.
4. **`--check`.** `hdast init <produto> --from-letter <carta.yml> --check` só confere: não cria pasta nem arquivo e não exige que o produto esteja livre. Com `--json`, o envelope traz `data.ready`, `data.check`, `data.generated_blocks`, `data.issues` (lista de `{field, code, message}`, uma entrada por campo) e `data.example_data`. `--check` sem `--from-letter` é erro de uso.
5. **Falha fechada.**
   - **Portões primeiro.** Ambiente de teste, dados sintéticos e autorização vigente precisam estar respondidos `true`; o dono do produto precisa estar preenchido. Resposta "não" (`GATE_DENIED`), desconhecida (`UNKNOWN`), ausente (`MISSING`) ou que não seja booleano (`INVALID_VALUE`) recusa **tudo**: nenhum outro campo é lido, e a lista traz só o(s) portão(ões).
   - **Campo obrigatório** ausente, nulo ou `desconhecido` é recusado (`MISSING`, `UNKNOWN`), com a mensagem de que a resposta vem da pessoa e não do agente.
   - **Valor-modelo** é recusado (`PLACEHOLDER`): domínios de exemplo (`exemplo.com.br`, `example.com`...), `SEC-0000`, `CHANGE_ME` e nomes de segredo `MEU_PRODUTO_*`. A lista é a mesma do `profile validate`, agora em `domain/placeholders.py` (uma fonte só).
   - **Valor inválido** (`INVALID_VALUE`): cada valor passa pelos MESMOS modelos do perfil (`ScopeRule`, `Scope`, `RunLimits`, `Authorization`, `ExecutionWindow`, `LoginAccount`, `ApiKeyAccount`, `LoginLimit`, `Environment`), com o caminho do campo na carta. A carta não tem regra própria que possa divergir do perfil.
   - **Segredo no lugar do nome**: `secret_ref` só aceita `env:NOME` ou `keyring:NOME`; um valor literal não passa e a mensagem nunca o repete (nem no envelope, nem no texto, nem no log).
   - **`path_mode: wide`** só passa com `source: carta` **e** `quote` não vazia (`WIDE_NEEDS_LETTER`). Ausente ou `desconhecido` vale `strict`.
   - **Produto da carta diferente do argumento**: `PRODUCT_MISMATCH`.
   - **Último teste**: com tudo certo, o perfil montado ainda passa por `ProductProfile.from_data`; recusa dele (base_url fora do escopo, login fora do escopo, apelido repetido...) vira `PROFILE_REJECTED`. O que o perfil recusa, a carta recusa.
   - Com qualquer pendência, nada é criado. O erro é `LetterRejected` (herda de `ConfigError`; código `LETTER_REJECTED`, saída 2, nenhum código novo de saída), e o envelope de falha ainda leva `data` com a lista de campos.
6. **Determinismo.** A geração não usa relógio nem ordem de chaves da carta: os blocos são montados em ordem fixa, valores canônicos vêm dos modelos do perfil (caminhos e métodos ordenados e sem repetição), e um escritor de YAML próprio (textos sempre entre aspas; sem `yaml.dump`) dá o mesmo texto byte a byte. Vigência da autorização e janela aberta **não** são conferidas aqui (dependem do relógio): continuam sendo do `profile validate` e do `preflight`.
7. **Dados de exemplo.** O `data-rules.yml` tem um encaixe natural para valores fixos (`generator: constant`, com `match` por `operation` e `field`), mas ele é escrito para o alcance das operações (`fix-reachability`), depende do OpenAPI e não é um bloco de proteção. Por isso `example_data` **não** gera `data-rules.yml`: fica no `carta.yml` e volta no envelope (`data.example_data`) como informação para o agente, que escreve as regras. Aceita-se uma lista de mapas `{operation?, field, value, note?}` só com valores JSON simples.
8. **Formato cresce por adição.** Campo novo é um `Answer` opcional numa seção existente (ou seção nova com padrão vazio); `schema_version` só sobe numa mudança incompatível. Versões seguintes acrescentarão, por exemplo, a permissão de teste de autorização com escrita.

## Fora desta decisão

- **Aprovação humana por hash** dos blocos gerados: ADR 0037, de outro trabalho, em cima deste formato.
- **Mudança do padrão da força** (`scan.strength`): outra versão (V1.7). Aqui a força é só opcional e, ausente, não muda nada.
- Conduzir a entrevista (perguntas, ordem, o que perguntar de novo): skills de `onboard-product` e `test-product`, depois deste formato.
- Campos que o perfil ainda não suporta (permissão de escrita no `authz`, `include_outcomes`...): entram por adição, nas versões que criarem o suporte no perfil.
- `cleanup`, `probe`, `auth.csrf`, `auth.account_map`, `authz`: não são gerados da carta.

## Alternativas consideradas

- **Continuar com a carta em texto livre e o agente escrevendo os blocos.** É o problema: a fidelidade depende de o agente ler certo. Descartada.
- **Carta em JSON Schema ou formulário web.** Dependência ou serviço novo, sem ganho sobre YAML estrito e modelos pydantic que já existem. Descartada.
- **Valores soltos no `carta.yml` (sem `source`).** Perde a origem de cada resposta, que é o que distingue "a carta diz" de "a pessoa disse" (e permite recusar `wide` sem carta). Descartada.
- **Preencher padrão quando falta resposta.** Contradiz a falha fechada: um padrão aqui seria uma decisão de escopo tomada pela CLI. Os únicos padrões são os do próprio perfil (`path_mode: strict`, sem bloco `scan`), que já eram o mais restrito.
- **Gerar o `data-rules.yml` dos dados de exemplo.** Mistura dado de alcance com bloco de proteção e dependeria do OpenAPI. Adiada para quando fizer sentido (ver item 7).
- **`--force` para sobrescrever perfil existente.** Mantém-se o comportamento do `init`: nunca sobrescreve. Quem quiser regenerar escolhe outro nome ou remove a pasta por conta própria.

## Consequências

- O agente deixa de escrever `environment`, `scope`, `limits` e `auth.accounts` (com `type` e caminho do login): essa parte do perfil é função pura da carta. O risco que sobra é o agente transcrever errado a resposta da pessoa; por isso cada resposta tem origem e frase, e a aprovação humana dos blocos gerados (ADR 0037) fecha o ciclo.
- O `target.yml` gerado é o ponto de partida: o agente ainda o completa nos blocos que não são de proteção (`probe`, `auth.csrf`, `auth.account_map`, `authz`, `cleanup`). O cabeçalho do arquivo gerado lista os blocos que vêm da carta e diz para não os editar à mão. Editar um bloco gerado não é bloqueado por esta decisão (o `target.yml` continua sendo um arquivo comum); detectar a edição é o que o ADR 0037 acrescenta.
- A interface `ProductScaffolder.scaffold` ganha o parâmetro opcional `target_text`, e nasce a porta `LetterReader` (fronteira com o sistema de arquivos, com dublê de teste). Contrato público novo: o formato do `carta.yml`, as opções `--from-letter` e `--check` e o envelope descrito acima.
- `profile_errors.to_config_error` ganha o parâmetro `subject` e a função `describe_problems`; as constantes de valor-modelo saem de `validate_profile` para `domain/placeholders.py`. Nenhuma mudança de comportamento no `profile validate`.
- Limites: a carta não prova que a pessoa respondeu de verdade; só impede que o agente deixe lacuna sem avisar e força cada resposta a declarar sua origem. Hosts de vários produtos com caminhos diferentes por host são suportados (uma regra por host), mas `deny_paths` é global, como no perfil. A vigência (`valid_until` já vencido) só é percebida no `profile validate`.
- Provado só por teste automatizado e no laboratório (Clínica Piloto); nenhum produto real.
