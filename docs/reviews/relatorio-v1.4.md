# Relatório da versão 1.4.0

Data: 2026-11-14. Branch: `feat/v1-4`. Plano: [docs/plans/2026-11-14-ciclo-v1-3-a-v1-8.md](../plans/2026-11-14-ciclo-v1-3-a-v1-8.md).

> **Rascunho.** As seções 3 e 5 ainda esperam a investigação do laboratório (seção 5, "Em investigação").

## 1. Resumo

**Número:** 1.4.0 (a anterior é a 1.3.0).

**Objetivo:** achar mais falhas de autorização, que o ZAP não detecta por construção: uma conta lendo ou alterando o que é de outra, um papel menor usando função de papel maior, pedido aceito sem login, crachá adulterado aceito, campo que o usuário não deveria poder mudar.

**Funcionalidades:**

1. **Teste entre contas ligado por padrão no `run`** (ADR 0038), só lendo. A escrita só liga quando a carta autoriza.
2. **Pedido sem login e token adulterado** (ADR 0039).
3. **Campos proibidos tirados do OpenAPI**, também no cadastro (`POST`) (ADR 0040).
4. **Tabela "quem pode o quê"**, conferida por uma pessoa (ADR 0041).
5. **Alterar recurso de outra conta e identificador na consulta** (ADR 0042).
6. **Correção** no portão do script de limpeza.
7. **Guia da escada de testes.**

**O que a versão é e o que não é:** código e testes, QA independente e uma prova com Docker na Clínica Piloto, nos modos vulnerável e seguro. Nada foi provado contra produto real.

## 2. Em linguagem simples

Os exemplos usam a Clínica Piloto, o sistema de mentira do laboratório, com duas pacientes inventadas, Ana e Bia.

| O que mudou | Exemplo | O que a pessoa precisa fazer |
| --- | --- | --- |
| O teste "uma conta vê o que é de outra" roda sempre | Antes, quem rodava `hdast run` sem lembrar do `--authz` não testava nada disso. Agora a Ana tenta abrir a consulta da Bia em toda execução. | Nada. Para desligar, `--no-authz` |
| Escrita só com a carta | O teste que tenta mudar o próprio papel para "administradora" escreve no sistema. Ele só roda se a carta disser que pode, com a frase da carta copiada. | Responder na entrevista se a carta autoriza escrever; "não sei" vale "não" |
| Sem login e com crachá adulterado | A ferramenta pede a lista de consultas sem login nenhum, e depois com o crachá da Ana estragado de propósito. Se o sistema entregar, é falha grave. | Nada |
| Campos proibidos tirados do OpenAPI | Antes só tentava `role`, `papel`, `admin`, `isAdmin`. Agora lê o OpenAPI e tenta também campos como `saldo` ou `status`, que aparecem na resposta mas não deveriam ser aceitos na entrada. No cadastro, cada tentativa deixa um registro de teste criado. | Rodar a limpeza ou o reset do ambiente depois |
| Alterar o que é de outro | A Bia tenta mudar o telefone da Ana. A Ana confere se mudou e desfaz. | Ter duas contas do mesmo papel na carta |
| Identificador na consulta | A Ana pede `/consultas?pacienteId=<da Bia>`. Antes só se testava o número no caminho. | Nada |
| Tabela "quem pode o quê" | O agente rascunha: "paciente não pode listar todos os pacientes". A pessoa confere e aprova. A ferramenta tenta e espera ser recusada. | Conferir a tabela antes de aprovar o perfil |

## 3. Evidências

Arquivos em `C:\harness-dast-artefatos\v1.4\` (fora do repositório).

**Teste de autorização na Clínica Piloto** (`lab-authz\lab-authz-vulnerable.json`, `lab-authz-secure.json` e `pytest-saida.txt`). O teste `tests/integration/test_lab_authz.py` sobe a pilha, roda `preflight`, `probe`, `authz` com todas as verificações e dois `run --skip-scan` (com e sem `--no-authz`), nos dois modos, com a escrita ligada numa cópia descartável do perfil. Primeira rodada: 16 passaram e 2 pularam (os exclusivos de cada modo), em 905 s.

| | Vulnerável | Seguro |
| --- | --- | --- |
| Pedidos do `authz` | 145 | 137 |
| Recursos criados por cadastro | 11 | 11 |
| Achados | 4 (3 altos, 1 médio): horizontal 1, dado a mais 1, atribuição em massa 2 | 1 médio (atribuição em massa em `POST /api/consultas`, em investigação) |
| `DELETE` enviados | 0 | 0 |
| Pedidos fora da cerca | 0 | 0 |
| Token ou segredo em artefato | 0 | 0 |
| Tempo: subir a pilha, `probe`, `authz` | 44 s, 69 s, 224 s | 48 s, 69 s, 159 s |

No `run.json`, `--skip-scan` deixa o estágio `authz` como `skipped` com a mensagem certa, e `--skip-scan --no-authz` também.

## 4. Qualidade e testes

| Gate | Resultado (commit `0c9f545`) |
| --- | --- |
| `ruff check` | sem problemas |
| `ruff format --check` | 837 arquivos |
| `mypy` | sem problemas em 700 arquivos, nas duas plataformas (Windows e `--platform linux`) |
| `lint-imports` | 6 contratos mantidos |
| `vulture` | limpo |
| `pytest` | 7812 passaram, 0 falharam, 4 pulados, 67 desselecionados |

Os testes passaram de 7012 (fim da 1.3) para 7812.

**QA independente.** Um subagente que não programou a versão atacou as travas de escrita, a impressão digital, o vazamento, as entradas, o relatório e o portão da limpeza, com 6 arquivos `*_qa.py`. Não achou defeito grave nem médio. Achou três baixos, todos corrigidos com o teste que os reproduzia:

| Defeito | O que foi feito |
| --- | --- |
| A ordem de `id_parameters` mudava a impressão digital (a pessoa teria de aprovar de novo sem motivo) | `id_parameters` e `mass_assignment_methods` tratados como conjuntos (commit `0c9f545`) |
| Uma barra vertical no nome de operação (que vem do OpenAPI do alvo) quebrava as tabelas do `report.md` | Barra escapada em toda célula de tabela (`cell_code`) |
| O rascunho da tabela estragava caracteres acima de U+FFFF | Escape `\U` de oito dígitos, que o YAML lê de volta igual |

Antes do QA, um teste de propriedade achou por acaso uma brecha no portão do script de limpeza, anterior à V1.4: `DELETE FROM PEDIDO DROP/* ; DROP TABLE X; */WHERE ...` era aceito, com `DROP` no lugar do apelido da tabela. O comentário não chegava ao banco e o Oracle recusaria o comando, mas o portão precisa falhar fechado sozinho. Corrigido no commit `5f6d780`.

## 5. Problemas e decisões

**Em investigação** (esta seção será completada antes do PR):

- **Pedidos sem login e com token adulterado estourando o tempo (15 s).** Cerca de 10 por modo. O proxy registrou a resposta, mas a CLI não a recebeu. Esses pedidos viram "inconclusivo" e reduzem o que as duas verificações novas testam.
- **Achado médio no modo seguro** (`POST /api/consultas`, campo `valor`, que aparece repetido no achado): pode ser falso positivo da leitura do recurso criado, ou comportamento real do alvo.
- **Verificações não exercitadas no laboratório:** a tabela "quem pode o quê" (o perfil do laboratório não tem tabela) e a escrita em recurso de outra conta (sem duas contas do mesmo papel nas operações de escrita).

**Decisões do coordenador** (dúvidas do projetista dos ADRs):

- Pedido sem login: severidade alta quando o OpenAPI exige autenticação, média quando não declara.
- Campo de dono (`ownerId`, `tenantId`) só é testado se declarado: trocar o dono poderia trancar a conta de teste.
- Chaves novas do `authz` no valor padrão ficam fora da impressão digital: nenhuma aprovação existente se perde.
- O cadastro pode deixar até 4 registros por operação, mais os declarados; quem limpa é o `cleanup` ou o reset.
- A tabela "quem pode o quê" fica só no perfil, aprovada no `profile approve`; não é campo da carta.
- O rascunho da tabela pode ser gravado na pasta do produto, fora do perfil.
- Identificador no corpo do pedido e geração de valores novos para fugir do 409 no cadastro ficam para depois.
- A escrita na carta exige `source: carta` e a frase copiada, como o modo amplo da cerca.

**Incidentes:**

- As worktrees criadas automaticamente para os subagentes partiam da V1.2. Todo briefing passou a mandar conferir o commit de partida.
- O Docker Desktop travou com os sockets antigos (`sailor-ingest.sock`); renomear a pasta `run` resolveu.
- O briefing do Codex citava o nome da pasta de gabaritos, e o teste de vazamento da cópia cega pegou. Texto trocado.

## 6. Sugestões descartadas

Nenhuma nesta versão.

## 7. Débitos e não provado

- **O `run` completo com varredura e o `authz` padrão** não foi rodado de ponta a ponta com Docker: cada modo leva de 20 a 30 minutos e o plano da versão não pedia. Só `run --skip-scan` e `--no-authz`.
- **Produto real:** nada foi provado.
- **O `profile approve` com a tabela**, num terminal de verdade, com uma pessoa conferindo.
- **BFLA vertical:** segue sem prova (o laboratório não tem conta de papel menor para as operações atribuídas a papel maior).
- **Identificador no corpo, `DELETE` e geração de valores únicos no cadastro:** fora desta versão.
- **Autenticação só por cookie de sessão** não é modelada pelo token adulterado; `alg` escrito como `None` ou `NONE` não é coberto.
- **QA não cobriu:** a carta com YAML hostil no `init --from-letter`, o envelope JSON e os códigos de saída do `authz` e do `run`.
- **Funções acima de 40 linhas** já existentes no `authz` cresceram um pouco (`_plan`, `execute`, `_run`, `_mass_apply`); `application/authz.py` tem 480 linhas.
- **ADRs 0038 a 0042** continuam "Proposto"; aceitar é decisão do dono.
- **Rodada cega:** não houve nesta versão (o plano pede só para a 1.8 e ao mudar skill; as skills mudaram em texto, por isso fica como débito).

## 8. Conclusão

A completar depois da investigação do laboratório.

**Orquestração:** coordenador Claude Opus 5.5; nove subagentes Claude Sonnet 5.5 (projetista, refatoração, cinco programadores, QA independente e teste de laboratório), cada um na sua worktree, juntados um por vez na `feat/v1-4` com os gates depois de cada junção.
