# 0038. Teste de autorização ligado por padrão no `run` e escrita só com a carta

- **Status:** Proposto
- **Data:** 2026-11-14
- **Origem:** rodada cega da Clínica Piloto (o agente não rodou `hdast run --authz` e as falhas H5, H6 e H7 não foram achadas), plano do ciclo V1.3 a V1.8 (versão 1.4). Altera o [ADR 0027](0027-teste-de-autorizacao-entre-contas.md) (estágio opcional) e usa a carta do [ADR 0036](0036-carta-estruturada.md) e a aprovação do [ADR 0037](0037-aprovacao-humana-do-escopo.md); não os substitui

## Contexto

O ADR 0027 criou o estágio `authz` como opcional e desligado por padrão (`--authz`), porque uma das quatro verificações, a atribuição em massa (`mass_assignment`), **escreve** no alvo e o agente não tinha a concordância de uma pessoa para isso. Na rodada cega o agente, sem essa concordância, não ligou o estágio; com isso as verificações que só **leem** (`horizontal`, `excessive_data` e `vertical` em `GET`/`HEAD`) também ficaram desligadas, e as falhas de autorização que o ZAP não detecta passaram em branco. Um estágio de leitura não deveria depender da mesma permissão que um estágio de escrita.

Restrições: a escrita no alvo é um alargamento e só pode vir de quem autoriza (a carta do dono do produto), nunca de flag ou do agente; flags só reduzem; o estágio ligado por padrão não pode derrubar o `run` quando faltam contas ou pedidos; mudar o perfil para ligar a escrita tem que exigir nova aprovação humana.

## Decisão

Vamos:

1. **Ligar o estágio `authz` por padrão no `hdast run`.** Por padrão ele só lê: `horizontal`, `excessive_data` e `vertical` restrita aos métodos `GET` e `HEAD`. A flag nova `--no-authz` o pula (é redução; o estágio consta como `skipped` em `run.json`). `--authz` continua aceito por compatibilidade e é redundante. Com `--skip-scan` o estágio segue `skipped`, como antes. `RunRequest.authz` passa a valer `True` por padrão.
2. **Escrita só com a carta.** O campo novo `AuthzConfig.allow_writes: bool = False` (`authz.allow_writes` no `target.yml`) libera a atribuição em massa e os métodos de escrita (`POST`, `PUT`, `PATCH`) de `authz.vertical_methods`. Sem ele, em `hdast authz` e no `run`:
   - `mass_assignment` não envia nada e vai para `not_tested` (`reason: writes_not_authorized`, mensagem "escrita não autorizada pela carta: authz.allow_writes"); o resumo da verificação sai `skipped`;
   - os métodos de escrita de `vertical_methods` saem do plano, com uma nota `writes_not_authorized` da verificação `vertical`;
   - `--check mass_assignment` **não liga** a escrita: o resultado é o mesmo `not_tested`, não um erro (flags só reduzem).
3. **Campo novo na carta estruturada:** `attack.allow_authz_writes` (um `Answer` booleano). Ausente, nulo, `desconhecido` ou `false` valem `false` e não geram pendência ("não sei" é "não"). `true` só passa com `source: carta` **e** `quote` não vazia (`AUTHZ_WRITES_NEEDS_LETTER` caso contrário); valor que não seja booleano é `INVALID_VALUE` e nunca vira `true`. Decisão sobre a `quote`: exigimos, igual ao `path_mode: wide`, porque a escrita é um alargamento que só vale se a carta assinada o disser; a frase fica registrada no `carta.yml` e dá à pessoa que aprova o escopo algo a conferir com o dono do produto. `source: pessoa` não basta: a entrevista não autoriza o que a carta não autoriza.
4. **Geração.** `hdast init --from-letter` escreve `authz:\n  allow_writes: true` no `target.yml` **só** quando a carta autoriza (o bloco não existe quando é `false`, e os perfis gerados sem o campo continuam byte a byte iguais aos de antes; com `true` o cabeçalho ganha uma linha). `authz.allow_writes` entra em `generated_blocks`. A carta pronta traz o aviso `AUTHZ_WRITES_AUTHORIZED` (`data.warnings`, ADR 0036), que não bloqueia: o agente o mostra e a pessoa confirma com o dono do produto.
5. **Estágio que não derruba o `run`.** O estágio do `run` pede `tolerate_missing_exchanges`: se `exchanges.json` estiver ausente ou ilegível, ou vazio, ou se não houver contas para comparar, cada verificação vai para `not_tested` com o motivo (`exchanges_unavailable`, `no_exchanges`, `no_peer_account`...). O comando `hdast authz` solto continua recusando `exchanges.json` ausente (erro de configuração). Produto da execução diferente do perfil continua sendo erro nos dois.
6. **Impressão digital da aprovação (ADR 0037).** O bloco `authz` já entra inteiro no cálculo, então mudar `allow_writes` já exigiria nova aprovação. Para que a chave nova não invalide toda aprovação existente, o cálculo deixa de fora, **de forma genérica**, as chaves do `authz` que não existiam na versão 2 do cálculo enquanto estiverem no valor padrão: `allow_writes: false` (ou ausente) dá a mesma impressão digital de antes, e `allow_writes: true` muda a impressão digital do bloco `authz` e exige aprovar de novo. Chaves futuras do `authz` seguem a mesma regra. A versão do cálculo **não muda** (perfil antigo, mesma impressão digital). O resumo que a pessoa lê no `hdast profile approve` mostra a linha "ESCRITA AUTORIZADA" quando `allow_writes` é `true`.

Contrato (aditivo): `hdast run` ganha `--no-authz` e o estágio vem ligado; o `target.yml` ganha `authz.allow_writes`; o `carta.yml` ganha `attack.allow_authz_writes`; o envelope do `init --from-letter` ganha o código de aviso `AUTHZ_WRITES_AUTHORIZED`, o código de pendência `AUTHZ_WRITES_NEEDS_LETTER` e o bloco gerado `authz.allow_writes`; `authz.json` ganha os motivos `writes_not_authorized`, `no_exchanges` e `exchanges_unavailable`. Sem mudança de `schema_version`, de códigos de saída nem de envelope.

## Alternativas consideradas

- **Manter o estágio opcional e só orientar o agente a ligá-lo.** É o que falhou na rodada cega: depende de o agente decidir. Descartada.
- **Ligar tudo por padrão, inclusive a escrita.** Escrever no alvo é alargamento; sem a carta seria o agente ou uma flag decidindo. Descartada.
- **Flag `--authz-writes` para liberar a escrita.** Contraria "flags só reduzem" e deixaria o agente liberar o que só o dono do produto pode. Descartada.
- **Aceitar `source: pessoa` para a escrita.** A pessoa na entrevista pode ser quem opera, não quem autoriza. A carta é a fonte. Descartada.
- **Não exigir `quote`.** Perderia o que a pessoa confere ao aprovar o escopo e destoaria do `path_mode: wide`. Descartada.
- **Subir a versão do cálculo da impressão digital.** Invalidaria toda aprovação existente à toa. Descartada em favor de omitir chaves novas no padrão.
- **Deixar o estágio falhar o `run` quando falta conta ou pedido.** Um estágio ligado por padrão que derruba a execução inteira por falta de segunda conta tornaria o padrão inviável. Descartada; o motivo vai para `not_tested`.

## Consequências

- O `run` passa a mandar requisições a mais por padrão (linhas de base e repetições, contadas no ritmo, no prazo e no orçamento de login) e a achar BOLA, dado a mais e BFLA de leitura sem ninguém lembrar de ligar o estágio. Quem não quer usa `--no-authz`.
- A atribuição em massa deixa de rodar sem a carta: a falha H6 do laboratório só aparece se o perfil do laboratório declarar `authz.allow_writes: true` (a carta do laboratório precisa dizê-lo) e a pessoa aprovar de novo.
- Textos que dizem "opcional, `--authz`" (relatório, `doctor`, painel) precisam acompanhar; os `not_tested` novos aparecem no relatório pelo caminho que já existe.
- O tempo do `run` cresce com o `authz`; o prazo único da execução continua valendo.
- Limites mantidos: o estágio só repete o que o `probe` provou, nunca `DELETE`, e a restauração da atribuição em massa é de melhor esforço.
