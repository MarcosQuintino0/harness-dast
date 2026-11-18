# Estratégia de testes

Este documento define como o projeto é testado. Regras resumidas para agentes estão em [AGENTS.md](../../AGENTS.md). O que já existe e o que é planejado está em [roadmap.md](../roadmap.md#tabela-de-status).

## Níveis

| Nível | O que valida | Dependências | Quando roda | Status |
| --- | --- | --- | --- | --- |
| Unitário | Regras de `domain`, `config`, `observability` e `cli`. Inclui testes baseados em propriedades (hypothesis) para escopo, caminhos, janelas e sobrescritas. Casos de uso com portas falsas (`tests/fakes/`) | Nenhuma | A cada commit e no CI | **Existe.** `tests/unit/` espelha `src/` (`domain`, `application`, `adapters`, `cli`, `config`, `observability`, `evals`, `lab`) |
| Suíte de QA independente (`*_qa.py`) | Testes escritos por um revisor que não escreveu o código, a partir da especificação: ataques de parser differential, propriedades com oráculo próprio, limites, redação de logs. Convivem com os unitários | Nenhuma | A cada commit e no CI | **Existe** (revisão de 2026-11-13; veja abaixo) |
| Integração | A CLI real (`python -m harness_dast`) contra o ZAP 2.17, o proxy de escopo e os alvos de laboratório reais, em Docker | Docker | Manual, antes de release (não roda no pull request) | **Existe** (`tests/integration/`, marcador `integration`; pulados sem Docker). Seção abaixo |
| Contrato | Envelope JSON e códigos de saída de cada comando; schema do perfil; suíte única que todo adaptador de `Scanner` precisa passar | Nenhuma ou Docker | Em todo pull request | **Parcial.** `tests/contract/` tem um arquivo por comando (`test_cli_*.py`: envelope, códigos de saída, `--json`), o modelo de perfil (`test_template_profile.py`), a conformidade dos documentos (`test_docs_conformance_qa.py`), os links dos documentos (`test_docs_links.py`), as skills e os guias (`test_skills_and_guides.py`) e o isolamento do estado (`test_state_isolation.py`). A suíte única que todo adaptador de `Scanner` precisa passar ainda não existe (só há o adaptador do ZAP) |
| Ponta a ponta | `hdast run` contra o VAmPI e a Clínica Piloto do lab: achado conhecido presente, zero requisição fora do escopo, nenhum segredo nos artefatos, regras removidas, trava de emergência e limpeza no Oracle | Docker, lab | Antes de release | **Existe**, dentro de `tests/integration/test_lab_run.py` e `test_cleanup_oracle.py`; não há marcador `e2e` separado |
| Avaliação das skills | Roteiro manual: o agente, partindo de um Swagger do lab, chega a um perfil válido e à alcançabilidade esperada | Claude Code | Antes de release e ao mudar skill | Roteiro escrito ([avaliacao-das-skills.md](avaliacao-das-skills.md)); a confirmar se alguma pessoa o executou |
| Avaliação cega (evals) | Agentes de teste sem contexto seguem o README contra o lab, com nota automática e rastro completo (seção abaixo) | Claude Code, Docker, lab | Ao fim da V1 e a cada mudança de skill, mensagem de erro ou trava | **Existe** como código e testes (M6); seis rodadas feitas em 2026-11-13 (cinco na 1.0 e uma na 1.1), por subagentes dentro de uma cópia cega e não com `claude -p`: [rodadas](../arquivo/reviews/2026-11-13-rodadas-cegas.md) e [rodada da V1.1](../arquivo/reviews/2026-11-13-rodada-cega-v1-1.md) |

## Como rodar

Até que degrau testar cada mudança (checagens, unitários, ataque direcionado, varredura completa, rodada cega) e os comandos de cada um: [escada-de-testes.md](escada-de-testes.md).

```bash
uv run pytest                  # só os testes que não exigem Docker
uv run pytest -m integration   # exige Docker; horas (cada varredura leva 12 a 30 min)
uv run pytest -m integration tests/integration/test_lab_vampi.py   # só alcançabilidade (minutos)
uv run pytest -m lab_fast                 # nível RÁPIDO (ciclo conserta-e-roda): poucos endpoints, uma pilha por grupo
HDAST_IT_METRICS_DIR=./medidas uv run pytest -m lab_full   # nível COMPLETO: todos os endpoints, política padrão, vulnerável e seguro; grava as medidas
```

Por padrão, `pytest` exclui os marcadores `integration` e `e2e` (configurado em `pyproject.toml`). Os marcadores `integration`, `contract` e `e2e` existem. Passar `-m` na linha de comando substitui o filtro padrão.

Antes de abrir um pull request, rode as seis verificações listadas na [Parte A do AGENTS.md](../../AGENTS.md#antes-de-terminar-rode).

### Dois níveis de integração contra o lab

| Nível | Marcador | O que roda | Para quê |
| --- | --- | --- | --- |
| Rápido | `lab_fast` (e `integration`) | `test_lab_fast.py`: sonda e varre 2 operações do piloto (uma escrita com XSRF, uma leitura com parâmetro, escolhidas pelo mecanismo e não por falha plantada) e confere XSRF em toda escrita do varredor, token em toda requisição, zero segredo nos artefatos, regras do Replacer removidas e as negações do proxy contadas; uma varredura do VAmPI a 5 req/s prova que o limitador de taxa segura (média ate 5,25 e pico até 6 req/s na auditoria do proxy); parada de emergência durante o `run`; limpeza no Oracle depois de `run` mais uma varredura de duas escritas; `test_lab_path_scope.py` (V1.1: 44 formas de caminho do ADR 0026 contra uma isca (caminho proibido do laboratório) pelo proxy real nos modos estrito e amplo, `detail` granular, caminho byte a byte e atraso do endpoint lento) e `test_lab_path_differential.py` (cerca x servidor: o que o Spring e o Flask roteiam de fato contra as leituras de `domain/widepath.py`, mais a coerção numérica do parâmetro) | Ciclo conserta-e-roda e rodadas que não dão nota |
| Completo | `lab_full` (e `integration`) | `test_lab_run.py`: `hdast run` com todos os endpoints, política padrão do ZAP, VAmPI e piloto em modo vulnerável e seguro, comparação entre execuções | Comparação com o gabarito; uma vez por alvo e modo, no fim |

O nível rápido NÃO valida: cobertura de todas as operações, a política padrão sobre o alvo inteiro, a comparação com o gabarito e o comportamento de varreduras longas (renovação de token, prazo, saúde do alvo sob carga). Escolher regras ou endpoints olhando o gabarito das falhas plantadas é proibido no nível completo. Os testes de alcançabilidade (`test_lab_vampi.py`, `test_lab_pilot.py`) e `test_cleanup_oracle.py` só levam `integration`.

## Dublês: quando usar e quando evitar

- **Falsos em memória** (em `tests/fakes/`) são o padrão para testar casos de uso. Têm comportamento, não só retorno fixo.
- **Mocks** só para injetar falha difícil de provocar (queda do ZAP no meio da varredura, tempo esgotado).
- **Não simular o que não é nosso sem contrato.** Respostas simuladas do ZAP vêm de capturas reais e têm um teste de integração que confirma o formato contra o ZAP verdadeiro.
- **Fixtures** são dados reais: Swaggers do lab, alertas capturados do ZAP, perfis válidos e inválidos.
- **Arquivos de referência** para o plano de varredura gerado e para o relatório em Markdown. Mudança neles aparece no diff.
- Nunca simular o módulo que está sendo testado, nem verificar chamadas internas em vez do resultado.

## Organização e nomes

- `tests/unit/` espelha `src/harness_dast/`.
- `tests/unit/claude_hooks/test_guard.py` carrega o hook de `.claude/hooks/` por `importlib`. As entradas JSON são sintéticas e os comandos são apenas inspecionados. A suíte também confere as negações legadas e o registro em `.claude/settings.json`. O mypy e o vulture incluem o diretório do hook em suas checagens.
- Arquivo: `test_NOME_DO_MODULO.py`.
- Função: `test_COMPORTAMENTO_quando_CONDICAO`. Exemplo: `test_rejects_request_when_redirect_leaves_scope`.
- Estrutura de cada teste: preparar, agir, verificar. Uma razão para falhar por teste.
- Nenhum teste depende de ordem, de relógio real ou de rede externa. Relógio e aleatoriedade entram por parâmetro ou porta.

## Cobertura como alarme, não como meta

Pisos propostos (AD-10):

| Alvo | Piso |
| --- | --- |
| `domain` | 95% de ramos |
| `application` | 85% de ramos |
| Linhas alteradas de cada pull request | 90% |
| `adapters` | Sem piso de linha; obrigação de um teste de integração ou de contrato |

Percentual global alto incentiva teste artificial; por isso os pisos são por camada. O número não é o objetivo: na revisão vale o critério abaixo. Os valores podem ser calibrados no fim do M2.

A verificação automática existe no CI (`.github/scripts/check_coverage_floors.py` e `diff-cover`). Achado A-05 (corrigido): o script ignorava qualquer camada sem instrução medida, o que deixava passar um prefixo errado ou um `coverage.json` quebrado. Agora só uma pasta que tem apenas `__init__.py` (como `application` hoje) é ignorada, com aviso; prefixo inexistente ou pasta com código e nada medido falham. Na revisão de 2026-11-13 a cobertura medida era: `domain` 100%, `config` 100%, `observability` 100%, `cli` 96,3%. Veja o [roadmap](../roadmap.md#tabela-de-status) e a [resposta à revisão](../arquivo/reviews/2026-11-13-qa-m1-m2-resposta.md).

## Uma implementação está suficientemente testada quando

- [ ] Cada regra de negócio nova tem um teste que falha se a regra for removida.
- [ ] Cada caso de uso tem o caminho feliz e pelo menos um caso negativo por tipo de falha de cada porta que usa.
- [ ] Cada entrada externa tem teste com dado inválido, ausente e malformado.
- [ ] Cada correção de defeito chega com um teste que reproduzia o defeito.
- [ ] Cada adaptador novo passa na suíte de contrato da sua porta.
- [ ] Mudança no envelope JSON ou no schema do perfil atualiza o teste de contrato e a versão do schema.
- [ ] Nenhum teste depende de ordem, de relógio real ou de rede externa.

## Casos obrigatórios do ScopeGuard

O `ScopeGuard` (**implementado no domínio**, `domain/scope.py`; chamado por `preflight` e `probe` via `approve`) é o componente de maior risco do projeto e recebe tratamento à parte. Ele valida toda requisição contra a lista permitida e falha fechado. Os casos abaixo são obrigatórios; todos têm teste em `tests/unit/domain/` (`test_scope.py`, `test_scope_qa.py`, `test_urlnorm*.py`, `test_host.py`, `test_pathpattern*.py`, `test_window*.py`).

- Redirecionamento para host fora da lista.
- Host com usuário embutido (`permitido.com@outro.com`).
- IP literal, IPv6, endereço de metadados da nuvem e redes privadas.
- Diferença de maiúsculas, ponto final no host, porta diferente, domínio internacionalizado.
- Caminho com `..` e com codificação dupla.
- Caminho com decoração que o servidor remove antes de rotear: `;x=1`, ponto final, espaço final, em forma crua e codificada (achado A-01). Sem isso, `deny_paths` é contornável.
- Método não permitido para o caminho.
- Janela fechada, janela que cruza a meia-noite e mudança de horário de verão.
- Propriedade: nenhuma requisição gerada aleatoriamente passa sem casar com uma regra explícita.

A "janela fechada no meio da execução" depende de quem executa (a conferência a cada lote é do M4 e M5); o domínio só responde se a janela está aberta num instante dado.

## Regressão

- **Linha de base do lab:** o conjunto de achados esperados no VAmPI fica versionado. O teste de ponta a ponta falha se um achado conhecido sumir.
- **Falso positivo:** o VAmPI em modo seguro não pode gerar achado de severidade alta.
- **Alcançabilidade:** o lab tem um mínimo; queda abaixo dele quebra o teste.
- **Imagem do ZAP:** atualizar a imagem é uma mudança como outra qualquer, em pull request próprio, com integração e ponta a ponta.
- **Defeito corrigido:** chega com o teste que o reproduzia.

Os itens de regressão contra o lab dependem do `lab/` e do `compose.yaml` e existem em `tests/integration/` (níveis `lab_fast` e `lab_full`, fora do `uv run pytest` padrão).

## Avaliação das skills

Roteiro manual, antes de release e ao mudar uma skill: partindo de um Swagger do lab, o agente chega a um perfil válido e à alcançabilidade esperada. Escrito em [avaliacao-das-skills.md](avaliacao-das-skills.md) (M6). A avaliação cega, abaixo, complementa o roteiro com repetição e nota automática.

## Avaliação cega (evals)

> **Implementado como código e testes (M6); seis rodadas contra o lab foram feitas em 2026-11-13** (resultados em [../arquivo/reviews/2026-11-13-rodadas-cegas.md](../arquivo/reviews/2026-11-13-rodadas-cegas.md) e [../arquivo/reviews/2026-11-13-rodada-cega-v1-1.md](../arquivo/reviews/2026-11-13-rodada-cega-v1-1.md)); faltam a forma fiel (`claude -p` com as permissões da cópia) e repetições por caso. O executor, os casos, a regra de nota e o passo a passo estão em [../evals/README.md](../../evals/README.md); o executor é testado em `tests/unit/evals/` com artefatos de exemplo, sem Docker. Decisão e alternativas: [ADR 0014](../decisoes/0014-avaliacao-cega-como-eval.md).

Uma **eval** é um teste automático de um sistema de IA: um caso com entrada e resposta esperada, rodado várias vezes, com nota calculada por regra. Ao fim da V1, a ferramenta é avaliada por agentes de teste **cegos**.

**O agente cego.** Um agente novo, sem contexto além do repositório. Recebe só a instrução de seguir o README e testar a API do lab. Não é dito quais vulnerabilidades existem nem se o alvo está em modo vulnerável ou seguro. O modo é sorteado antes de cada rodada e guardado fora do alcance do agente.

**Casos e repetição.** Um caso é alvo + modo + gabarito.

| Alvo | Para que serve |
| --- | --- |
| VAmPI (primeiro) | Linha de base e regressão. Por ser público, provavelmente está na memória dos modelos, então o resultado pode ser otimista |
| API pequena própria, com falhas plantadas (a Clínica Piloto, em `lab/`) | Mede o que o modelo não memorizou. O gabarito é nosso |
| OWASP crAPI (`lab/crapi/`, só vulnerável) | Alvo maior, com `multipart`; nenhum desafio do gabarito é detectável pelo ZAP, então os achados ficam fora da nota |

Cada caso roda várias vezes, porque o resultado varia entre execuções. O número de repetições e o orçamento por rodada ainda não foram definidos (item aberto no [roadmap](../roadmap.md#itens-em-aberto)); até agora cada caso e modo rodou uma ou duas vezes (a segunda do VAmPI foi depois de uma correção).

**Nota automática por execução.**

| Medida | Como se calcula | Meta |
| --- | --- | --- |
| Alcançabilidade | Parcela das operações do OpenAPI que respondem 2xx | Acima da importação crua do OpenAPI (M3) |
| Falhas conhecidas encontradas | Achados contra o gabarito | Medido, sem meta fixa na V1 |
| Falsos alarmes | Achados de severidade alta em modo seguro | Zero |
| Requisições fora do escopo | Trilha de auditoria contra o escopo do perfil | **Zero**; qualquer valor acima é falha |
| Custo e tempo | Tokens e duração da execução | Medido |

**Rastro completo de cada execução.** Para poder depurar uma falha, cada execução guarda:

1. a transcrição do agente: mensagens, chamadas de ferramenta e resultados, em ordem (gravada quando o agente roda de forma não interativa);
2. toda versão do perfil e das regras de dados que ele escreveu;
3. a trilha de auditoria (`audit.jsonl`) e o manifesto (`manifest.json`) do harness;
4. um registro de decisões por execução, que as skills **exigem** que o agente escreva: cada decisão importante e o motivo.

O raciocínio interno do modelo pode vir resumido ou incompleto, e não deve ser usado como fonte. O registro de decisões é a fonte.

**Triagem de falhas.** Cada falha de eval cai em exatamente uma causa, com destino fixo:

| Causa | Destino |
| --- | --- |
| A documentação ou a skill não explicou | Corrigir o texto |
| O agente tentou algo que não devia e a ferramenta deixou | Nova trava em código, com teste (nunca só texto) |
| A ferramenta devolveu um erro que o agente não soube interpretar | Melhorar a mensagem e a dica do erro |

Toda falha corrigida vira um caso permanente da suíte.

## Análise de mutação

Em 2026-11-13 a revisão de QA aplicou 40 mutantes à mão (uma alteração pequena no código por vez, para ver se algum teste falha). A suíte existente matou 36. Sobreviveram quatro, o que mostra que os tetos de carga e a imutabilidade das settings não eram testados nos valores:

- `MAX_REQUESTS_PER_SECOND` de 50 para 500;
- `MAX_DURATION_MINUTES` de 480 para 4800;
- `MAX_ZAP_THREADS_PER_HOST` de 8 para 80;
- `Settings` deixando de ser `frozen`.

Os testes `*_qa.py` matam esses quatro. Os testes de QA, por sua vez, deixaram passar sete mutantes que a suíte existente matou; em cinco deles a defesa é redundante com outra camada de validação. A análise foi pontual e não é um gate do CI. Detalhes na seção 6 do [relatório](../arquivo/reviews/2026-11-13-qa-m1-m2.md).

## O que existe hoje

- `tests/unit/` espelhando `src/harness_dast/` (`adapters`, `application`, `cli`, `config`, `domain`, `evals`, `lab`, `observability`), com um arquivo `test_<módulo>.py` por módulo e, ao lado, o `test_<módulo>_qa.py` da suíte de QA.
- `tests/contract/`: um arquivo por comando e por assunto (envelope, códigos de saída, documentos, links, skills e guias); a lista está em [Níveis](#níveis).
- `tests/unit/test_coverage_floors_script.py`: testa o script de pisos de cobertura do CI.
- Na revisão de 2026-11-13 eram cerca de 1,7 mil testes, sem Docker nem rede. Esse número envelhece; a fonte é o próprio diretório `tests/`.
- Desde o M3: falsos com comportamento em `tests/fakes/` (`probe_ports.py`, `rig.py`, `runtime.py`) para os casos de uso `spec inspect`, `preflight` e `probe`; servidor HTTP real em 127.0.0.1 (`tests/fakes/local_server.py`) para o cliente do alvo, as duas estratégias de autenticação com CSRF e o cliente da API do ZAP (contra um ZAP falso com as formas de resposta do spike); contratos dos três comandos em `tests/contract/test_cli_probe_commands.py`; e a afirmação central do projeto como regressão (`tests/unit/application/test_probe_vampi.py`: alcançabilidade com regras acima da sem regras, sobre o OpenAPI real do VAmPI).
- Desde o M4/M5: `tests/integration/` roda a CLI como processo contra o lab real. `test_lab_vampi.py` e `test_lab_pilot.py` (alcançabilidade do `probe`, XSRF, contas, vencimento do token), `test_lab_run.py` (`hdast run` completo: VAmPI vulnerável e seguro com comparação, Clínica Piloto vulnerável e seguro, trava de emergência durante a varredura; afirma só o que é robusto e **mede** o que o ZAP achou, sem ajustar ao gabarito) e `test_cleanup_oracle.py` e `test_run_cleanup_oracle.py` (limpeza contra um Oracle Free real, a segunda depois de um `hdast run`). Apoio em `lab_support.py` e `run_support.py`. Cada chamada tem prazo; sem Docker (ou sem a imagem do Oracle) o teste é pulado.
- Desde o M6: `tests/unit/evals/` (executor da avaliação cega, com artefatos de exemplo) e `tests/contract/test_skills_and_guides.py` (comandos e flags citados em skills, subagentes e guias existem na CLI real; permissões e forma das skills).
- Mutação à mão no M3 (cada mutante quebrou ao menos um teste): `approve` sem `ensure_allowed`; `deny_paths` sem pular; janela sem rechecagem; prazo sem checagem; trecho de resposta sem redação; token não registrado no redator; cabeçalho CSRF em todos os métodos; `DELETE` sem pular; novo login sem teto; redirecionamento seguido; decisão de auditoria gravada depois do envio.

A suíte `*_qa.py` nasceu com 29 testes que demonstravam defeitos; eles guiaram a [rodada de correção](../arquivo/reviews/2026-11-13-qa-m1-m2-resposta.md).
