# Plano da versão 1.5.2: avaliação atualizada e correções achadas na rodada cega

Data: 2026-11-15. Origem: a rodada cega de 2026-11-15 ([evals/results/2026-11-15-clinica-piloto-sonnet55-medium-wide/README.md](https://github.com/MarcosQuintino0/harness-dast/blob/fd611a9/evals/results/2026-11-15-clinica-piloto-sonnet55-medium-wide/README.md)). Executor: Codex (coordenador GPT 6.1 Sol, esforço xhigh). Revisão e junção: Claude Code, na sessão do dono.

## Por que esta versão existe

A 1.5.1 ficou mais forte no laboratório, mas a rodada cega achou as mesmas falhas da V1.1. Os motivos foram cinco, e nenhum deles é falta de técnica de ataque:

1. **A carta do caso de avaliação é antiga.** Desde a 1.4/1.5, escrever no alvo, testar valores proibidos com escrita e varrer operações que deram "não encontrado" exigem autorização da carta. A carta da Clínica Piloto em `evals/cases/clinica-piloto/` não autoriza nada disso.
2. **A régua da nota é antiga.** O `evals.runner score` só conta achados do ZAP e do `authz`. A cerca viu o erro 500 com detalhes internos (sinais `S-`, ADR 0049), e isso não contou. Os achados do `negative` (`N-`, ADR 0051) também não contam.
3. **O `probe` sorteia paginação.** Na lista de pacientes ele mandou `page=20917&size=52`, recebeu uma lista vazia, e o teste de dado a mais ficou sem amostra (`no_sample_data`).
4. **Os sinais de erro da cerca não são ligados à operação.** Em `error-signals.json` todos os achados saíram com `operation_id` vazio e bateram no teto de 500. Deveriam agrupar por operação e por categoria.
5. **O agente não recebe dicas que a ferramenta poderia dar.**
   - Ele não encadeou "listar documentos" com "baixar documento": a lista traz o nome de arquivo que o download precisa.
   - Ele roteou todas as leituras de objeto para uma conta só, sem conta par para o teste entre contas.
   - A V1.0 encadeou por sorte do agente; a ferramenta deve sugerir.

Também ficou claro um defeito de processo: **cada versão que põe uma função atrás da carta precisa atualizar o caso e a régua da avaliação no mesmo PR.**

## Contexto obrigatório

Leia antes de tudo, nesta ordem:
1. `docs/como-funciona/finalidade-e-uso-responsavel.md`: a ferramenta é **defensiva**. Ela roda só em ambientes de teste autorizados e, no desenvolvimento, só no laboratório local (Clínica Piloto, VAmPI, crAPI), com dados sintéticos.
2. `CLAUDE.md`, partes A e B. Elas valem para você e para os seus subagentes.
3. `docs/desenvolver/escada-de-testes.md`.
4. `evals/README.md`, `evals/runner/` e `evals/cases/clinica-piloto/`.
5. O README da rodada cega citado acima.

Este trabalho melhora a **avaliação** e corrige **defeitos de qualidade**: régua de nota, caso de teste, geração de dados, agrupamento de achados e dicas de configuração. Ele não acrescenta técnica de ataque nova. Se algum item parecer fora do que você pode fazer, **pare e registre no relatório o item, o motivo e o que faltou**. Não recuse em silêncio nem entregue pela metade sem dizer.

## Itens

| Item | O que fazer | Critério de aceite |
| --- | --- | --- |
| A. Carta e caso da Clínica | Em `evals/cases/clinica-piloto/`, a carta (`authorization.md`) passa a autorizar, por escrito, com frase própria: o modo amplo de caminho; a escrita do teste entre contas (`attack.allow_authz_writes`); a escrita do teste de valores proibidos (`attack.allow_invalid_input_writes`); varrer operações que deram `not_found` (`attack.include_outcomes`); e dar exemplos de dados que existem (por exemplo, como obter um nome de arquivo existente). O `case.yml` acompanha (`expected.path_mode`, os campos novos esperados no perfil). Os exemplos não podem entregar as falhas plantadas (o teste de vazamento precisa passar). Decida, e registre no ADR, se o caso estrito antigo fica como um segundo caso (`clinica-piloto-estrito`) para comparação histórica | `prepare` e `approve` funcionam com a carta nova; `tests/unit/evals` e o teste de vazamento passam |
| B. Régua | O `score` passa a reconhecer achados de `proxy_signals` (`S-`, por categoria e operação) e de `negative` (`N-`, por técnica e operação), além dos do ZAP e do `authz`. O gabarito (`case.yml`, `flaws`) ganha os `match` necessários: por exemplo, H2 casa com um sinal `stack_trace_java` na rota certa. A verificação de fidelidade do perfil confere os campos novos contra a carta (só podem estar ligados se a carta autoriza). Rodadas antigas continuam pontuáveis | Testes da régua com achados sintéticos de cada fonte; a nota de uma rodada antiga salva não muda (recalcule uma e compare) |
| C. Laboratório | A Clínica Piloto ganha uma segunda conta de médico (`PILOT_MEDICO_B_*`), para o teste de escrita em recurso de outra conta poder rodar. Sem falha plantada nova. O perfil de laboratório (`lab/pilot/product-profile/`), o `prepare` e os segredos sorteados da rodada acompanham | O `test_lab_authz.py` mostra `horizontal_write` testando ao menos uma operação |
| D. Paginação no `probe` | Parâmetros de paginação reconhecíveis (`page`, `pagina`, `offset`, `skip` com `minimum` 0 ou 1; `size`, `limit`, `per_page`, `tamanho` com teto) passam a receber o primeiro valor válido (0 ou 1) e um tamanho pequeno, em vez de sorteio, a menos que uma regra do `data-rules.yml` diga outra coisa. Decisão no `domain`, com teste | Teste com o OpenAPI da Clínica: `listarPacientes` sai com página inicial; no laboratório, a lista volta com itens e o `excessive_data` deixa de dar `no_sample_data` |
| E. Sinais da cerca | Achados de sinal ligados à operação (resolva o caminho concreto, inclusive os que o ZAP alterou, pelo modelo do OpenAPI; o que não casar fica agrupado como "fora do contrato" num só achado por categoria). Fingerprint por categoria, método e operação. O teto de 500 não deve ser alcançado com o tráfego normal de uma varredura | No laboratório, o modo vulnerável dá poucos achados de sinal (um por operação e categoria), com `operation_id` preenchido |
| F. Dicas ao agente | O `spec inspect` (e, se couber, o `probe` na mensagem de `not_found`) aponta: (1) encadeamento lista→detalhe quando uma operação `GET` de coleção devolve itens cujo campo casa com o nome ou o formato de um parâmetro obrigatório de outra operação; (2) conta par: quando a carta traz duas contas do mesmo papel e as leituras de objeto estão roteadas para uma só, sugerir rotear ao menos uma leitura por objeto para as duas. A dica é texto e proposta; a CLI não muda o perfil sozinha. Atualize as skills `fix-reachability` e `onboard-product` para usar as dicas | Teste com o OpenAPI da Clínica: as duas dicas aparecem para as operações certas |
| G. Docker na rodada cega | A rodada cega deu nota zero porque o agente rodou `docker images` num comando composto que começava por um comando permitido. Faça o `evals.runner prepare` negar o Docker de forma que pegue comandos compostos, se as regras de permissão do Claude Code permitirem; se não permitirem, registre o limite. E faça a mensagem do `doctor` (falha de `images` por lentidão) dizer para repetir o `doctor`, nunca para chamar o Docker | Teste da mensagem do `doctor`; a regra nova (ou o limite registrado) |
| H. Processo | Acrescente ao plano do ciclo e ao `CONTRIBUTING.md` (ou ao "Definition of Done" do `CLAUDE.md`): toda versão que põe função atrás da carta atualiza o caso e a régua da avaliação no mesmo PR | Texto nos documentos |

## Como trabalhar

- **Worktree e branch.**
  - O coordenador do Claude Code já criou a worktree `C:\harness-dast-wt\v1-5-2`, na branch `feat/v1-5-2-avaliacao`, a partir da `develop`. Trabalhe só nela; **nunca** mexa em `C:\harness-dast`.
  - Os seus subagentes usam worktrees próprias, criadas a partir da `feat/v1-5-2-avaliacao` (por exemplo, `C:\harness-dast-wt\v1-5-2-<tarefa>`), cada uma com branch própria. Você junta na `feat/v1-5-2-avaliacao`.
  - Depois de juntar, remova as worktrees e apague as branches dos subagentes. No fim só pode sobrar a `feat/v1-5-2-avaliacao`.
- **Modelos.**
  - Coordenador: você, GPT 6.1 Sol, esforço xhigh.
  - Programadores: GPT 6.1 Terra, high, no máximo três ao mesmo tempo, cada um com arquivos que não se cruzam.
  - Documentação, se precisar: GPT 6.1 Terra, medium.
  - QA independente: GPT 6.1 Terra, high, um subagente que não programou e tenta quebrar.
- **ADRs:** use os números **0053 em diante**. Os números 0049 a 0052 já foram usados no complemento da 1.5. O ADR nasce como "Proposto".
- **Versão:** 1.5.2. Atualize `CHANGELOG.md`, `CLAUDE.md` (o parágrafo de estado), `docs/roadmap.md`, `docs/decisoes/README.md` e o `pyproject.toml`, e escreva o relatório `docs/arquivo/reviews/relatorio-v1.5.2.md` no formato de `relatorio-v1.5.1.md`.
- **Testes:**
  - Degrau 2 para tudo: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run mypy --platform linux`, `uv run lint-imports`, `uv run vulture` e `uv run pytest -q`, todos verdes, com a suíte inteira depois da última mudança.
  - Degrau 3 só pelos testes de integração (`tests/integration/`, marcadores `integration` e `lab_fast`), para os itens C, D e E. O Docker fica em `%LOCALAPPDATA%\Programs\DockerDesktop\`. Se ele travar com `sailor-ingest.sock`, renomeie a pasta `%LOCALAPPDATA%\Docker\run`; nunca use "Reset to factory defaults".
  - Antes de subir a pilha, derrube pilhas do laboratório que sobraram (`docker compose ls -a`). Use `HDAST_ZAP_API_KEY` aleatória no processo e termine sempre com `stack down`.
- **Regras da parte B ao tocar o laboratório:**
  - só comandos `hdast` e o suporte de testes;
  - nada de `curl` contra o alvo;
  - não leia `.env`;
  - nunca rode `hdast profile approve` nem `secret set`/`delete`.
- **Detector de segredos:** o `gitleaks` roda no CI. Não afrouxe o detector para caber um arquivo. Se um arquivo for marcado por alarme falso, deixe-o fora do repositório e diga no relatório.
- **Commits** em Conventional Commits, em português.
- **Push e PR.**
  - Faça push da `feat/v1-5-2-avaliacao` e abra o PR para a `develop`, com resumo, gates e o que não foi provado.
  - **Não junte o PR**: quem revisa e junta é o Claude Code.
  - Nunca force push, e nunca mexa na `main` nem na `develop` diretamente.

## Relatório final (a sua última mensagem)

Em português:

1. Para cada item de A a H:
   - **feito**, **feito em parte** ou **não feito**, com o motivo;
   - arquivos;
   - testes;
   - como foi provado.
2. Se algum pedido foi recusado ou limitado por regra do seu modelo: qual, e por quê. Não esconda.
3. Gates com números.
4. Testes de integração rodados, com números.
5. O PR aberto (link), a branch e o último commit.
6. Os modelos e o esforço de cada subagente, e quantos rodaram.
7. O que o Claude Code precisa saber para revisar e juntar.
