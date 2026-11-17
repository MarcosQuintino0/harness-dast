# 0104. Bloqueio local e liberação humana de mutações

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** V1.12.1; pendências de POST com resposta 500 na rodada `crapi-foco`

## Contexto

O diário abre uma intenção antes de enviar uma mutação. Uma resposta 5xx não demonstra
ausência de efeito, portanto a intenção permanece pendente. Na V1.12, o `probe`
seguinte interrompia o estágio inteiro por essa pendência, impedindo o `scan`, o
`authz` e o `negative` de conferir operações independentes. A orientação de apagar
um arquivo à mão também não oferecia liberação auditável pela CLI.

A trava do [ADR 0080](0080-diario-estagios.md) continua necessária: desconhecer o efeito
não autoriza repetir a mutação. Esta correção preserva a chave conservadora entre
estágios e a autorização de escopo, janela, métodos e limites.

## Decisão

Vamos distinguir pendência conhecida de falha do diário. Somente a primeira pula
a operação e conta afetadas e permite continuar as demais. `probe`, `authz`,
`negative`, `extra_checks`, o SSRF guiado/OAST já existente e o consumo de sementes históricas pelo `scan` respeitam
esse limite. O motivo público é `mutation_pending`, visível nos artefatos,
relatório e painel; ele nunca conta como alcance ou sucesso. Corrupção, dados
malformados e falhas de E/S continuam falhando de modo fechado.

Vamos oferecer `hdast mutation list` para leitura local por pessoa ou agente e
`hdast mutation release <id>` exclusivamente para uma pessoa em terminal
interativo. A liberação pede confirmação explícita de que a pessoa conferiu o
alvo, arquiva a entrada em `completed` com desfecho próprio de liberação humana e
registra o ato na auditoria. A segunda linha do próprio diário arquivado contém
`outcome: human_release`, `event: mutation_human_release` e `released_at` em ISO 8601;
o diário de comandos da CLI registra a invocação separadamente. A auditoria HTTP
`audit.jsonl` conserva seu contrato de decisões e respostas de requisições.
Sem TTY ou com modo JSON, a liberação é recusada.
Não haverá flag automática de confirmação. TTY e declaração não autenticam a
identidade da pessoa; a Parte B de `AGENTS.md` e a negação do Claude proíbem o agente.
A liberação mantém a mesma trava exclusiva de execução já usada por `run`,
`probe`, `scan`, `authz` e `negative`, incluindo o tempo do prompt. Assim não se
libera uma intenção enquanto a CLI ainda pode estar executando o pedido, nem se
inicia outro envio durante a liberação. A exclusão depende da mesma pasta de estado
e de processos que respeitem essa trava; uso direto da aplicação não a substitui.

Vamos acrescentar ao registro os metadados não sensíveis necessários: operação,
apelido da conta, método, `run_id` e horário. O identificador continua opaco e não
aceita caminhos. A listagem projeta somente esses dados e o identificador; não
expõe snapshot, corpo, credenciais ou conteúdo bruto do arquivo. Registros antigos
sem metadados permanecem bloqueantes, listáveis e liberáveis, com os campos
ausentes tratados como desconhecidos. Nenhuma migração libera intenção antiga.
O registro de intenção mantém `intent: mutation`, `previous_state` e o snapshot
seguro opcional do formato anterior, com `metadata` opcional contendo `operation_id`,
`account`, `method`, `run_id` e `started_at` com fuso. A listagem usa `{id, metadata}`.
Contexto que não cabe na projeção segura é omitido sem alterar a aceitação do
OpenAPI; a chave da trava continua usando a identidade original. Não se armazenam
corpos ou identificadores de recursos nesses metadados.

O caso de uso depende da nova porta `MutationReleaseStore`, um `Protocol` da
aplicação para listar e arquivar intenções nessa fronteira externa. O adaptador
`FileMutationJournal` a implementa e mantém a validação da intenção no domínio;
a CLI monta o armazenamento, o relógio, o terminal e a trava existentes.

Antes de liberar um registro legado, a CLI cria `completed` se necessário. O
desfecho é acrescentado e sincronizado antes de arquivar. Se o arquivamento falhar
depois dessa gravação, o arquivo permanece bloqueante e a leitura recusa o estado
inconsistente; não há desbloqueio silencioso ou recuperação automática de falha de disco.

Os testes de tentativas de rejeição em `extra_checks` usam a mesma chave de
operação, conta e método dos demais estágios. Resposta 5xx conserva a pendência;
não é sinal de limite de consumo nem motivo para repetir o POST.

`options.include_outcomes` do envelope mantém o contrato: `true` usa a lista
`scan.include_outcomes` do perfil, inclusive quando vazia, e `false` restringe a
`success`. A explicação documental não concede autorização para novas classes.

## Alternativas consideradas

- Interromper o estágio inteiro: preserva a trava, mas perde cobertura de operações
  independentes e foi a causa da falha de usabilidade.
- Repetir após 500 ou expirar pendências automaticamente: efeito desconhecido
  continua possível; essa alternativa remove a garantia de segurança.
- Remover o arquivo manualmente: perde o histórico e a auditoria e exige conhecer
  o formato interno do armazenamento.
- Marcar a operação como sucesso para continuar: distorce alcançabilidade e pode
  transformá-la em semente de ataque sem prova de alcance.

## Consequências e aceites

A execução pode terminar com lacunas explícitas, sem repetir a mutação pendente.
Uma pessoa resolve a incerteza por comando local, e registros históricos continuam
conservadores. Não há dependência nova ou mudança de escopo autorizado.

Os testes devem provar continuidade e ausência de reenvio por operação e conta,
apresentação de `mutation_pending`, listagem sem segredo, compatibilidade antiga,
recusa sem TTY e de entradas inválidas, ausentes ou malformadas. No crAPI local,
um `probe` deve deixar os POSTs 500 pendentes e o `run` seguinte deve varrer as
demais operações sem reenviá-los, com auditoria e duração registradas. Aceite
do ADR e integração permanecem decisões do dono.
