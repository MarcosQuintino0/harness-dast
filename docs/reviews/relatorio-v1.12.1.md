# Relatório da V1.12.1

Data: 2026-11-17. Base: `develop` em `b50f843`. Branch: `fix/v1-12-1-mutacao-pendente`.
Versão do pacote e lock: 1.12.1. Aceites e provas mínimas desta correção atendidos;
os seis gates locais passaram. Sem publicação de release nesta entrega.

## Entrega

A execução continua nas operações e contas independentes quando encontra uma mutação pendente.
O motivo `mutation_pending` aparece no probe, cobertura, relatório e painel, sem alcance ou
sucesso implícito. A reserva continua impedindo reenvio antes da liberação humana, inclusive
nas checagens adicionais e no scan sobre semente histórica. Corrupção ou falha de E/S continua
interrompendo o estágio. A decisão e a compatibilidade estão no
[ADR 0104](../adr/0104-bloqueio-local-e-liberacao-humana-de-mutacoes.md), proposto.

`hdast mutation list` projeta somente identificador e metadados não sensíveis; legado sem
contexto continua bloqueante. `hdast mutation release <id>` exige pessoa, TTY, confirmação
e trava exclusiva de execução; arquiva com `human_release` e evento `mutation_human_release`.
Os testes usam terminais simulados; o coordenador não executou o comando humano.

O caso `crapi-foco` v3 explicita `mechanic_api` do próprio workshop no contêiner isolado,
sem alterar caminhos, métodos, limites, capacidades ou detectabilidade. `options.include_outcomes`
mantém o contrato: `true` usa a lista do perfil, que pode estar vazia; `false` restringe a `success`.

## Provas e gates

Evidências externas: `C:\harness-dast-artefatos\v1-12-1\`.

CrAPI local, teste `test_lab_mutation_pending.py`: aprovado em 274,04 s de pytest
(276,376 s de parede). Probe inicial `2026-11-17T22-45-26Z-crapi-8c33`: `check_otp_v2`
e `validate_coupon`, conta `user_a`, deram 500, uma tentativa cada. O run seguinte
`2026-11-17T22-45-33Z-crapi-d6e1` concluiu em 47,703 s de processo, saída 0,
com todos os seis estágios `ok`. Ambos os POSTs ficaram `mutation_pending`,
sem status e com zero tentativas. Houve varredura completa de `get_vehicles` e
`get_products`; `mutation_pending` apareceu no relatório e no painel.

Auditoria da CLI: duas decisões `denied/mutation_pending` e nenhum resultado de POST
bloqueado. Auditoria do proxy de toda a prova: exatamente um envio de cada POST,
o do primeiro probe. A aprovação permaneceu idêntica, o vínculo ficou `fresh`
e as pilhas foram removidas. Resumo sanitizado: `crapi-proof-summary.json`;
métricas: `metrics-crapi-diagnostic/v1121-mutation-pending.json`.
O manifesto confirma harness 1.12.1 e ZAP 2.17.0. O crAPI é 1.1.6-rc8,
com imagens fixadas por digest em `lab/crapi/compose.yaml`; o proxy foi reconstruído
pelo `stack up`, sem mudança de seus recursos ou do limite de 200 ms.

As tentativas anteriores são preservadas: duas falharam porque o helper de auditoria
regravava a aprovação descartável (corrigido no teste). Uma terceira passou o novo
probe, mas o proxy interrompeu o scan com `STACK_STALE/approval_changed`. O hash da
aprovação continuava igual ao vínculo quando conferido depois; a categoria da vigia
não foi coletada nessa tentativa. Uma repetição verde não demonstra a correção dessa
intermitência, que permanece fora do escopo desta versão.

Regressão dirigida: `uv run pytest -m regressao_dirigida` aprovado com 14 testes,
26 combinações inaplicáveis puladas e 11.420 desmarcados, em **750,99 s de pytest**
(12min30,99s; 754,712 s de parede). Resumo em `regression-proof-summary.json`.

| Cenário | Execução | Tempo operacional | Resultado |
| --- | --- | --- | --- |
| Clínica vulnerável | `2026-11-17T22-49-30Z-clinica-piloto-a0fd` | 443,6 s | H1 a H10 achadas |
| Clínica segura | `2026-11-17T22-56-51Z-clinica-piloto-987f` | 189,0 s | Zero achado de autorização |
| VAmPI vulnerável, autorização | `2026-11-17T22-59-57Z-vampi-5e9b` | 65,5 s no cenário todo | V3 achada |
| VAmPI vulnerável, scan | `2026-11-17T23-00-03Z-vampi-80fd` | Incluído nos 65,5 s | V1 achada |

Tempos operacionais excluem a descida e parte da coleta; o total do pytest as inclui.
A primeira tentativa da regressão teve 4 aprovações, 23 pulos e 13 erros em 436,57 s:
o fixture da Clínica vulnerável parou no probe com `STACK_STALE`. A repetição preservou
as asserções e os limites e coletou o diagnóstico antes de descer cada pilha.

| Gate final | Resultado | Duração de parede |
| --- | --- | --- |
| `uv run ruff check .` | Passou | 1,182 s |
| `uv run ruff format --check .` | Passou | 1,182 s |
| `uv run mypy` | Passou | 2,571 s |
| `uv run lint-imports` | Passou, 6 contratos preservados | 0,916 s |
| `uv run vulture` | Passou | 2,830 s |
| `uv run pytest` | 11.128 passaram, 5 pulados, 327 desmarcados | 383,063 s |

O tempo interno do pytest foi 378,84 s (6min18,84s). `uv run mypy --platform linux`
também passou, em 16,097 s. Evidências: `final-*.log` e metadados `final-*.json`.

A primeira suíte completa teve 11.108 aprovações, 3 falhas e 5 pulos em 446,57 s.
As falhas de texto da skill, versão no changelog e tradução dos comandos foram
corrigidas; os 29 testes focados das falhas e os 34 de documentação passaram.
Não houve afrouxamento de testes, import-linter, gitleaks ou hooks.

## Revisão e commits

Programação por dois agentes GPT 6.1 Terra high em worktrees próprias, no máximo
dois simultâneos; integração serial e autorrevisão pela coordenação. A revisão
cruzada corrigiu contagens de pedidos não enviados, aviso de efeito desconhecido,
auditoria anterior ao envio, compatibilidade de legado e a concorrência da liberação.

Commits principais: diário/CLI `5ad99bb`, metadados `9b63021`, legado `ab1c1e7`,
política `1a8176a`, auditoria `93102a0`, consumidores `d28381e`, trava humana `4cff488`,
OAST `ff186c7` e versão `2286917`. Prova crAPI `a5b692d`, preservação da aprovação
`193e92a`, diagnóstico `6185941` e regressão diagnosticada `2dfc909`. A lista completa
da branch fica em `commits.txt` na pasta externa de evidências. ADR 0104 permanece proposto.

## Limites

- Só laboratório local, dados sintéticos e aprovações descartáveis do suporte de integração.
- Sem nova rodada cega v3, nota de avaliação ou varredura `lab_full` das APIs inteiras.
  Esta entrega atende às provas dirigidas solicitadas; não mede cobertura integral do produto.
- Sem produto real, release publicada, PR ou merge; ADR permanece proposto.
- O inventário Compose estava vazio ao encerrar o laboratório, às 23:04:56 UTC;
  a trava `codex-v1-12-1` foi removida após conferir seu dono. CI remoto e uma
  execução humana real de `mutation release` não foram realizados.
- TTY não autentica a pessoa. A exclusão de liberação depende da mesma pasta de estado e de
  processos que respeitem a trava; acesso direto à aplicação não participa dessa exclusão.
- Falha ou queda entre append sincronizado e rename deixa o arquivo bloqueante com duas linhas;
  a CLI recusa o estado inconsistente e não faz reparação automática. Teste de falha injetada cobre
  essa recusa; não há prova de durabilidade de metadados após perda de energia.
