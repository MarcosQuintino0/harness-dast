# Modelo de achado (planejado)

> **Status: Planejado (M4).** Nada nesta página existe em código. O desenho aprovado fixa apenas os pontos abaixo; os campos exatos do modelo, do fingerprint e do relatório são definidos no M4 e serão registrados em ADR, porque o formato do achado é contrato.

## O que o desenho aprovado diz

- A CLI tem um **modelo próprio de achado**, independente do formato do ZAP. Isso permite trocar o motor e adicionar destinos de relatório (SARIF, DefectDojo, Jira) sem mexer no domínio.
- Os tipos previstos em `domain/finding.py` são `Finding`, `Evidence`, `Severity` e `Fingerprint`.
- O adaptador do ZAP converte os alertas brutos do ZAP (`RawAlert`) em achados. A conversão é tradução; severidade e fingerprint são decididos no `domain`.
- **Evidência:** todo achado no relatório traz a requisição e a resposta que o sustentam, **sem segredos**. Cabeçalhos de autenticação, valores de segredos conhecidos e padrões como JWT e CPF são redigidos antes de qualquer gravação.
- **Fingerprint:** identificador estável de um achado entre execuções, usado para comparar releases. Precisa ser definido com cuidado e **versionado**, porque mudá-lo depois invalida o histórico. O desenho prevê que o fingerprint considere papéis de conta, para o teste de autorização da V2.
- **Relatório:** gerado em JSON e Markdown (porta `ReportSink`).
- **Triagem:** o agente pode anotar achados, mas **não muda a severidade nem apaga achados**.

## O que ainda não está definido

| Ponto | Onde é decidido |
| --- | --- |
| Campos de `Finding` e de `Evidence` | M4 |
| Escala de `Severity` e mapeamento a partir do ZAP | M4 |
| Composição e versão do `Fingerprint` | M4 |
| Limiar de severidade que faz o comando sair com código `1` | M4 |
| Estrutura do relatório JSON e do Markdown | M4 |
| Prazo de retenção das evidências em `runs/` | Em aberto (desejável na V1) |

## Onde o achado aparece

Em `runs/RUN_ID/`, junto de `audit.jsonl`, `harness.log` e `manifest.json` (veja [../architecture.md](../architecture.md#logs-e-rastreabilidade)). A pasta `runs/` fica fora do git.

## Baseline de regressão

O conjunto de achados esperados no VAmPI (alvo vulnerável do lab) fica versionado. O teste de ponta a ponta falha se um achado conhecido sumir, e o modo seguro do VAmPI não pode gerar achado de severidade alta. Veja [../testing.md](../testing.md).
