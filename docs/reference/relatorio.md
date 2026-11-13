# `hdast report`: achados, relatório e triagem

> **Status: Implementado (M4), verificado contra o ZAP 2.17 real.** Decisões: [ADR 0022](../adr/0022-scan-e-report-plano-por-requisicao-achado-e-triagem.md) e [ADR 0023](../adr/0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md). Formato dos achados: [finding-schema.md](finding-schema.md). Antes dele vem o [`scan`](scan.md); `hdast run` encadeia tudo. (O nome do arquivo é `relatorio.md` e não `report.md`: a ferramenta de escrita usada no desenvolvimento recusa esse nome.)

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

## O que foi verificado contra o ZAP real

Os 12 itens que a autora do `scan` e do `report` deixou (ela só tinha um ZAP simulado) foram conferidos em 2026-11-13 contra o ZAP 2.17.0, o proxy de escopo e os alvos do lab (VAmPI e Clínica Piloto). Resultado de cada um; números e tabelas em [../reviews/2026-11-13-e2e-lab.md](../reviews/2026-11-13-e2e-lab.md); decisões em [ADR 0023](../adr/0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md).

| # | Item | Resultado |
| --- | --- | --- |
| 1 | Nomes de parâmetros e formas de resposta (`ascan/*`, `context/*`, `core/view/message(s)`, `alert/view/alerts`, política) | **PASS** nos nomes e formas; **FIXED** um defeito: `disableScanners` recusava o pedido inteiro (`does_not_exist`) por causa do id 10095. O `scan` ainda precisa do contexto do `probe` MAIS RECENTE: um novo `probe` faz `newSession` e as execuções anteriores perdem o contexto (erro claro, saída 4) |
| 2 | Ids das regras desligadas existem e ficam `enabled=false` | **FIXED**: 9 de 10 existem e ficam desligados (lidos de volta); 10095 é regra passiva e foi removido da lista. O adaptador agora confere os ids ANTES de desligar |
| 3 | `maxScanDuration` corta e o corte aparece como `FINISHED` com `progress < 100` | **PASS**: teto de 1 min cortou a varredura de `buscarPacientesPorNome` em 40% (290 requisições, 62 s), marcada `truncated` |
| 4 | `postData` idêntico acha o nó; `POST` e `PUT` reaproveitam o cabeçalho | **PASS** para corpos JSON (`criarConvenio`, `criarPaciente`, `register_user`...). Corpos com acentos e quebras de linha não foram exercitados (os gerados eram ASCII): não verificado |
| 5 | Replacer: `REQ_HEADER` vale nas requisições do varredor; renovação sem perda; regra de cookie; remoção de tudo | **PASS** na autenticação: 100% das mensagens do varredor ativo levavam o cabeçalho de autenticação (histórico do ZAP, todos os cenários). Remoção: **PASS** após sucesso e após `hdast stop`/Ctrl+C (teste de integração); **limitação confirmada**: processo morto à força deixa as regras `hdast-` (varridas na próxima partida). Regra do cookie CSRF: **FIXED** (`REQ_HEADER_STR` não acrescenta o cookie ausente; passou a `REQ_HEADER` sobre `Cookie`), veja o item 12 |
| 6 | Atribuição por `sourceMessageId` | **PASS**: 100% dos achados em `source_message` nos dois alvos (nenhum `scan`, `url_match` ou `unresolved`). Limitação: uma injeção em caminho cai na operação VARRIDA, não na rota que respondeu |
| 7 | Evidência: requisição e resposta completas, limite de 1 MiB | **PASS** (26 mensagens de evidência numa execução do piloto); mensagens grandes caem em "evidência indisponível" |
| 8 | Redação (token, senha e XSRF reais) nos artefatos, `stdout` e `stderr` | **PASS**: zero ocorrências (teste de integração, abaixo) |
| 9 | Parada: `ascan/action/stop`, contagem no proxy depois do `stop`, janela fechada no meio | **PASS**: `hdast stop` durante a varredura: veja o relatório do lab para o tempo; o `scan` solto também para por janela e prazo (testes unitários e prazo de 1 min medido) |
| 10 | Saturação: o `GET` de saúde detecta a lentidão do VAmPI com e-mail malicioso (ReDoS) | **NÃO VERIFICÁVEL**: o `PUT` de e-mail do VAmPI não é varrido pela política da V1 (só `PUT` sobre recurso criado na execução), então a ReDoS não foi provocada. A guarda ficou ligada e quieta (22 conferências, 0 falhas no piloto); o caminho de parada tem testes com falsos |
| 11 | O proxy de escopo recusa o que o varredor inventa fora do contexto sem derrubar a varredura | **PASS**: milhares de pedidos negados por execução (`malformed_request`, `path_not_allowed`, `origin_not_allowed`), contados em `scan.json` `traffic.denied`, e as varreduras terminaram normalmente |
| 12 | Piloto: limite de login, CSRF por cookie duplicado, `PUT` sobre recurso criado, `POST` que cria dados e `cleanup`, tabela CWE | **PASS** no login (cada conta uma vez; o `run` compartilha cache e orçamento); **FIXED** no CSRF (cerca de 6% das escritas do varredor, das regras PHP, saíam sem o cookie e eram recusadas; depois da correção, 547 de 547 com o par igual e zero recusas; [ADR 0023](../adr/0023-verificacao-do-scan-no-zap-real-csrf-trafego-e-regras.md)); **PASS** em `PUT`/`POST` (dados criados e removidos pela limpeza contra um Oracle Free real) e na tabela CWE, conferida contra as páginas oficiais de 2023 (nenhuma correção; fontes no docstring de `domain/finding_taxonomy.py`) |

