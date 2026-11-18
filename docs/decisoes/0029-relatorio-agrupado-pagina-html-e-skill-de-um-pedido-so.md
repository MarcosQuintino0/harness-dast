# 0029. Relatório agrupado pela causa, página `report.html` e skill de um pedido só

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** primeiras rodadas cegas ([2026-11-13-rodadas-cegas](../arquivo/reviews/2026-11-13-rodadas-cegas.md)): quem lê o relatório é uma pessoa de QA e o dono do produto, não especialistas, e hoje precisa fazer quatro pedidos ao agente. Muda o contrato de [findings.json](../referencia/finding-schema.md) (campo novo), cria um arquivo novo de saída e uma skill nova; estende os ADRs [0022](0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md) e [0025](0025-limpeza-confirmacao-so-em-terminal-e-correcoes-do-qa-m2-m5.md), que seguem imutáveis.

## Contexto

Três alertas de injeção de SQL com a mesma causa apareciam como três achados, e 26 alertas "Cookie No HttpOnly Flag" do cookie `XSRF-TOKEN` enchiam o relatório. Quem lê precisa ver "quantas causas" e não só "quantos alertas". O `report.md` é bom para quem corrige, mas ruim para ler no navegador e compartilhar. E as quatro skills (`onboard-product`, `fix-reachability`, `run-scan`, `triage-findings`) exigem quatro pedidos. A regra do projeto continua: não apagar nem esconder achado, não mudar severidade.

## Decisão

Vamos:

1. **Agrupar sem esconder.** O relatório ganha uma visão agrupada, `groups`, em `findings.json` (campo **aditivo**: `schema_version` continua 1, arquivos antigos sem o campo continuam legíveis para `--compare`). Dois achados são do mesmo grupo quando têm a mesma regra do ZAP (`alert_ref`), o mesmo vetor de entrada, o mesmo parâmetro e a mesma severidade proposta. Cada achado está em exatamente um grupo e continua em `findings`, com a severidade e o fingerprint de sempre. O grupo traz contagem de achados e de alertas e a lista de **onde aparece** (método, caminho, operação, id do achado). A regra é pura, em `domain/finding_group.py`, com versão própria (`GROUPING_VERSION`, 1); o id do grupo é `G-` e 8 hexadecimais da chave, estável entre execuções. O envelope de `hdast report` ganha `data.groups` com o mesmo conteúdo. O `report.md` ganha a seção "Achados agrupados pela causa".
2. **Notas fixas de padrões esperados.** `domain/known_patterns.py` guarda, em texto nosso, explicações de padrões que costumam ser esperados. A primeira: o cookie de XSRF por duplo envio precisa ser lido por script, então a falta de `HttpOnly` nele costuma ser esperada (regra 10010 com cookie `XSRF-TOKEN`, `X-XSRF-TOKEN`, `csrf-token` ou `csrftoken`). A nota vai em `groups[].expected_note`, não altera severidade nem confiança e não retira o achado; a decisão continua sendo humana.
3. **`report.html`.** O `report` grava, junto de `findings.json` e `report.md`, uma página HTML única e autocontida: CSS embutido, **sem JavaScript**, sem fonte nem imagem externa e sem dependência nova, com claro e escuro pelo sistema e uma política de conteúdo (CSP) na própria página que proíbe script e qualquer carga de fora. Seções: resumo (achados por gravidade, política e limites, cobertura), "o que fazer agora", achados agrupados por gravidade (evidência resumida, comando de reprodução, direção de correção), o que a varredura não cobriu e o tráfego recusado pela cerca. A renderização é pura, em `domain/report_html.py` (mais `html_safe.py`, `report_actions.py` e `report_html_style.py`); a gravação é um destino novo, `HtmlReportSink`, na mesma porta `ReportSink`. Não há porta nem dependência nova.
4. **Texto do alvo é dado.** Tudo que vem do alvo, do ZAP ou do agente passa por `domain/html_safe.py`: remoção de controle, ANSI e bidi, **redação de segredos de novo** (mesma rede de `redaction.py`, antes do corte), corte e escape dos cinco caracteres do HTML. Identificadores de nós (execução, operação, caminho de modelo) só são escapados, porque a redação por padrão mascararia ids longos legítimos. "O que fazer agora" é texto nosso derivado dos números do relatório e nunca sugere ampliar escopo, limite ou janela.
5. **Aceita mais de uma origem e qualquer motivo de recusa.** O agrupamento usa só campos que todo `Finding` tem; achados de uma origem nova (por exemplo, autorização entre contas) entram pela mesma regra. A seção de tráfego lista `denied_by_reason` com qualquer motivo, sem tabela fixa de motivos.
6. **Skill `test-product`.** Uma skill orquestradora conduz as quatro skills de etapa em sequência e só para quando precisa da pessoa: falta dado na carta, alcançabilidade abaixo da meta depois das tentativas permitidas, achado alto para confirmar, ou dúvida de autorização, escopo ou janela. Ela **não repete regra**: aponta para as skills de etapa e para a CLI, e cita as travas da Parte B do `CLAUDE.md`. O teste de contrato `tests/contract/test_skills_and_guides.py` confere cada comando e flag citados nela, a ordem das etapas, os casos de parada e a citação das travas.

## Alternativas consideradas

- **Fundir os achados no fingerprint (menos achados).** Apagaria achados e quebraria o histórico e o `--compare`; vai contra a regra de não esconder achado. Descartada: o grupo é visão, não identidade.
- **Agrupar só por regra.** Juntaria `book_title` e `username` na mesma injeção de SQL, que não têm a mesma causa provável. Descartada: o parâmetro entra na chave.
- **Subir `schema_version` para 2.** O campo é aditivo e o leitor antigo o ignora. Descartada, como no ADR 0025 para `coverage.partial`.
- **Página com JavaScript (filtros, abas).** Ganho pequeno para o público, superfície de ataque grande com texto do alvo. Descartada; `<details>` cobre o recolher e o expandir.
- **Biblioteca de templates (Jinja2).** Dependência nova para um relatório de seções fixas; o escape fica mais fácil de auditar com poucas funções. Descartada.
- **Uma skill que absorve as quatro.** Duplicaria regra (critério de parada, tabelas de erro) e divergiria. Descartada: a orquestradora só aponta.

## Consequências

- O relatório fica legível para quem não é especialista, sem perder nenhum achado. Quem consome `findings.json` ganha `groups` e pode ignorá-lo.
- Mudar a regra de agrupamento muda os ids de grupo: suba `GROUPING_VERSION` e registre. O fingerprint de achado não é afetado.
- O agrupamento é uma heurística: "mesma regra, mesmo parâmetro" não prova a mesma causa. Por isso a lista de onde aparece fica sempre visível e a nota de padrão esperado fala em "costuma".
- A lista de padrões conhecidos é curta de propósito (um padrão). Cada nota nova exige teste e passa por revisão, porque pode induzir a descartar um achado real.
- `report.html` é mais um arquivo a manter em sincronia com `report.md`; os dois derivam do mesmo `FindingsReport`.
- O teste de ponta a ponta com o agente (um pedido só) ainda não foi medido na avaliação cega: a skill existe e o contrato dela é conferido, mas a rodada cega com ela está pendente.

## Adendo (2026-11-13): achados de autorização entre contas e o agrupamento

Não altera a decisão acima; registra o que ficou decidido quando o ADR [0027](0027-teste-de-autorizacao-entre-contas.md) chegou ao mesmo relatório.

- **Decisão:** os achados de `authz` (`A-<8 hex>`, em `findings.json` `authz.findings`) **não entram em `groups`**. A regra de agrupamento (versão 1) usa a regra do ZAP (`alert_ref`), o vetor de entrada e o parâmetro, que um achado de autorização não tem; e cada achado de `authz` já é um por operação e técnica, com os campos envolvidos (só nomes) no próprio achado. Forçá-los na chave do ZAP criaria um "grupo" sem regra do ZAP ou obrigaria a mudar `GROUPING_VERSION` e os ids `G-` de quem já consome o campo. O item 5 da decisão ("origens novas entram pela mesma regra") fica como capacidade do código, não como o que o `report` faz hoje.
- **O que garante que não somem:** `summary.authz_by_severity` (aditivo), cartões próprios e a linha "Autorização entre contas" no resumo de `report.html`, a seção própria com uma divisão por técnica (visão só da página, não identidade), os passos de "o que fazer agora" e o `--fail-on`, que conta os dois tipos. `summary.total` e `summary.by_severity` seguem sendo só do ZAP, e `groups` continua cobrindo exatamente os achados de `findings`.
- **Quando rever:** se uma execução real trouxer muitos achados de `authz` com a mesma causa (o mesmo campo exposto em várias listagens, por exemplo), um ADR novo pode agrupá-los por técnica e campo, com versão própria do agrupamento.
