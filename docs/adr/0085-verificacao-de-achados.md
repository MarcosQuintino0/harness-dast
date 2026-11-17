# 0085. Verificação aditiva de achados

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** plano V1.11, fase A

## Contexto

A evidência guardada pode sugerir uma falha sem demonstrar reprodução. A ausência de prova não é prova contrária; a indicação de falso positivo do ZAP é consultiva. Achados, severidade e status precisam permanecer intactos.

## Decisão

Vamos usar `verification.json` com envelope v1, produto, execução e entradas por fingerprint único. O domínio define os níveis `reproduced`, `likely`, `inconclusive`, `likely_false_positive` e `not_verifiable`, com motivo, receita e evidências opcionais de ataque e controle. A fase offline só atribui `likely` a evidência disponível com trecho apontado pelo ZAP; indicação de falso positivo ou falta de trecho resulta em `not_verifiable`. Ela não inventa reprodução nem conclui falso positivo sem prova contrária. A reprodução controlada acrescenta comparações conforme o ADR 0087.

A escrita redige textos com as rotinas existentes e a máscara dos segredos da execução; padrões isolados não garantem ocultar segredos desconhecidos. O envelope é separado de `findings.json`, `triage.json` e `finding_confidence`: não modifica esses contratos nem representa confirmação humana. Falhas de validação não incluem valores recebidos.

## Alternativas consideradas

Modificar o achado ou sua severidade apagaria a distinção entre alerta e revisão. Tratar a opinião do ZAP como prova de falsidade ou a ausência de evidência como prova contrária geraria conclusões indevidas. Foram descartadas.

## Consequências e aceites

O envelope é consultivo e está ligado a `confirm`, painel e relatórios. Testes devem cobrir versões e entradas inválidas, ausentes e malformadas, unicidade, redação, leitura e escrita e regras offline, sem rede. A validação no laboratório e a calibração permanecem pendentes; não há porcentagem ou afirmação de eficácia nesta fase.
