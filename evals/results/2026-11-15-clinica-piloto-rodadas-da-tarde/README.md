# Clínica Piloto: rodadas cegas da tarde de 2026-11-15 (V1.5.2 e V1.5.3)

As três rodadas abaixo vieram depois da rodada da manhã ([2026-11-15-clinica-piloto-sonnet55-medium-wide](../2026-11-15-clinica-piloto-sonnet55-medium-wide/README.md)) e dos consertos que ela motivou. Todas usaram o mesmo método:
- **Agente:** Claude Code em modo não interativo (`claude -p`), `--model sonnet`, que respondeu como `claude-sonnet-5-5` em todas as respostas.
- **Configuração:** `--effort medium`, `--permission-mode auto` e as duas permissões do `hdast` passadas por `--allowedTools`.
- **Pedido:** o texto exato do roteiro (`evals/README.md`).
- **Intervenção do coordenador:** só a aprovação do escopo (`evals.runner approve`).
- **Caso:** a carta nova da V1.5.2 (modo amplo, escrita, valores proibidos e varredura de `not_found` autorizados, segunda conta de médico) e, na última rodada, a regra dos papéis compartilhados da V1.5.3.

Os rastros completos e os transcripts ficam fora do repositório, em `C:/harness-dast-artefatos/rodadas-cegas/`. As medições estão em [../../measurements](../../measurements/README.md), nas pastas `2026-11-15-clinica-piloto-sonnet55-v152-*` e `-v153-vulneravel`.

## Resultado

| Rodada | Versão | Modo | Nota | O que aconteceu |
| --- | --- | --- | --- | --- |
| Semente 16 | 1.5.2 | Seguro | 6,75 (não vale como medida) | Parou no `preflight`: o alvo respondeu 415 ao login em formulário e a mensagem da CLI não dizia o formato. Corrigido no PR #15 (mensagem com o código HTTP e a dica de `auth.request_encoding`) |
| Semente 17 | 1.5.2 + PR #15 | Seguro | 6,75 | Fluxo inteiro, 97% de alcance, o agente se recuperou do 415 pela dica nova. 5 alarmes falsos de BOLA entre os dois médicos, que no sistema compartilham pacientes. Corrigido na V1.5.3 (campo `shared_roles` vindo da carta) |
| **Semente 18** | **1.5.3** | **Vulnerável (forçado)** | **9,16** | **8 de 10 falhas achadas** (H1, H2, H4, H6, H7, H8, H9, H10), H3 em parte, H5 não. Alcance 97%. Nenhuma violação, perfil fiel à carta |

## Falhas achadas no modo vulnerável, ao longo das versões

| Falha | V1.0 (4 falhas no gabarito) | V1.1 | Codex 1.5.0 | Manhã 1.5.1 | **Tarde 1.5.3** |
| --- | --- | --- | --- | --- | --- |
| H1 SQL injection (busca) | sim | sim | sim | sim | **sim** |
| H2 Erro 500 com detalhes internos | não | não | não | não | **sim** (sinais da cerca) |
| H3 Cabeçalhos e CORS | em parte | em parte | em parte | em parte | em parte |
| H4 Travessia de caminho no download | sim | não | não | não | **sim** |
| H5 BOLA entre pacientes | n/a | não | não | não | não |
| H6 Atribuição em massa | n/a | não | não | não | **sim** |
| H7 Dado a mais na lista | n/a | não | não | não | **sim** |
| H8 SQL injection por tempo | n/a | sim | sim | sim | **sim** |
| H9 Travessia em parâmetro de caminho | n/a | fora da nota | fora da nota | fora da nota | **sim** |
| H10 SQL injection com aspa | n/a | sim | sim | sim | **sim** |
| **Nota** | 9,53 | 8,51 | 7,18 | 0 (8,02 sem a violação) | **9,16** |

## Tempo e tokens da rodada vulnerável, comparados com a V1.1

| Medida | V1.1 | 1.5.3 |
| --- | --- | --- |
| Duração | 27 min 49 s | 33 min 12 s |
| Cadastro | 82 s | 165 s |
| Alcance | 292 s | 271 s |
| Varredura | 1 235 s | 1 456 s (o `scan` da CLI levou 1 301 s) |
| Triagem | 41 s | 69 s |
| Tokens de saída | 19 038 | 24 349 |
| Tokens lidos do cache | 4,47 M | 4,19 M |

A rodada nova custou cerca de 5 minutos a mais, por causa do modo amplo e dos estágios novos (`authz`, `negative`), e achou o dobro de falhas.

## O que ainda não foi achado e por quê

- **H5 (BOLA entre pacientes):** o teste entre contas precisa de uma leitura de consulta feita por uma conta de paciente, com a outra conta de paciente como par. O agente roteou as leituras de consulta para o médico, que agora é papel compartilhado e por isso não é comparado. As skills e as dicas (V1.5.3) orientam usar as contas de paciente, mas o agente não seguiu nesta rodada.
- **H3:** segue em parte, como em todas as versões, porque é uma limitação do ZAP para CORS.

## Limites

- Uma rodada por modo; a variação entre rodadas do mesmo agente é grande (veja a V1.0 r1 e r2).
- A rodada vulnerável teve o modo **forçado** (`--mode vulnerable`), não sorteado.
- Nada disso é prova contra produto real.
