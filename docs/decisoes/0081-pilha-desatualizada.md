# 0081. Pilha desatualizada: `STACK_STALE` antes do primeiro pedido

- **Status:** Parcialmente substituído pelo ADR 0106
- **Data:** 2026-11-16
- **Origem:** rodadas cegas da V1.9 (Clínica Piloto e VAmPI)

## Contexto

Desde a V1.8 o proxy de escopo gerenciado prende o hash SHA-256 completo do `target.yml` e da
aprovação no `stack up` (`approval_sha256` e `profile_sha256` em `binding`; V1.8, ADRs 0070 a 0075 e `docs/reference/strategy.md`) e, a cada
concessão, confere se os dois arquivos continuam iguais. Qualquer edição de `target.yml` depois
do `stack up`, mesmo num campo livre que não muda a aprovação (`auth.request_encoding`,
`probe.setup_path`), faz o proxy negar todo pedido com 403 e `X-Hdast-Reason: approval_changed`
até a pilha ser recriada. Enquanto isso, `hdast profile approval` continua dizendo `approved`
(os blocos protegidos não mudaram) e a CLI não explica nada: o motivo só aparece no `audit.jsonl`
do estado, que o agente não lê. Nas rodadas cegas da V1.9 o primeiro `preflight` de um perfil
novo falhou com 415 no login, o agente corrigiu `auth.request_encoding` com a pilha de pé e dali
em diante tudo virou 403: numa API o agente parou, na outra adivinhou que devia recriar a pilha.

A falha fechada do proxy está certa e não muda. O defeito é que a trava é invisível e não diz o
que fazer.

## Decisão

Vamos manter o proxy como está (hash completo, falha fechada) e tornar a trava visível e
acionável, com três mudanças na CLI:

1. **Conferência antes do primeiro pedido.** Todo comando que passa pelo proxy (`preflight`,
   `probe`, `scan`, `authz`, `negative` e `run`; fora do `--dry-run`) compara o hash do
   `target.yml` e da aprovação de agora com o vínculo gravado em `policy.json` da pilha ativa do
   mesmo produto. Divergindo, falha **antes de abrir qualquer conexão** com o erro
   `StackStale`. A conferência fica em `FreshStackProfiles`, por cima do repositório que já
   confere a aprovação, de modo que `SCOPE_NOT_APPROVED` tem prioridade. O `cleanup` (fala com o
   banco, não passa pelo proxy), `stack up|down|status` e `stop` não são bloqueados.
2. **Tradução do 403 no meio da execução.** O cliente do alvo transforma a resposta do proxy
   (403, `X-Hdast-Reason: approval_changed` **e** o corpo fixo `hdast scope-proxy: request
   refused`) no mesmo `StackStale`, em vez de entregá-la como resposta do alvo (que viraria
   achado, "não encontrado" ou recusa de escopo comum). As outras recusas do proxy
   (`deny_path`, `path_not_allowed` etc.) e qualquer 403 do próprio alvo seguem como resposta.
   Isto cobre o que a CLI envia (preflight, probe, authz, negative); o tráfego do ZAP no `scan`
   não passa pelo cliente da CLI e continua só na auditoria do proxy.
3. **`stack status` mostra.** O relatório ganha `binding` (`fresh`, `stale`, `unbound` ou
   `unreadable`), `stale_parts` e `stale_message`, e a saída humana destaca "PILHA
   DESATUALIZADA".

### Contrato do erro e do envelope

- `error.code`: **`STACK_STALE`**. Classe `StackStale(HarnessError)`, que **não** herda de
  `ScopeViolation` nem de `ScopeNotApproved` (nenhum `except` existente a engole) nem de
  `ExternalToolError`/`TargetError` (os executores não a tratam como parada de estágio).
- **Código de saída: 4** (`ExitCode.PREFLIGHT`), sem valor novo. A semântica é compatível ("verificação
  anterior à execução falhou") e o chamador distingue o caso pelo `error.code`. Não usamos o 3
  para não confundir com cerca ou aprovação, nem criamos um 9: nenhum chamador precisa de uma
  saída própria para algo que se resolve com `stack down` e `stack up`.
- Envelope: o de falha de sempre (`ok: false`, `error: {code, message, hint}`), sem campos novos.
  `message` diz que o perfil (`target.yml`) e/ou a aprovação mudou depois do `stack up` e que
  nada foi enviado ao alvo; `hint` manda rodar `hdast stack down` e `hdast stack up <produto>`
  (e, se a aprovação mudou, lembra que só uma pessoa aprova). O hash nunca aparece.
- `stack status` (`data`): campos **aditivos** `binding`, `stale_parts` (`profile`, `approval`,
  `binding`) e `stale_message`; ausentes (`null`/vazios) sem pilha.
- O `preflight` não converte `StackStale` em verificação reprovada: ela sobe até o tratador da
  CLI, com o envelope e a saída acima.

### Falha fechada

- Sem pilha gerenciada, ou com a pilha de outro produto: a conferência não decide (a pilha não é
  a deste comando; o resto do fluxo já falha como antes).
- Política da pilha ausente, grande demais ou inválida: `StackStale` com `stale_parts: ["binding"]`
  (o proxy também falharia fechado).
- Política sem `binding` (escrita à mão, sem fontes presas): `unbound`, nada a comparar.
- `target.yml` ou aprovação ausente, ilegível ou acima de 1 MiB no momento da conferência: conta
  como divergente.

### Limite conhecido

A conferência compara **conteúdo** (hash). O proxy compara também a identidade do arquivo (inode,
tamanho e data de modificação). Regravar o arquivo com o mesmo conteúdo, por exemplo salvar sem
mexer, muda a data, e o proxy nega mesmo com o hash igual. Esse caso só é pego pela
tradução do 403 (item 2). Também não há conferência no `scan` além do que o `run` já fez no
início.

## Alternativas consideradas

- **Recarregar o perfil no proxy (hash só dos blocos protegidos).** Descartada: afrouxa a
  garantia da V1.8 (o proxy passaria a confiar em campos "livres" calculados na CLI) e muda o
  contrato do proxy. O pedido foi manter a falha fechada.
- **Recriar a pilha automaticamente.** Descartada: `stack up` recria ZAP, proxy e alvo, perde a
  sessão e o estado do alvo, e exige trava e aprovação; decisão de uma pessoa ou do fluxo
  explícito da skill, não efeito colateral de um `preflight`.
- **Só documentar.** Descartada: o agente cego já tinha a documentação e ainda assim parou ou
  adivinhou. A mensagem precisa estar na falha.
- **Código de saída novo (9).** Descartada: ver acima.

## Consequências

- O primeiro `preflight` depois de editar o perfil com a pilha de pé falha com `STACK_STALE` e uma
  instrução exata, sem tráfego ao alvo e sem 403 enganoso no relatório.
- As skills passam a mandar recriar a pilha depois de editar `target.yml` com a pilha de pé.
- O fluxo continua exigindo `stack down` e `stack up`; quem edita só `data-rules.yml` ou
  `flows.yml` não é afetado (o proxy não prende esses arquivos).
- Há um novo valor de `error.code` e um adaptador de leitura (`StackBindingSource`), aditivos.
  Nenhum campo ou código existente muda; o teste de contrato e `docs/reference/` foram
  atualizados.
