# Captura REAL do ZAP 2.17.0

Estes quatro arquivos (`probe.json`, `scan.json`, `alerts.raw.json`, `evidence.json`) são de uma
execução real de `hdast probe` e `hdast scan` contra o VAmPI vulnerável do lab, com o ZAP 2.17.0
e o proxy de escopo reais (2026-11-13). Já saíram redigidos da CLI (token, cabeçalho
`Authorization` e `SECRET` do depurador do Werkzeug aparecem como `***`). O VAmPI é um alvo de
treino público e os dados são os de semente; nada aqui é de ambiente real.

Servem para o teste de forma (`tests/unit/application/test_report_real_capture.py`): o `report`
precisa ler alertas e evidência exatamente como o ZAP real os devolve. Os arquivos
`../zap_alerts/` seguem sendo a referência reconstruída (e hostil) do relatório.
