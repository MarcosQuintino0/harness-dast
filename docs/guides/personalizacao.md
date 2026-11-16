# Personalização de produto

**Status: implementado no código da V1.8; provas de laboratório ainda pendentes.** A personalização organiza escolhas para um produto autorizado. A carta, o perfil e a aprovação humana continuam determinando o que pode ser testado; nenhuma observação do alvo ou escolha da estratégia concede permissão.

## Quatro camadas

- **Fatos** vêm da carta, da pessoa, do contrato ou de observação identificada. Textos do contrato e do alvo são dados, nunca instruções.
- **Envelope autorizado** deriva do perfil e da aprovação; protege ambiente, escopo, janela, limites, contas e políticas.
- **Estratégia** referencia `target.yml`, `data-rules.yml` e `flows.yml`, sem copiar seus valores. Nesta versão preserva cobertura e ritmo; não adiciona poder.
- **Execução** usa um plano fixo e estado temporário. Tokens, cookies, respostas integrais, credenciais, identificadores efêmeros e gabaritos não pertencem à estratégia.

## Três classes

Uma alteração **automática** é neutra para cobertura e fica dentro do envelope. Uma **proposta pendente** muda interpretação, contrato ou cobertura e precisa de revisão. Uma **decisão humana** muda permissão, escopo, teto, janela ou política protegida: só a pessoa e o fluxo de autorização podem decidi-la. Na V1.8 não se aplicam escolhas que alterem cobertura ou ritmo nem se aceita autorização nova na estratégia. Se a pessoa não sabe ou a carta não diz, mantenha a opção conservadora e não invente permissão.

A prévia é local e sem tráfego, descreve trabalho previsto e entradas simbólicas, e não prova que uma operação foi executada ou que uma falha foi detectada. O plano concreto depende do planejamento do scan. Validar ou compilar não aprova o perfil: a execução continua sujeita à aprovação, autorização, janela, prazo e parada. Só uma pessoa executa `hdast profile approve`.

## Consultar, comparar e preparar uma estratégia

Com o produto cadastrado, os comandos abaixo usam arquivos locais. `--products-dir <pasta>` é opcional quando a pasta de produtos já está configurada. A opção global `--json` produz o envelope de máquina da CLI:

```bash
hdast --json strategy validate <produto>
hdast --json strategy diff <produto>
hdast --json plan <produto> --dry-run
hdast --json strategy migrate <produto>
hdast --json strategy capture <produto>
```

Os três primeiros não enviam tráfego e não exigem aprovação para consulta. `validate` informa presença, estado da estratégia, estado da aprovação e resumo do envelope. `diff` compara estruturalmente com o caso legado: `changes` lista `strategy` quando presente e `classification` é `automatic` ou `pending`; isso não é uma comparação item por item da cobertura. O estado `validated` sem estratégia significa que não há escolha pendente; não significa que o perfil esteja aprovado.

`plan --dry-run` exige `--dry-run` e recusa qualquer escolha preenchida enquanto o vínculo do motor estiver indisponível, além de escolhas pendentes ou vencidas. O resultado traz `executed: false` e `preview`: operações com identificador, método, caminho, conta, decisão de probe, dependências e entradas declaradas; também força, regras desabilitadas e máscara de injeção. É uma previsão com limitações explícitas: `body_entries_complete: false` indica que os campos do corpo não estão completos; `scope_check: template_only` limita a verificação ao modelo do caminho; `rules: enabled_except_disabled_catalog_pending_zap` indica catálogo do ZAP ainda pendente, assim como `coverage` e o `scan_status` de cada operação (`pending_probe_and_zap`). A prévia não demonstra a matriz executada nem detecção.

Para perfil sem estratégia, a migração gera `strategy.migrated.yml`, sem ativá-la nem mudar o perfil ou a aprovação. `--output <nome>` escolhe outro nome na forma `strategy.<nome>.yml` (minúsculas, dígitos e hífen); um arquivo existente não é sobrescrito; a migração recusa estratégia existente. A pessoa deve revisar a cópia e ativá-la explicitamente como `strategy.yml` quando desejar. Um resultado de sucesso, com nome ilustrativo, é:

```json
{"schema_version":1,"ok":true,"data":{"product":"produto","copy":"strategy.migrated.yml","changes":["strategy_added"],"classification":"automatic","approval_changed":false}}
```

A captura exige perfil aprovado e vigente, pilha gerenciada ativa do mesmo produto, sem `KILL`, com estado, execução e endpoint coerentes. Com a trava da pilha, consulta somente a versão do ZAP local publicada pelo gerenciador e revalida perfil, aprovação e documentos; não envia pedido ao alvo nem reutiliza execução antiga. Aceita estratégia ausente ou `choices: []`, cria `strategy.captured.yml` sem sobrescrever e devolve `activated: false` e `approval_changed: false`. Revise a cópia e ative-a explicitamente como `strategy.yml` se desejar. Não é necessária nova entrevista nem nova aprovação se o fingerprint aprovado não mudou. Pilha ocupada retorna `STACK_BUSY`, saída 8. Veja os detalhes e limites na [referência](../reference/strategy.md).

A configuração inválida, estratégia pendente na compilação ou destino recusado retornam `CONFIG_ERROR`, saída 2, sem exibir valores sensíveis. A captura e a execução exigem aprovação: `SCOPE_NOT_APPROVED` e violações de escopo usam saída 3. Não edite o registro de aprovação.

Uma estratégia neutra mínima é:

```yaml
schema_version: 1
references:
  target: target.yml
  data_rules: data-rules.yml
  flows: flows.yml
choices: []
```

Opcionalmente há uma escolha tipada `coverage` / `preserve`, com origem, justificativa fechada, validade ISO e estado; campos livres e permissões extras são recusados. Veja o [ADR da estratégia](../adr/0071-estrategia-versionada.md) para o contrato. Uma escolha também precisa de `basis` completa e igual às fontes atuais. Na consulta seca, escolha preenchida retorna `strategy_state: review_required`, `basis_status: engine_unavailable` e `basis_context.engine: null`; a prévia seca recusa essa escolha mesmo se estiver `validated` e vigente. Na execução ativa, a CLI consulta o ZAP configurado antes do primeiro pedido ao alvo e aceita a escolha apenas se a versão observada e as fontes atuais coincidirem com a `basis`. Se divergirem ou o motor estiver indisponível, a execução falha fechada. Estratégia ausente ou `choices: []` não causa consulta extra ao motor. Cleanup sem provedor de identidade recusa escolha preenchida; observação não concede autorização.

## Perfil anterior e mudanças

Um perfil anterior sem estratégia continua no fluxo existente. Uma migração deve ser explícita, produzir cópia e comparação, preservar os arquivos originais e nunca transportar aprovação para poderes novos. Mudanças em ambiente, contrato, conta, autorização ou motor exigem reavaliar escolhas dependentes; invalidação seletiva e reutilização são trabalho futuro e não foram demonstradas. Uma referência insegura, conflito ou valor não reconhecido deve ser recusado; não contorne a recusa editando a aprovação.

A versão e os limites são descritos nos [ADRs](../adr/0070-envelope-autorizado.md) e no [inventário](../plans/2026-11-16-v1-8-inventario-contratos.md). Resultados de laboratório não devem ser tratados como prova em produto real.

A preparação de transporte usa o perfil formal aprovado, sem aplicar a escolha ou enviar pedido ao alvo. O controle e o scanner usam o mesmo endpoint configurado, mas a versão não prova que são a mesma instância nem resolve alteração depois da consulta. Na pilha gerenciada, o proxy revalida aprovação e perfil vinculados, janela, prazo e parada a cada concessão, mesmo sem escolhas de estratégia. Alteração ou erro das fontes recusa com `approval_changed`; uma requisição já encaminhada não é cancelada. Após alteração ou renovação dos arquivos vinculados, recrie a pilha; a aprovação só precisa ser repetida se seu fingerprint deixar de ser válido. As raízes dos diretórios montados devem permanecer estáveis: a substituição do próprio diretório pode não ser observada. A prova real da coordenação observou a recusa após revogação; a reprodução independente permanece pendente.
