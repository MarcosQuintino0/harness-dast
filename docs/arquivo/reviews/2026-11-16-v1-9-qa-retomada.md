# QA independente: retomada da V1.9

Data: 2026-11-16. Na base `4758f8a`, os seis casos de recibo adulterado passaram e os quatro cenários reproduzidos anteriormente falharam: três falsos efeitos e ausência de aviso após PUT com resposta 500. Os testes continuam sem `xfail`.

O teste independente `test_independent_effect_audit.py`, com alvo falso, exige um efeito e um achado não vazios, além de GETs de receita antes e depois da escrita identificados na auditoria e ordenados pelo número de sequência. Falhou na base antiga por ausência de efeito; Ruff e mypy dirigidos passaram. A verificação é offline e não substitui a T2 com alvo de laboratório.

Os recibos e hashes relacionam artefatos a fontes, mas não autenticam arquivos contra substituição coordenada: não são assinatura. Uma resposta 404 anterior demonstra invisibilidade à conta consultada, não inexistência global de um identificador. O estado anterior precisa permanecer `unknown` quando não foi observado; o snapshot observado é dado privado, limitado a campo e escalar elegíveis, não deve ser publicado. A persistência no teste de arquivo antes do envio não demonstra durabilidade dos metadados após perda de energia.

## Revalidação offline da integração

Após rebase sobre `ed0a90d`, os oito arquivos independentes passaram: **35/35**, incluindo os quatro casos antes falhos, recibos adulterados, auditoria e snapshot com receita e restauração. O teste verifica dois PUTs: o snapshot anterior à primeira escrita registra o valor inicial; o da restauração registra o valor observado depois da alteração. Ruff, formatação e mypy dirigidos aos três arquivos de observação, diário e auditoria passaram. Os testes usam falsos e o adaptador de diário real em diretório temporário; não foram executados Docker, alvo, T2/T4 nem suíte global nesta revisão.

O verificador T2 integrado em `ed0a90d` exige listas não vazias e não exporta os valores dos snapshots. Contudo, suas contagens de GET anterior e posterior aceitam eventos de receitas e contas diferentes e não verificam ordem junto à escrita; além disso, procura snapshots arquivados pela chave de produto/operação/conta/método, sem restringir os arquivos ao período da rodada atual. Assim, as contagens por si só ainda não vinculam as três evidências à mesma execução e mutação. A coordenação foi avisada; a conclusão da prova de laboratório depende da correção ou de evidência equivalente.
