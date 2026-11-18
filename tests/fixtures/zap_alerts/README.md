# Fixtures de alertas do ZAP

**Estes arquivos foram RECONSTRUÍDOS a partir do spike do M0 (`docs/arquivo/spikes/2026-11-13-m0-zap.md`),
não capturados de um ZAP real.** As formas dos campos (`pluginId`, `alertRef`, `cweid`, `risk`,
`confidence`, `inputVector`, `messageId`, `sourceMessageId`...) e os identificadores de regra
(`40018` SQL Injection, `40012` XSS refletido, `10021`, `10036`, `10104`) são os do spike. Os
valores (URLs, ids de mensagem, textos de descrição) são inventados para exercitar o código.
Um achado do conjunto é deliberadamente hostil (título, parâmetro e corpo com Markdown, HTML e
texto que imita instruções) para provar que o relatório não os executa nem os interpreta.

Quando houver captura real do ZAP (teste de integração contra o lab), troque `alerts.raw.json` e
`evidence.json` por ela e regrave os arquivos de referência.

| Arquivo | O que é |
| --- | --- |
| `probe.json` | `probe.json` de uma execução do VAmPI (formato de `ProbeResult`) |
| `scan.json` | `scan.json` da mesma execução (uma varredura truncada, três operações puladas) |
| `alerts.raw.json` | Alertas brutos, já redigidos, no formato que o `scan` grava |
| `evidence.json` | Mensagens de evidência, já redigidas |
| `findings.golden.json` | Saída esperada de `findings.json` |
| `report.golden.md` | Saída esperada de `report.md` |
| `report.golden.html` | Saída esperada de `report.html` (também serve de exemplo para revisão: abra no navegador) |

Regravar as saídas esperadas depois de uma mudança intencional no relatório:

```bash
HDAST_UPDATE_GOLDEN=1 uv run pytest tests/unit/application/test_report_golden.py
git diff tests/fixtures/zap_alerts
```

Revise o diff: a mudança precisa ser a que você quis.
