# Medições de rodadas cegas

Resumos pequenos de rodadas de laboratório, guardados para comparar versões do `hdast` (tempo e tokens por etapa, número de `probe`, nota). Cada pasta é `<AAAA-MM-DD>-<caso>-<rótulo>/`. Quando duas rodadas do mesmo caso caem no mesmo dia, o rótulo leva um sufixo (`v1-0-r1`, `v1-0-r2`).

Como gravar (no repositório original, com a rodada em `<out>`):

```powershell
uv run python -m evals.runner measure --out <out> --save v1-2
uv run python -m evals.runner compare evals\measurements\<pastaA> evals\measurements\<pastaB>
```

## O que entra

| Arquivo | Conteúdo |
| --- | --- |
| `agent-metrics.json` | Tempo, tokens, chamadas e voltas por etapa (só contagens e nomes de subcomando, flag e arquivo) |
| `score.json` | A nota da rodada, se existir |
| `metrics-<run_id>.json` | O `metrics.json` de cada execução (tempo da varredura, regras do ZAP), se existir |
| `meta.json` | Caso, modo, versão do `pyproject.toml` da cópia, data, rótulo, nome da rodada e modelo |

## O que NUNCA entra

- Alvo real, dado bruto de produto real, perfil (`products/`), auditoria do proxy, achados e `report`.
- Transcript, texto de raciocínio, saída de comando, conteúdo de arquivo.
- Segredo, senha, token ou qualquer coisa de `sealed/` (o modo vai no `meta.json` porque é laboratório e a medição é do coordenador, nunca da cópia cega).

`measure --save` confere cada arquivo contra `sealed/secrets.json` da rodada e recusa gravar se um valor aparecer; também recusa sobrescrever uma pasta que já existe. `evals/` inteira fica fora da cópia cega (`prepare`), então estes arquivos nunca chegam ao agente.

## Como ler

- `compare A B` mostra `B - A`. Campo que não existe numa das medições aparece como `n/d`, nunca como zero.
- `hdast_version` é a do `pyproject.toml` da cópia da rodada. As rodadas anteriores à 1.1.0 trazem `0.1.0` (a versão só foi subida depois); quem identifica a versão do produto nessas pastas é o rótulo (`v1-0`, `v1-1`).
- Uma rodada é uma amostra: os tempos de varredura variam com a carga da máquina e os tokens com o caminho que o agente escolheu. Compare várias rodadas antes de concluir.
- `agent-metrics.json` descreve o agente que executou a rodada (modelo no campo `model`); não troque de modelo entre as rodadas que for comparar.
