# ADR 0053: caso e régua da avaliação V1.5.2

Estado: Proposto. Data: 2026-11-15.

## Decisão

A carta da Clínica autoriza explicitamente modo amplo, escrita de autorização entre contas,
escrita de valores proibidos e varredura de `not_found`. Ela entrega duas contas de médico e
uma orientação para obter nomes de documentos. Não autoriza varredura de upload. O caso antigo
fica em `clinica-piloto-estrito`, incluindo seu gabarito original. H9 passa a ser pontuável no
caso amplo, conforme a medição já existente; não é prova nova.

A régua lê os achados próprios do relatório (`proxy_signals` e `negative`) além dos anteriores.
Um match alternativo exige todos os campos declarados, inclusive categoria/técnica e operação.
Sinais são heurísticos e exigem triagem humana. A fidelidade e o aprovador recusam permissões
que o caso não autoriza, inclusive upload. Reduções são permitidas.

Cada `prepare` grava em `sealed/case.json` o gabarito completo, que `approve`, `collect` e
`score` utilizam; mudar um caso depois não altera uma rodada já preparada. Para rodadas antigas
sem snapshot, o coordenador informa `--case-file CAMINHO` para apontar o gabarito exato da
rodada; sem ele, o executor falha em vez de presumir uma carta. O arquivo não substitui um
lacre existente. O score registra caminho e SHA-256. O caso
`evals/cases/clinica-piloto-historico-terra-wide.yml` reconstrói a rodada Terra de 14/11 a
partir do caso estrito e do patch arquivado `attempts/02-main/coordinator/isolation-and-wide.patch`:
porta de estado, imagem do alvo e modo amplo. Essa reconstrução não se aplica automaticamente
a outras rodadas.
O lacre não versiona o código do avaliador: para reproduzir rigorosamente uma nota antiga,
também é necessário o código e as entradas e parâmetros daquela rodada. A evolução da régua
pode mudar notas quando aplicada a artefatos anteriores com um gabarito novo.

## Docker em comandos compostos

A documentação atual de [permissões do Claude Code](https://code.claude.com/docs/en/permissions)
diz que negações Bash valem para cada subcomando, inclusive em subshell, e que `:*` equivale
a ` *`; PowerShell também verifica comandos compostos. Assim, as regras existentes
`Bash(docker:*)` e `PowerShell(docker:*)` usam a sintaxe documentada. O `prepare` também grava
`Bash(*docker*)` e `PowerShell(*docker*)`: a documentação descreve `*` em qualquer posição e diz que
PowerShell usa a mesma forma de regra. A intenção é cobrir o comando composto observado, inclusive
Docker fora do início do texto; isso pode bloquear menções textuais inofensivas. O teste confere
apenas as regras gravadas, não o comportamento do Claude em execução. Não se provou que a
versão e o modo de permissão usados na rodada obedeciam a esse comportamento: a rodada passou
um comando composto. As regras não são uma fronteira de segurança e o transcript continua
sendo auditado; caminhos alternativos e versões diferentes não são abrangidos por esta prova.
