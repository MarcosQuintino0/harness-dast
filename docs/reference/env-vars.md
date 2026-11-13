# Variáveis de ambiente `HDAST_*`

Configuração da **ferramenta**, lida e validada na partida (camada "ferramenta" da [configuração em camadas](../architecture.md#configuração-em-camadas)). Segredos de produtos não entram aqui: o perfil usa `secret_ref` ([ADR 0009](../adr/0009-segredos-por-referencia.md)).

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `HDAST_ZAP_BASE_URL` | `http://127.0.0.1:8080` | URL base da API do ZAP |
| `HDAST_ZAP_API_KEY` | (sem valor) | Chave da API do ZAP, quando habilitada. Tratada como segredo: não aparece em log nem em mensagem de erro |
| `HDAST_RUNS_DIR` | `runs` | Pasta onde cada execução grava seus arquivos. Fica fora do git |
| `HDAST_PRODUCTS_DIR` | `products` | Pasta com os perfis de produto. Perfis reais ficam fora deste repositório e são apontados por esta variável (P-01) |
| `HDAST_LOG_LEVEL` | `INFO` | Nível mínimo de log: `DEBUG`, `INFO`, `WARNING` ou `ERROR` |

`HDAST_ZAP_BASE_URL` só aceita URL `http` ou `https` com host (`file://` e semelhantes são recusados). Valores inválidos fazem o comando falhar com `CONFIG_ERROR` (código de saída `2`). A mensagem cita o nome da variável, nunca o valor.

## Status

| Variável | Lida pelo código hoje? |
| --- | --- |
| Todas as cinco | Sim (settings da ferramenta, M1) |

O ZAP, `runs/` e `products/` ainda não são usados por nenhum comando; as variáveis existem para os marcos M2 em diante.

## Observações

- Use `.env.example` como modelo (lista todas as variáveis `HDAST_*`, sem valores reais). Nunca versione um `.env` com valores reais.
- Segredos de produtos (por exemplo `AGENDA_USER_A_SENHA`, citados em `secret_ref: env:...`) também são variáveis de ambiente, mas não têm o prefixo `HDAST_` e seus nomes são definidos por produto. Veja [target-yml.md](target-yml.md).
- Precedência: flag, depois ambiente, depois perfil. Escopo e limites só podem ser reduzidos por flag.
