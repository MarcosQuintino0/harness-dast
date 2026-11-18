# Relatório da versão 1.5.1

Data: 2026-11-15. Branch: `feat/v1-5-complemento`. Plano: [docs/arquivo/plans/2026-11-14-ciclo-v1-3-a-v1-8.md](../plans/2026-11-14-ciclo-v1-3-a-v1-8.md). Versão anterior: [1.5.0](relatorio-v1.5.md).
Versão em linguagem simples: <https://claude.ai/artifact/XtPBjDeCrv3iZ66jbPUFGH> (cópia em C:/harness-dast-artefatos/v1.5c/relatorio-v1-5-1-artifact.html).

## 1. Resumo

**Número:** 1.5.1. Completa a V1.5 ("achar mais: entrada e erros").

**Por que existe:** a 1.5.0 foi feita pelo Codex, que entregou só diagnósticos offline. Ele recusou, por regra do próprio modelo, programar as partes que mandam testes ativos ao alvo, mesmo no laboratório. Esta versão faz essas quatro partes, no mesmo processo da V1.4.

**Funcionalidades:**

1. **Sinais de erro interno vistos pela cerca** (ADR 0049).
2. **Varrer as operações que deram "não encontrado"**, quando a carta pedir (ADR 0050).
3. **Valores que o esquema proíbe:** comando `hdast negative` e sexto estágio do `run` (ADR 0051).
4. **Envio de arquivo (`multipart`)** no `probe`. O `scan` de upload fica pulado, porque o ZAP real o recusa (ADR 0052).
5. **Documentos de finalidade e uso responsável** (PRs #9 e #10, já na `develop`).

**Mudança de uso:** `--include-outcome` do `scan` só escolhe dentro do perfil. Antes ela alargava o que era atacado.

**O que a versão é e o que não é:** código e testes, QA independente e prova com Docker na Clínica Piloto, nos modos vulnerável e seguro. Nada foi provado contra produto real.

## 2. Em linguagem simples

| O que mudou | Exemplo | O que a pessoa precisa fazer |
| --- | --- | --- |
| A cerca percebe quando o sistema "vaza as entranhas" num erro | A busca de pacientes quebra e responde com o rastreamento de pilha Java. Antes ninguém lia essa resposta. Agora vira um achado no relatório, sem guardar o texto da pilha. | Rodar `hdast stack up --build` uma vez, para a cerca nova valer |
| Atacar também o que deu "não encontrado" | A função "baixar arquivo" deu 404 porque ninguém sabia um nome de arquivo que existisse. Se a carta pedir, ela entra no ataque mesmo assim. | Responder na entrevista se a carta autoriza; "não sei" mantém como era |
| Valores que o contrato proíbe | O OpenAPI diz que a idade vai de 0 a 130. A ferramenta manda -1 e vê se o sistema aceita. Por padrão só em consultas (`GET`). | Para testar cadastros e alterações, a carta precisa autorizar, com a frase copiada |
| Envio de arquivo | A função de enviar documento passa a ser alcançada com um arquivo de teste minúsculo e inofensivo. O ZAP ainda não consegue atacá-la, e o relatório diz isso. | Nada |

## 3. Evidências

Arquivos em `C:\harness-dast-artefatos\v1.5c\` (fora do repositório).

**Sinais na cerca** (`lab-final/lab-error-signals-*.json`, 12 testes passaram):

| | Vulnerável | Seguro |
| --- | --- | --- |
| Respostas liberadas com status | 42 | 315 |
| Respostas com sinal | 1 (rastreamento de pilha Java, HTTP 500) | 0 |
| Tempo médio por resposta (leitura incluída) | 67 ms | 16,6 ms |

**Varredura de "não encontrado"** (`lab-final/lab-include-outcomes-*.json`, 8 testes passaram). O `probe` deu `not_found` em 2 operações nos dois modos. Com `scan.include_outcomes: [not_found]`, a operação entrou no `scan` com `seed_outcome: not_found`: 508 e 492 pedidos, nenhum `DELETE`. Sem o campo, ficou de fora com o motivo `not_success`.

**Valores proibidos** (`lab-final/lab-negative-*.json`, 18 testes passaram):

| | Só leitura | Com escrita (cópia descartável) |
| --- | --- | --- |
| Pedidos | 9 `GET`, todos recusados com 400 | 59 |
| Achados | 0 | 9 baixos: número aceito em campo de texto |
| Recursos criados e restaurados | 0 e 0 | 5 e 4 |
| Respostas 5xx | 0 | 0 |

Os números foram iguais nos dois modos. A validação de tipo da Clínica Piloto é a mesma no vulnerável e no seguro. Nenhum valor inválido apareceu em artefato nem na auditoria da cerca.

**Envio de arquivo** (`lab-multipart/` e `lab-multipart-scan/`). O `probe` mandou o arquivo e recebeu 201 nos dois modos (10 testes, 136 s). O `scan` do ZAP 2.17 recusou o pedido `multipart` com `url_not_found` nos dois modos (10 testes, 157 s), por isso o desvio `multipart_not_scannable` ficou ligado.

**Depois do conserto do QA:** a prova do `negative` foi repetida na branch integrada com os consertos do QA (`lab-final/depois-do-conserto/`). Deu 18 testes verdes em 788 s e os mesmos números nos dois modos: 9 pedidos de leitura recusados, 59 com escrita, 9 achados baixos, 5 recursos criados e 4 restaurados, nenhum valor vazado.

## 4. Qualidade e testes

| Gate | Resultado |
| --- | --- |
| `ruff check` | sem problemas |
| `ruff format --check` | 961 arquivos |
| `mypy` | sem problemas em 800 arquivos, nas duas plataformas (Windows e `--platform linux`) |
| `lint-imports` | 6 contratos mantidos |
| `vulture` | limpo |
| `pytest` | 9125 passaram, 0 falharam, 4 pulados, 149 desselecionados (integração com Docker rodada à parte: seção 3) |

**QA independente.** Cerca de 370 testes novos em 11 arquivos `*_qa.py`. Achou 7 defeitos, todos corrigidos com o teste que os reproduzia:

| Defeito | Gravidade | O que foi feito |
| --- | --- | --- |
| O limite de pedidos do `negative` era furado pelas repetições de 429 (limite 1, saíam 4) | Média | O envio conta toda tentativa e reserva um pedido para a restauração |
| Escrita cuja linha de base perdeu um campo obrigatório dava falsa segurança | Média | A operação fica `not_tested` (`omitted_required_field`) |
| O `negative` repetia os caminhos de saúde e de preparação | Baixa a média | A mesma regra do `authz`, agora no perfil (`infrastructure_paths`) |
| O plano do `scan` não normalizava o método | Baixa | `upper()` |
| E-mail e CPF inteiros no caminho dos sinais | Baixa | Viram `{}`; os fingerprints antigos não mudaram |
| Limite negativo na função de plano | Baixa | `max(0)` |
| Painel ao vivo sem estágios | Baixa | Termina como parcial |

O que o QA atacou sem conseguir quebrar: impressão digital da aprovação, bomba de compressão de 200 MiB, textos para travar expressões regulares, travas do `negative`, 30 nomes de arquivo hostis e relatório com nomes hostis.

## 5. Problemas e decisões

**Decisões do coordenador** (dúvidas do projetista):

- `attack.include_outcomes` vale com origem `carta` ou `pessoa`, sem exigir a frase, como a força do ataque, e com aviso.
- `--include-outcome` passa a só escolher dentro do perfil. A quebra está declarada.
- O `negative` fica ligado por padrão no `run`, só em `GET`.
- A Clínica Piloto ganhou uma operação de envio de arquivo sem falha plantada.
- Varrer upload exige campo próprio da carta (`attack.allow_upload_scan`). O ZAP gravaria conteúdo de ataque no armazenamento do alvo.
- Se o ZAP não aceitasse `multipart`, a entrega ficaria só com o alcance. Foi o que aconteceu.
- Severidades: erro de banco e página de depuração como média, rastreamento de pilha como baixa, todos para triagem.

**Incidentes:**

- Outra sessão (provavelmente o Codex) escreveu na pasta `C:\harness-dast`, criando `evals/results/` e linhas no `evals/README.md`. Um `git add -u` do coordenador levou uma dessas linhas para um commit. Ela foi desfeita no `b048042`, e a cópia de trabalho da outra sessão foi devolvida.
- Uma pilha de laboratório esquecida (`hdast-blind-qa`) ocupou a porta da Clínica Piloto e derrubou um teste. Foi derrubada com a autorização do dono.
- Dois ADRs e um briefing citavam a pasta de gabaritos, e o teste de vazamento da cópia cega pegou. O texto foi trocado.
- O subagente do laboratório escreveu no `CHANGELOG.md`, que é arquivo do coordenador. A entrada foi substituída pela da 1.5.1.

## 6. Sugestões descartadas

Nenhuma.

## 7. Débitos e não provado

- **Produto real:** nada foi provado.
- **`scan` de upload:** pulado. O ZAP 2.17 recusa `multipart` pela API de varredura. Ficaram como caminho futuro o plano do Automation Framework e um script de regra.
- **`negative`:** nenhum 5xx apareceu no laboratório; `PATCH` aceito com restauração não foi provado; os recursos criados por `POST` ficaram no alvo descartável (`hdast cleanup` não foi usado, porque não havia Oracle na prova). Por desenho, ficam fora `pattern`, formato, parâmetro de caminho, cabeçalho, formulário e `multipart`.
- **Sinais na cerca:** o custo em respostas grandes (perto de 64 KiB), `br`/`zstd` e HTTPS não foram medidos.
- **`include_outcomes`:** só `not_found` foi provado no laboratório.
- **Evidência do ZAP:** no modo vulnerável, o relatório mostra um trecho do rastreamento de pilha que vem da evidência do alerta do ZAP (ADR 0022: redigida e cortada), não da cerca. Fica para o dono decidir se quer cortar mais.
- **`HDAST_UPDATE_GOLDEN=1` não funciona:** o `conftest` limpa as variáveis `HDAST_*`. Defeito antigo, contornado regravando os golden pela função geradora.
- **ADRs 0049 a 0052** seguem "Proposto"; aceitar é decisão do dono.

## 8. Conclusão

A V1.5 está completa: a 1.5.0 trouxe os diagnósticos offline e a 1.5.1 trouxe as quatro partes ativas, provadas no laboratório, com QA independente e os defeitos corrigidos. A única parte que não chega ao alvo é a varredura de upload: o ZAP não a aceita, e o relatório diz isso.

**O que depende do dono:**

1. Aceitar (ou não) os ADRs 0045 a 0052.
2. Rodar `hdast stack up --build` na próxima vez que usar a pilha.
3. Decidir se o trecho do rastreamento de pilha que vem do ZAP deve aparecer no relatório.
4. Avisar a outra sessão que está escrevendo em `C:\harness-dast`.

**Orquestração:** coordenador Claude Opus 5.5 e doze subagentes Claude Sonnet 5.5: um projetista, oito programadores, um QA, um de conserto e um de laboratório.
