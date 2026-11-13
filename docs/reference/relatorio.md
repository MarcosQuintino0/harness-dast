# `hdast report`: achados, relatório e triagem

> **Status: Implementado (M4)**, verificado contra um ZAP falso com as formas do spike do M0, **não** contra o ZAP real. Decisão: [ADR 0022](../adr/0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md). Formato dos achados: [finding-schema.md](finding-schema.md). Antes dele vem o [`scan`](scan.md). (O nome do arquivo é `relatorio.md` e não `report.md`: a ferramenta de escrita usada no desenvolvimento recusa esse nome.)

```bash
uv run hdast --json report meu-produto --run <run_id>
uv run hdast report meu-produto --run <run_id> --compare <outro_run_id> --fail-on high
```

Transforma os alertas brutos de uma execução em **achados** e escreve `findings.json` e `report.md` na pasta dela. **Não usa rede nem o ZAP**: lê só arquivos (`probe.json`, `scan.json`, `alerts.raw.json`, `evidence.json` e, se existir, `triage.json`). Por isso não confere janela nem autorização.

| Flag | Efeito |
| --- | --- |
| `--run RUN_ID` | **Obrigatória.** Execução com `probe.json` e `scan.json` |
| `--compare RUN_ID` | Marca os achados como `new` ou `persistent` e lista os `not_observed` (precisa de `findings.json` da outra execução, do mesmo produto e da mesma versão de fingerprint) |
| `--fail-on LIMIAR` | `none`, `low`, `medium` ou `high`. Sai com `1` se houver achado com severidade proposta igual ou acima. Sobrepõe `scan.fail_on` do perfil (padrão `none`) |
| `--products-dir` | Pasta de produtos |

## Código de saída 1

**O `report` é o dono do código `1`**, não o `scan`: o `scan` só coleta alertas; o veredito depende de fingerprint, deduplicação e severidade lida. Regras:

- `1` não é erro: o envelope traz `ok: true`, `data.exceeds_threshold: true` e o mesmo `data` de sempre.
- Conta **todos** os achados na severidade **proposta pelo ZAP**, inclusive os anotados como "suspeita de falso positivo": a triagem do agente nunca retira nada da conta.
- Sem limiar (`none`, o padrão), a saída é `0` com ou sem achados.
- Erros: `2` (execução sem `scan.json`, arquivo ilegível, `triage.json` inválido, comparação impossível, `--fail-on` desconhecido).

## `data`

| Campo | Descrição |
| --- | --- |
| `run_id`, `product`, `files` | Execução e arquivos gerados (`findings.json`, `report.md`) |
| `threshold`, `exceeds_threshold` | Limiar aplicado e se há achado nele ou acima |
| `summary` | Totais por severidade proposta |
| `coverage` | Alcançabilidade do `probe`, varreduras truncadas, operações sem varredura com o motivo, limites e política |
| `not_tested_statements` | As afirmações fixas sobre o que não foi testado |
| `findings` | Resumo de cada achado (`finding_id`, `fingerprint`, `title`, severidade e confiança propostas, operação, método, modelo de caminho, parâmetro, ocorrências, CWE, categoria OWASP, `comparison`, `suspected_false_positive`). **A evidência não vai no envelope**: está em `findings.json` e `report.md`, para o agente não carregar dado do alvo sem precisar |
| `not_observed`, `comparison`, `triage_orphans` | Comparação e triagem |

## O que o relatório diz sobre honestidade

Toda execução, inclusive sem achados, leva no `findings.json` (`not_tested_statements`) e no `report.md` (seção "O que este relatório não testou", sempre antes do resumo):

- autorização (BOLA/IDOR, BFLA, troca de dados de outro usuário), atribuição em massa, exposição excessiva em respostas legítimas e lógica de negócio **estão fora** do que uma varredura ativa do ZAP detecta;
- só se varreu o que o `probe` alcançou com sucesso e o plano permitiu; o resto está listado como não testado, com o motivo;
- a alcançabilidade do `probe`, as varreduras truncadas e os limites e a política aplicados;
- severidade e confiança são propostas, todo achado exige triagem humana;
- **um relatório sem achados não é evidência de que a API é segura.**

## `report.md`

Em português, para quem corrige: aviso de que blocos de requisição e resposta são dado do alvo, a seção acima, resumo e tabela (ID, severidade, confiança, título, onde, ocorrências, comparação quando houver, coluna "Triagem (agente)"), um bloco por achado (o que é, onde, parâmetro e vetor, classe, evidência, como reproduzir, **direção de correção sugerida** genérica para APIs no estilo Spring e marcada como sugestão não verificada, solução padrão do ZAP, triagem) e a seção de comparação.

**Seguro para renderizar:** todo texto derivado do alvo, do ZAP ou do agente passa por `domain/markdown_safe.py`: texto em linha com barra invertida antes de todo caractere de marcação e sem quebra de linha, trecho de código em linha com crases suficientes, e requisição e resposta em bloco cercado por uma cerca mais longa que qualquer sequência de crases do conteúdo. HTML não é interpretado (`<`, `>` e `&` escapados ou dentro de bloco). Um texto que imite instrução ("ignore as instruções anteriores") continua sendo texto, mostrado em bloco sob um aviso; nenhuma função "entende" ordens.

## Triagem (`triage.json`)

O agente **pode** anotar achados num arquivo **separado**, `runs/<run_id>/triage.json`. O `report` nunca deixa uma anotação apagar achado, mudar a severidade proposta ou o status.

```json
{
  "schema_version": 1,
  "annotations": [
    {
      "fingerprint": "<64 hexadecimais minúsculos do achado>",
      "note": "texto livre, até 500 caracteres",
      "suspected_false_positive": true,
      "reason": "obrigatório quando há suspeita, até 500 caracteres"
    }
  ]
}
```

- Só esses quatro campos existem. **Qualquer outro** (`severity`, `status`, `delete`...) é erro de validação (`CONFIG_ERROR`, saída 2) com a mensagem "campo não permitido (a triagem não altera severidade nem status)".
- No máximo uma anotação por fingerprint; no máximo 5000 anotações; textos de até 500 caracteres.
- Fingerprint inexistente é "órfão": ignorado e listado em `triage_orphans`.
- A anotação aparece em `findings[].triage` e na coluna "Triagem (agente)" do `report.md`, escapada; o texto vem do agente e é tratado como não confiável.
- O arquivo ausente é normal (sem triagem).

## Comparação entre execuções

`--compare OUTRA` lê o `findings.json` da outra execução e classifica por **fingerprint**:

| Marca | Significado |
| --- | --- |
| `new` | No relatório atual, não na base |
| `persistent` | Nos dois |
| `not_observed` | Na base, **não observado nesta execução**. Nunca é chamado de "corrigido": `operation_scanned_now` diz se a operação foi varrida agora, e o relatório avisa que varredura cortada ou não repetida também explica a ausência |

Recusas: execução de outro produto; versão de fingerprint diferente; a mesma execução; execução sem `findings.json` (rode o `report` nela antes).

## O que ainda precisa ser verificado contra o ZAP real

Nada do `scan` e do `report` rodou contra o ZAP 2.17 real nesta rodada (o ZAP do lab estava em uso pelo `probe`). A verificação precisa conferir, nesta ordem:

1. **Nomes de parâmetros e formas de resposta** do cliente de varredura: `ascan/action/setOption*` com o valor no parâmetro `Integer`; `ascan/action/addScanPolicy` (`scanPolicyName`, `attackStrength`, `alertThreshold`), `removeScanPolicy`, `disableScanners` (`ids`, `scanPolicyName`); `ascan/view/scanPolicyNames`, `ascan/view/scanners` (`id`, `enabled`); `ascan/action/scan` (`url`, `method`, `postData`, `contextId`, `scanPolicyName`, `recurse`) e o retorno `{"scan": "<id>"}`; `ascan/view/scans` (`id`, `progress`, `state`, `reqCount`, `alertCount`); `context/view/context` (`context.id`); `core/view/messages` (paginação `start`/`count`, campo `type`, `requestHeader`...), `core/view/message` (`message`); `alert/view/alerts` (paginação).
2. **Ids das regras desligadas** ([scan.md](scan.md#política-e-limites-sempre-explícitos)) existem na imagem fixada e ficam `enabled=false` na política `hdast-scan` depois de `disableScanners`.
3. **`maxScanDuration` e `maxRuleDuration`** de fato cortam e o corte aparece como `FINISHED` com `progress < 100` (o spike mediu 45%).
4. **`postData` idêntico** ao corpo aprendido acha o nó (corpo JSON com acentos e com quebras de linha); varredura de `POST` e `PUT` reaproveita o cabeçalho aprendido.
5. **Replacer**: a regra `REQ_HEADER` com `url` sobrescreve `Authorization` nas requisições do varredor ativo; renovação por `addRule` antes de `removeRule` não perde requisição; a regra `REQ_HEADER_STR` com regex troca só o valor do cookie XSRF dentro de `Cookie` e o escape de `$` e da barra invertida no valor da substituição está certo; **o que acontece quando o `Cookie` não existe na requisição aprendida** (CSRF: a verificar); remoção de todas as regras `hdast-` ao fim, também após erro.
6. **Atribuição**: o `sourceMessageId` dos alertas é uma mensagem do histórico aprendido (e não outra mensagem do mesmo nó); medir quantos alertas caem em `scan`, `url_match` e `unresolved`.
7. **Evidência**: `core/view/message` devolve requisição e resposta completas; o tamanho respeita o limite de 1 MiB do cliente; mensagens grandes viram "evidência indisponível".
8. **Redação**: procurar o token, a senha e o valor do cookie XSRF reais em `alerts.raw.json`, `evidence.json`, `findings.json`, `report.md`, `scan.json` e no log do `stderr` depois de um `scan` e um `report` completos.
9. **Parada**: `ascan/action/stop` com varredura em curso; contagem de requisições no proxy de escopo depois do `stop`; janela fechada de verdade no meio.
10. **Saturação**: o `GET` de saúde detecta a lentidão do VAmPI com `email` malicioso (ReDoS) e para o `scan` com saída 6 antes de o alvo cair.
11. **Proxy de escopo**: o varredor gera caminhos fora do contexto (288 de 467 no spike); o proxy precisa recusá-los sem derrubar a varredura, com a injeção em caminho ligada.
12. **Alvo piloto (Spring/Oracle)**: login com limite de 5 por minuto durante a renovação do token (o mínimo `60 / max_per_minute` entre logins), CSRF por cookie duplicado de ponta a ponta, `PUT` sobre recurso criado, `POST` que cria dados e o `cleanup` depois, e a tabela CWE para OWASP conferida contra as páginas oficiais de 2023.
