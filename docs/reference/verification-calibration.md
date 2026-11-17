# Calibração da verificação

**Estado: medida só no laboratório (Clínica Piloto e VAmPI), em 2026-11-17, com amostras pequenas.** Nada foi medido contra produto real. O que segue descreve a ferramenta nesses dois alvos sintéticos; não é probabilidade de acerto nem se estende a outros produtos.

O cruzamento com o gabarito (`evals/answer-keys/clinica-piloto.md` e `evals/cases/*/case.yml`) foi feito só no desenvolvimento. A matriz, o JSON e este arquivo ficam fora da cópia cega.

## Como foi medido

- Cinco execuções completas do `hdast run` (varredura concluída, estágios `ok`), cada uma seguida de um `hdast confirm` por achado (todos os achados do relatório, um fingerprint por chamada). `findings.json` ficou intacto em todas.
- Aprovações descartáveis só no estado do teste, pelo suporte de integração; nenhum `profile approve`, nenhuma escrita em `products/` nem no estado real.
- Código: `e79c5b0` na Clínica vulnerável, na Clínica segura sem `shared_roles` e no VAmPI vulnerável; `80929bb` (só a leitura de cabeçalhos repetidos mudou) na Clínica segura com `shared_roles` e no VAmPI seguro.

| Execução | run_id | Achados (ZAP + autorização + sinais) | Níveis |
| --- | --- | --- | --- |
| Clínica vulnerável | `2026-11-17T06-14-55Z-clinica-piloto-3454` | 131 (98 + 4 + 29) | 4 reproduzidos, 1 inconclusivo, 126 não verificáveis |
| Clínica segura | `2026-11-17T06-01-16Z-clinica-piloto-143c` | 64 (63 + 1) | 1 reproduzido, 63 não verificáveis |
| Clínica segura com `authz.shared_roles: [medico]` | `2026-11-17T06-39-37Z-clinica-piloto-7ee5` | 63 (63 + 0) | 63 não verificáveis |
| VAmPI vulnerável | `2026-11-17T06-35-11Z-vampi-009c` | 37 (30 + 3 + 4) | 3 reproduzidos, 34 não verificáveis |
| VAmPI seguro | `2026-11-17T06-53-13Z-vampi-050d` | 28 (25 + 3) | 3 reproduzidos, 25 não verificáveis |

Nenhuma das cinco execuções teve `likely` nem `likely_false_positive`. A capacidade de descartar um falso positivo **não foi exercitada**: não há medida de acerto dela.

## Matriz por tipo (contagens)

Legenda do gabarito: **plantada** é falha do gabarito (modo vulnerável); **observação** é propriedade verdadeira que não é falha plantada (cookie sem `HttpOnly`, sessão, autenticação, cabeçalhos do VAmPI); **declaração** é achado de autorização cuja verdade depende de o papel compartilhar recursos ou a operação ser pública; **sem gabarito** é o que o gabarito não classifica.

| Tipo de alerta | Execução | Gabarito | Reproduzido | Inconclusivo | Não verificável |
| --- | --- | --- | --- | --- | --- |
| Autorização: CORS com credenciais | Clínica vulnerável | plantada (H3) | 1 | 0 | 0 |
| Autorização: campos fora do esquema | Clínica vulnerável | plantada (H7) | 1 | 0 | 0 |
| Autorização: leitura entre contas de paciente (`buscarConsulta`) | Clínica vulnerável | plantada (H5) | 1 | 0 | 0 |
| Autorização: leitura entre médicos (`buscarPaciente`), sem `shared_roles` | Clínica vulnerável e segura | declaração (a carta do caso diz que médicos compartilham) | 2 | 0 | 0 |
| Autorização: mesma leitura, com `shared_roles: [medico]` | Clínica segura | declaração | sem achado | 0 | 0 |
| Autorização: resposta sem login (`authz_anonymous_access`) | VAmPI vulnerável e segura | sem gabarito (o OpenAPI não declara `security`) | 6 | 0 | 0 |
| SQL Injection, parâmetro de consulta (`pacientes/busca`) | Clínica vulnerável | plantada (H1) | 0 | 1 | 0 |
| SQL Injection, parâmetro de caminho (`medicos/crm`) | Clínica vulnerável | plantada (H10) | 0 | 0 | 1 |
| SQL Injection por tempo, caminho (`convenios/codigo`) | Clínica vulnerável | plantada (H8) | 0 | 0 | 1 |
| SQL Injection, caminho (`/users/v1...`) | VAmPI vulnerável | plantada (V1) | 0 | 0 | 3 |
| Travessia de caminho (`documentos/download`) | Clínica vulnerável | plantada (H4) | 0 | 0 | 1 |
| Divulgação de hash BCrypt | Clínica vulnerável | plantada (H7) | 0 | 0 | 1 |
| `X-Content-Type-Options` ausente | Clínica vulnerável | plantada (H3) | 0 | 0 | 30 |
| `X-Content-Type-Options` ausente | VAmPI vulnerável e segura | observação | 0 | 0 | 22 |
| XSS refletido (caminho) | VAmPI vulnerável | sem gabarito | 0 | 0 | 2 |
| Cookie sem `HttpOnly`, sessão e autenticação identificadas | Clínica (3 execuções) e VAmPI (2) | observação | 0 | 0 | 191 |
| Versão no cabeçalho `Server` | VAmPI vulnerável e segura | observação | 0 | 0 | 26 |
| Sinal de erro interno do proxy | Clínica e VAmPI vulneráveis | sem gabarito | 0 | 0 | 33 |

Leitura, sem extrapolar:

- **Alcance das receitas.** Só um achado de todo o conjunto era elegível a receita ativa (consulta, GET, semente de sucesso varrida): o SQL de `pacientes/busca`. Os demais SQL e XSS do laboratório estão em parâmetro de caminho, e a receita só aceita parâmetro de consulta. As receitas de tempo, de reflexão HTML e de erro detalhado nunca rodaram contra um achado real neste laboratório (a única receita que enviou pedidos mandou 5, todos para `buscarPacientesPorNome`).
- **O único caso ativo ficou `inconclusive`**, o nível conservador, e não `reproduced`: a semente de `nome` devolve lista vazia e a consulta usa `LIKE '%…%'`, de modo que a condição "falsa" também devolve todas as linhas (748 bytes nas duas) e não difere da "verdadeira". A falha plantada existe (H1), então é uma limitação da receita, não um falso positivo; o motivo gravado diz que respostas iguais não refutam o alerta.
- **Todo `reproduced` veio de recibo gravado de autorização**, sem pedido novo. Ele confirma que o fato descrito foi observado, não que seja falha: dos 11 reproduzidos nas cinco execuções, 3 são falhas plantadas, 2 são médicos que compartilham pacientes (a carta do caso declara isso e, com `shared_roles`, o achado some e o reproduzido some junto) e 6 são operações sem login do VAmPI, para as quais o gabarito não decide.
- **Os tipos plantados fora do alcance** (caminho, travessia, hash, cabeçalho em JSON) saíram `not_verifiable`, nunca `likely_false_positive`. Nenhuma falha plantada foi descartada.
- **Os alertas do modo seguro** que o ZAP levanta (cookie, sessão, autenticação, `Server`) são observações reais e ficaram `not_verifiable`: nenhum virou `reproduced`.

## O que entra no JSON

`verification-calibration.json` lê só medidas com gabarito inequívoco e mostra "no laboratório, X de Y" por tipo. Hoje são três linhas, todas com amostra abaixo de 10, então o relatório e o painel mostram contagens e nenhuma porcentagem:

| Tipo | Critério | Correto de amostra |
| --- | --- | --- |
| Autorização entre contas com recibo (Clínica Piloto) | reproduzido coincide com falha plantada | 3 de 5 |
| SQL Injection em parâmetro de consulta (receita booleana) | falha plantada recebe reproduzido | 0 de 1 |
| Clínica segura com `shared_roles` declarado pela carta | execução completa sem nenhum reproduzido | 1 de 1 |

Não entram no JSON: as 6 respostas sem login do VAmPI (sem gabarito inequívoco) e as contagens de `not_verifiable` (medem alcance, não acerto, e uma taxa de 100% enganaria).

## Limites

- Amostra pequena e um único par de produtos sintéticos. Não há medida de sensibilidade para tipos sem achado real, nem do `likely_false_positive`.
- A receita booleana depende de semente com linhas e de contexto sem `LIKE`; fora disso fica `inconclusive`. A receita de tempo só cobre PostgreSQL; a de reflexão HTML não prova execução de JavaScript.
- Cabeçalhos repetidos (`Vary`, `Set-Cookie`) tornavam a evidência "indisponível" para os 30 alertas de `X-Content-Type-Options` da Clínica vulnerável. Corrigido em `80929bb`; o nível não muda neste laboratório (a resposta é JSON, e o motivo passa a ser "não comprova interface HTML"), mas a execução medida é anterior à correção e não foi repetida.
- Achados de autorização por recibo dependem da declaração do perfil (`authz.shared_roles`, operação pública). Sem ela o nível `reproduced` confirma o fato, não a vulnerabilidade.

## Formato do JSON

O JSON tem `schema_version`, `status`, `provenance` e `measurements`. Enquanto estiver `blocked`, a lista fica vazia; depois de medida, `status` passa a `measured` e cada entrada traz `finding_type`, `criterion`, `correct`, `sample` e `provenance`. A quantidade correta não pode superar a amostra. Percentual só aparece com dez ou mais observações. Dados ausentes ou inválidos não viram zero.
