# QA independente: retomada da V1.9

Data: 2026-11-16. Na base `4758f8a`, os seis casos de recibo adulterado passaram e os quatro cenários reproduzidos anteriormente falharam: três falsos efeitos e ausência de aviso após PUT com resposta 500. Os testes continuam sem `xfail`.

O teste independente `test_v19_independent_effect_audit.py`, com alvo falso, exige um efeito e um achado não vazios, além de GETs de receita antes e depois da escrita identificados na auditoria e ordenados pelo número de sequência. Falhou na base antiga por ausência de efeito; Ruff e mypy dirigidos passaram. A verificação é offline e não substitui a T2 com alvo de laboratório.

Os recibos e hashes relacionam artefatos a fontes, mas não autenticam arquivos contra substituição coordenada: não são assinatura. Uma resposta 404 anterior demonstra invisibilidade à conta consultada, não inexistência global de um identificador. O estado anterior precisa permanecer `unknown` quando não foi observado; o snapshot observado é dado privado, limitado a campo e escalar elegíveis, não deve ser publicado. A persistência no teste de arquivo antes do envio não demonstra durabilidade dos metadados após perda de energia.
