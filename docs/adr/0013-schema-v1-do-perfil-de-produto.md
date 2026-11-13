# 0013. Schema v1 do perfil de produto

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** Achados A-01, A-02, A-07, A-11 e A-13 da [revisão de QA](../reviews/2026-11-13-qa-m1-m2.md); detalha o [ADR 0005](0005-perfil-de-produto-versionado.md)

## Contexto

O [ADR 0005](0005-perfil-de-produto-versionado.md) diz que o formato do perfil "pode evoluir até o fim do M2". A primeira metade do M2 (domínio) implementou o schema como modelos pydantic. A implementação acrescentou campos que a ilustração do documento de fundação não tinha, fixou tetos de carga e definiu regras de normalização de URL. Mudança de schema é mudança de contrato e exige ADR. A referência campo a campo está em [../reference/target-yml.md](../reference/target-yml.md); este ADR registra a decisão e o porquê.

## Decisão

Vamos fixar o schema v1 do `target.yml` como implementado em `domain/profile.py`, `scope.py`, `auth.py`, `window.py`, `run.py` e `secret_ref.py`.

### Forma

Raiz com `schema_version` (sempre `1`), `product`, `environment`, `openapi`, `scope`, `limits`, `auth` e, opcional, `cleanup`. Todo bloco é imutável e **rejeita campo desconhecido**. Erros saem em português, por caminho de campo, **sem repetir o valor recebido** (um segredo digitado no lugar errado nunca vira texto de erro).

### Campos acrescentados além da ilustração do desenho

| Campo | Onde | Por quê |
| --- | --- | --- |
| `scheme` (padrão `https`) | regra de `scope.allow` | O lab usa `http`. `http` precisa ser escrito de propósito |
| `port` (padrão: a do esquema) | regra de `scope.allow` | Porta diferente da padrão só passa se declarada; evita liberar todas as portas de um host |
| `allow_local` (padrão `false`) | regra de `scope.allow` | O lab roda em `localhost`, IP privado ou nome de contêiner (`vampi`), o caminho clássico de SSRF contra a rede interna. Exige declaração explícita, só vale para host local e é erro em host público |
| `request_encoding`, `username_field`, `password_field`, `token_response_field`, `token_header`, `token_scheme` | `auth` do tipo `login_password` | APIs de login diferem em corpo (formulário ou JSON), nomes de campo e local do token. Têm padrões razoáveis (`form`, `username`, `password`, `access_token`, `Authorization`, `Bearer`) |
| `header_name` | `auth` do tipo `api_key` | Nome do cabeçalho que leva a chave |
| `authorization.reference`, `authorization.valid_until` | `scope` | Autorização formal registrada e sua validade |

### Nome `login_password`

O tipo de autenticação com usuário e senha que devolve token chamava-se `oauth2_password` na ilustração. Passa a se chamar **`login_password`**. O nome antigo sugere conformidade com o fluxo OAuth2 "resource owner password", que é só um dos formatos possíveis. O tipo cobre qualquer endpoint de login que receba usuário e senha e devolva um token, e o perfil descreve o formato (`request_encoding`, campos e caminho do token). O tipo de chave fixa continua `api_key`. Não há perfil publicado, então não há migração.

### Normalização falha fechada

O `ScopeGuard` decide sobre a forma canônica e recusa qualquer ambiguidade em vez de adivinhá-la (detalhes em [../reference/target-yml.md](../reference/target-yml.md#o-que-o-scopeguard-recusa)). Regra de segurança acrescentada pelo achado A-01: **recusa-se todo segmento de caminho que contenha `;`, que termine em ponto ou espaço ou que comece por espaço**, em forma crua ou codificada. Motivo: Tomcat/Spring e IIS removem `;x=1` e aparam ponto e espaço finais antes de rotear, de modo que `/admin;x=1`, `/admin.` e `/admin%20` chegariam à rota `/admin` e contornariam `deny_paths: /admin`. A alternativa de comparar uma forma "limpa" só na negação foi descartada: exigiria adivinhar a reescrita de cada servidor, e recusar a forma é mais simples e mais seguro. O custo é recusar caminhos legítimos com esses caracteres, aceitável numa ferramenta de teste autorizado.

Outras regras de validação do perfil:

- `valid_until` aceita apenas data `AAAA-MM-DD` (inclusiva, contada em UTC). Data com hora e timestamp são recusados, porque o fuso seria ambíguo.
- Janela com início igual ao fim é sempre recusada, também na forma estruturada (achado A-07): ela seria lida como "o dia todo" e ampliaria a janela autorizada.
- `requires_confirmation` da limpeza só aceita `true`.
- Segredo só como `env:NOME`; valor literal não casa.
- A `base_url` do ambiente e o `POST` de login precisam estar cobertos por `scope.allow`.

### Tetos absolutos de carga

| Limite | Teto | Motivo |
| --- | --- | --- |
| `requests_per_second` | 50 | Acima disso a varredura vira teste de carga contra ambiente compartilhado; o padrão do ZAP é sem limite |
| `max_duration_minutes` | 480 (8 h) | Cabe numa janela noturna típica sem deixar execução aberta |
| `zap_threads_per_host` | 8 | Limita a concorrência contra o mesmo host |

Os valores são escolhas iniciais, a calibrar com o piloto (M7). O teto vale para o perfil **e** para as sobrescritas de linha de comando. Valor acima do teto é erro de validação, nunca é reduzido em silêncio. Sobrescritas só reduzem (`domain/overrides.py`).

## Alternativas consideradas

- **Manter `oauth2_password`.** Menos mudança, mas o nome promete um protocolo que o tipo não implementa. Descartada.
- **Aceitar `valid_until` com hora.** Mais flexível, mas ambíguo. Descartada.
- **Liberar `allow_local` por padrão no lab.** Menos fricção, mas abre o caminho de SSRF por descuido. Descartada.
- **Deixar os limites sem teto e confiar no perfil.** Contraria a falha fechada. Descartada.

## Consequências

- O schema é contrato público. Só evolui por adição, com `schema_version` nova e ADR quando houver quebra.
- Um teste valida o `products/_template/target.yml` contra o modelo, para o template não divergir de novo (achado A-02).
- Os tetos podem ser revistos no M7; mudar um teto é mudança de contrato e pede ADR novo.
- O carregador de YAML e o comando `hdast profile validate` ainda não existem. Dependência: [ADR 0012](0012-dependencias-tzdata-e-pyyaml.md).
- As limitações da normalização (sem DNS, `%` literal, cabeçalhos e corpo não conferidos, caminhos de IIS) estão em [../reference/target-yml.md](../reference/target-yml.md#limitações-conhecidas).
