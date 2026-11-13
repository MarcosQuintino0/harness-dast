# Variáveis de ambiente `HDAST_*`

Configuração da **ferramenta**, lida e validada na partida (camada "ferramenta" da [configuração em camadas](../architecture.md#configuração-em-camadas)). Segredos de produtos não entram aqui: o perfil usa `secret_ref` ([ADR 0009](../adr/0009-segredos-por-referencia.md)).

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `HDAST_ZAP_BASE_URL` | `http://127.0.0.1:8080` | URL base da API do ZAP |
| `HDAST_ZAP_API_KEY` | (sem valor) | Chave da API do ZAP, quando habilitada. Tratada como segredo: não aparece em log nem em mensagem de erro |
| `HDAST_ZAP_PROXY_URL` | (sem valor: usa `HDAST_ZAP_BASE_URL`) | Proxy do ZAP pelo qual o `probe` envia as operações. O ZAP serve API e proxy na mesma porta no lab |
| `HDAST_AUTH_PROXY_URL` | (sem valor: sai direto; com pilha gerenciada, `http://127.0.0.1:3128`) | Proxy da rota de login e token CSRF: o proxy de escopo, para que a senha nunca passe pelo ZAP e cada requisição de login seja conferida pelo ScopeGuard. Com `hdast stack up` o valor vem do estado; a variável de ambiente, se definida, vence |
| `HDAST_ZAP_CA_FILE` | (sem valor) | Certificado (PEM) da CA do ZAP, para alvos HTTPS pela rota do ZAP |
| `HDAST_RUNS_DIR` | `runs` | Pasta onde cada execução grava seus arquivos (`manifest.json`, `audit.jsonl`, `probe.json`). Fica fora do git |
| `HDAST_PRODUCTS_DIR` | `products` | Pasta com os perfis de produto. Perfis reais ficam fora deste repositório e são apontados por esta variável (P-01) |
| `HDAST_STATE_DIR` | `%LOCALAPPDATA%/hdast` (Windows) ou `~/.local/state/hdast` | Pasta do estado da pilha gerenciada (`stack.json` com a chave do ZAP e as senhas descartáveis do alvo, modo 0600; políticas e auditorias por pilha em `stacks/`). Fora do repositório e de `runs/` |
| `HDAST_SCOPE_POLICY_DIR` | (sem valor) | Pasta da política do proxy. O `stack up` define a dele; sem pilha gerenciada, `hdast stop` usa esta variável para achar onde criar o `KILL` |
| `HDAST_ZAP_HOST_PORT` / `HDAST_PROXY_HOST_PORT` | `8080` / `3128` | Portas em `127.0.0.1` do ZAP e do proxy de escopo (ponte `proxy-gateway`) no host; lidas pelo `stack up` e pelo compose |
| `HDAST_LOG_LEVEL` | `INFO` | Nível mínimo de log: `DEBUG`, `INFO`, `WARNING` ou `ERROR` |

`HDAST_ZAP_BASE_URL`, `HDAST_ZAP_PROXY_URL` e `HDAST_AUTH_PROXY_URL` só aceitam URL `http` ou `https` com host (`file://` e semelhantes são recusados). Valores inválidos fazem o comando falhar com `CONFIG_ERROR` (código de saída `2`). A mensagem cita o nome da variável, nunca o valor.

## Status

| Variável | Lida pelo código hoje? |
| --- | --- |
| Todas | Sim (settings da ferramenta). `preflight` e `probe` usam o ZAP, `runs/` e os proxies; `products/` é usada desde o M2 |

## Precedência com a pilha gerenciada

`HDAST_ZAP_BASE_URL`, `HDAST_ZAP_API_KEY` e `HDAST_AUTH_PROXY_URL` definidos no ambiente sempre vencem. O que não está definido é completado pelo `stack.json` gravado por `hdast stack up`. `HDAST_ZAP_PROXY_URL` segue o `HDAST_ZAP_BASE_URL` efetivo. As senhas descartáveis do alvo de laboratório (`PILOT_*_USERNAME`/`_PASSWORD`) também vêm do estado, mas só para os nomes que um `secret_ref: env:` do perfil cita e que o ambiente não define.

## Observações

- Use `.env.example` como modelo (lista todas as variáveis `HDAST_*`, sem valores reais). Nunca versione um `.env` com valores reais.
- Segredos de produtos (por exemplo `AGENDA_USER_A_SENHA`, citados em `secret_ref: env:...`) também são variáveis de ambiente, mas não têm o prefixo `HDAST_` e seus nomes são definidos por produto. Veja [target-yml.md](target-yml.md).
- Precedência: flag, depois ambiente, depois perfil. Escopo e limites só podem ser reduzidos por flag.
