# Plano da versão 1.5.5: achar o que ainda escapa, em qualquer API

Data: 2026-11-15. Executor: Codex (coordenador GPT 6.1 Sol, esforço xhigh). Revisão e junção: Claude Code, na sessão do dono. As rodadas cegas desta versão serão pedidas depois pelo dono, em **pelo menos duas APIs**.

## Por que esta versão existe

Na rodada cega da V1.5.4 com o GPT 6.1 Terra (semente 20, nota 8,57), o fluxo foi até o fim e achou 7 das 10 falhas da Clínica Piloto. Na referência com o Sonnet 5.5 (V1.5.3, nota 9,16), foram 8. As perdas restantes vêm de limites da **ferramenta**, não de descuido do agente. A causa de cada uma foi conferida no rastro:

1. **Espera da varredura gastando tokens.**
   - A skill `run-scan` manda rodar o `hdast run` em segundo plano e acompanhar `scan-progress.json`.
   - O Terra leu esse arquivo 26 vezes e fez 58 chamadas só de espera durante os 21 minutos da varredura. Cada chamada reenvia a conversa: foram 11,4 milhões de tokens, 3,8 vezes o orçamento do caso, contra 4,4 milhões do Sonnet.
   - Não existe hoje um jeito de esperar com **um comando que bloqueia** até a execução terminar.
2. **Atribuição em massa sem conferência (H6).**
   - A verificação `mass_assignment` confere o efeito por uma leitura do mesmo modelo de caminho **e da mesma conta** (`update_reader` em `src/harness_dast/application/authz.py`).
   - No rastro do Terra, `PUT /api/me` foi provado com uma conta e `GET /api/me` com outra do mesmo papel. Sem leitura da mesma conta, a conferência caiu na resposta do próprio `PUT`, que não ecoa o campo, e o achado não saiu.
   - O Sonnet provou as duas operações com a mesma conta e achou.
3. **CORS permissivo (parte da H3).** A falha só aparece quando o pedido leva o cabeçalho `Origin`, que o ZAP não manda. Os cabeçalhos de segurança ausentes já são achados.
4. **Acesso a objeto de outra conta do mesmo papel (H5). Os dois modelos erraram igual.**
   - O teste `horizontal` só compara objetos que o `probe` leu, com a conta que o `probe` usou.
   - Os dois agentes provaram as leituras de objeto com uma conta de papel declarado como compartilhado na carta (`authz.shared_roles`), e a ferramenta pula esse papel de propósito.
   - Nenhum objeto de uma conta de papel **não** compartilhado entrou no teste.
   - A dica do `spec inspect` (ADR 0056) não bastou com nenhum dos dois modelos. A ferramenta precisa montar o par sozinha.
5. **Um achado alto sem anotação na triagem.** O agente anotou 9 de 10. A skill não pede uma conferência final.

Evidências, fora do repositório:
- `C:\harness-dast-artefatos\rodadas-cegas\piloto-terra61-v154-random-2026-11-15\` (`README.md`, `score.md`, `agent-metrics.json`, `trace/runs/*/authz.json` e `exchanges.json`);
- a referência `C:\harness-dast-artefatos\rodadas-cegas\piloto-sonnet55-v153-vuln-2026-11-15\`.

## Regra que vale para todos os itens: funcionar em qualquer API

A ferramenta vai receber o Swagger de produtos diferentes.

1. **Nada de nomes de um produto.** Nenhuma regra, dica, mensagem, skill ou teste de comportamento pode depender de nomes de um produto: campos, rotas, papéis ou recursos. As decisões saem do contrato OpenAPI, do perfil, da carta e da resposta HTTP.
2. **Prova em pelo menos duas APIs.** Cada item de B a E precisa ser provado no laboratório em **pelo menos duas APIs diferentes**: a Clínica Piloto **e** o VAmPI (`tests/integration/test_lab_vampi.py` existe). O crAPI é bem-vindo, mas não obrigatório, porque fica fora do `hdast stack up`. Se a falha correspondente não existir numa das APIs, prove ao menos que a regra roda nela sem alarme falso e sem erro.
3. **Uma regra que só funciona na Clínica não entra.** Pare e registre no relatório.

## Contexto obrigatório

Leia antes de tudo:
1. `docs/como-funciona/finalidade-e-uso-responsavel.md`: a ferramenta é **defensiva**. Ela roda só em ambientes de teste autorizados e, no desenvolvimento, só no laboratório local, com dados sintéticos.
2. `CLAUDE.md`, partes A e B, e `CONTRIBUTING.md`, incluindo a regra de atualizar a avaliação no mesmo PR.
3. `docs/desenvolver/escada-de-testes.md`.
4. `docs/referencia/authz.md` e os ADRs do teste entre contas: 0027, 0038 a 0043 e 0057.
5. As skills `run-scan`, `fix-reachability`, `test-product` e `triage-findings`.
6. `evals/README.md`, `evals/protocolo-da-rodada-cega.md` e os casos `evals/cases/clinica-piloto/`, `vampi/` e `crapi/`.
7. O `README.md` da rodada Terra citada acima.

Este trabalho torna a ferramenta **mais completa e mais barata de operar**. Ele acrescenta verificações de autorização e de configuração com o mesmo nível de cuidado das existentes: só ambiente de teste autorizado, só pela cerca de escopo, limites respeitados, escrita só com a carta. Se algum item ficar fora do que você pode fazer, registre no relatório o item, o motivo e o que faltou. Não recuse em silêncio.

## Itens

| Item | O que fazer | Critério de aceite |
| --- | --- | --- |
| A. Esperar sem gastar | Um jeito de esperar uma execução com **um comando que bloqueia** até ela terminar ou até um prazo, por exemplo `hdast wait --run <id> --timeout <s>`; você decide a forma no ADR. Ele imprime pouco: fase, percentual e, no fim, o estado e o código de saída da execução. Se o shell do agente tiver limite de tempo por comando, o agente repete o comando de espera, e cada chamada cobre minutos, não segundos. Atualize `run-scan` e `test-product`: lançar, esperar com o comando novo e **não** ler `scan-progress.json` em laço. Contrato do envelope e códigos de saída documentados | Testes do comando com execução terminada, em andamento, parada e inexistente; skill atualizada; teste de contrato das skills |
| B. Conferência da atribuição em massa | Quando não houver leitura provada da **mesma conta** no mesmo modelo de caminho, a verificação `mass_assignment` repete a leitura provada de outra conta (mesmo método `GET`, mesmo caminho) **com a conta que escreveu**, pela cerca e dentro dos limites. A leitura de antes e a de depois são feitas da mesma forma. Isso vale para `PUT`/`PATCH` (`update_reader`) e para a leitura do recurso criado no `POST` | Testes de unidade com dois contratos; no laboratório, Clínica Piloto (perfil com escrita e leitura provadas por contas diferentes) e VAmPI: o achado sai onde a falha existe e nada sai no modo seguro |
| C. CORS | Verificação nova, só de leitura: para algumas operações `GET` provadas pelo `probe`, com teto pequeno e configurável, o mesmo pedido com um cabeçalho `Origin` de origem estranha e inexistente (por exemplo um nome sob `.invalid`, gerado por execução). Avalie `Access-Control-Allow-Origin` e `Access-Control-Allow-Credentials` pela regra do CORS: origem refletida **com** credenciais é a classe mais grave; `*` sem credenciais é aviso baixo ou informativo. Uma só ocorrência por combinação de política, não uma por operação. Decida no ADR onde mora (estágio próprio ou dentro de um existente), a severidade, o CWE e a OWASP | Testes com respostas sintéticas de cada classe; no laboratório, a Clínica vulnerável dá o achado, a segura não, e o VAmPI roda sem erro e com o resultado que a política dele mostrar |
| D. Par automático entre contas do mesmo papel | Quando a carta traz duas ou mais contas de um papel **não** listado em `authz.shared_roles` e a escrita está autorizada (`authz.allow_writes`), o `authz` passa a montar o par sozinho, sem depender do roteamento que o agente escolheu:<br>1. para cada operação `POST` de criação provada pelo `probe`, cria um recurso **como a conta A** desse papel, com dados novos pelas regras do perfil;<br>2. confirma que **A** lê o recurso criado pelo `GET` por identificador da mesma família, com o mesmo mecanismo da leitura do recurso criado no `POST` da atribuição em massa;<br>3. tenta ler o mesmo identificador **como a conta B**.<br>Achado: B recebe o recurso de A. Sem achado: B recebe 401, 403 ou 404. A não consegue criar ou ler: `not_tested`, com motivo. Objetos que A não criou nesta execução não entram. Recursos criados entram em `created_resources`. Respeite o teto de pedidos de escrita e os limites do perfil. Sem escrita autorizada: `not_tested` com o motivo de sempre | ADR com a regra, os motivos de `not_tested` e o cuidado contra alarme falso; testes com dois contratos; no laboratório, a Clínica vulnerável mostra o acesso entre as contas de paciente, a segura não, e a comparação entre médicos continua pulada. No VAmPI, entre as duas contas `user`, o resultado que a falha dele permitir |
| E. Conferência final da triagem | Na skill `triage-findings` (e em `test-product`), um passo final: conferir que todo achado alto de `findings.json`, de qualquer origem, tem anotação no `triage.json` antes de entregar. Se couber, a CLI ajuda com uma verificação só de leitura que lista os altos sem anotação, para o agente não depender de memória | Texto da skill; teste se houver comando ou campo novo |
| F. Avaliação no mesmo PR | Atualize os casos para medir as regras novas:<br>1. **Clínica:** o `match` da H3 passa a reconhecer o achado de CORS. A H5 e a H6 já estão no gabarito.<br>2. **VAmPI:** a carta passa ao formato atual, com escrita autorizada para o teste entre contas, e as falhas que as verificações agora cobrem (V3, acesso a objeto de outro usuário; V4, atribuição em massa) passam a `detectable: true`, com `match`, **só se** o laboratório provar.<br>3. **Histórico:** preserve o caso antigo do VAmPI como `vampi-estrito`, como foi feito com a Clínica na V1.5.2.<br>4. **crAPI:** faça o mesmo se der; senão, registre o que falta.<br>O teste de vazamento do `prepare` precisa continuar passando | `tests/unit/evals` e o teste de vazamento passam; `prepare` e `approve` funcionam nos casos alterados |

## Como trabalhar

- **Worktree e branch.**
  - O Claude Code já criou a worktree `C:\harness-dast-wt\v1-5-5`, na branch `feat/v1-5-5-achar-mais`, a partir da `develop`. Trabalhe só nela; **nunca** mexa em `C:\harness-dast`.
  - Os subagentes usam worktrees próprias a partir desta branch. Depois de juntar, remova as worktrees e apague as branches dos subagentes.
- **Modelos.**
  - Coordenador: você, GPT 6.1 Sol, esforço xhigh.
  - Programadores: GPT 6.1 Terra, high, no máximo três ao mesmo tempo, com arquivos que não se cruzam.
  - Documentação: GPT 6.1 Terra, medium.
  - QA independente: GPT 6.1 Terra, high, que não programou e tenta quebrar. Ele confere em especial:
    - a regra "qualquer API": procura nomes da Clínica ou do VAmPI no código, nas skills, nas mensagens e nos testes de comportamento;
    - que nada novo escapa da cerca de escopo, dos limites ou da exigência de escrita autorizada.
- **ADR:** números **0061 em diante**, com status "Proposto". Comando novo, verificação nova, motivo novo de `not_tested` e mudança de envelope são mudanças de contrato e exigem ADR.
- **Versão:** 1.5.5. Atualize `CHANGELOG.md`, `CLAUDE.md` (o parágrafo de estado), `docs/roadmap.md`, `docs/decisoes/README.md`, `docs/referencia/` e `pyproject.toml`, e escreva `docs/arquivo/reviews/relatorio-v1.5.5.md`, curto, no formato do `relatorio-v1.5.4.md`.
- **Testes:**
  - Degrau 2 para tudo: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run mypy --platform linux`, `uv run lint-imports`, `uv run vulture` e `uv run pytest -q`, todos verdes, com a suíte inteira depois da última mudança.
  - Degrau 3 para os itens B, C e D, pelos testes de integração (`tests/integration/`, marcadores `integration` e `lab_fast`), na Clínica Piloto **e** no VAmPI, nos modos que cada alvo tem.
    - O Docker fica em `%LOCALAPPDATA%\Programs\DockerDesktop\`. Se travar com `sailor-ingest.sock`, renomeie `%LOCALAPPDATA%\Docker\run`; nunca use "Reset to factory defaults".
    - Derrube pilhas que sobraram antes de subir (`docker compose ls -a`).
    - Use `HDAST_ZAP_API_KEY` aleatória no processo e termine sempre com `stack down`.
  - **Sem rodada cega nesta versão.** O dono vai pedir as rodadas depois, em pelo menos duas APIs, pelo `evals/protocolo-da-rodada-cega.md`. Deixe os casos prontos para isso (item F).
- **Parte B do `CLAUDE.md` no laboratório:**
  - só comandos `hdast` e o suporte de testes;
  - nada de `curl` contra o alvo;
  - não leia `.env`;
  - nunca rode `hdast profile approve` nem `secret set`/`delete`.
- **Detector de segredos:** não afrouxe o `gitleaks`.
- **Commits** em Conventional Commits, em português.
- **Push e PR:** faça push da branch e abra o PR para a `develop`. **Não junte o PR.** Nunca mexa na `main` nem na `develop` diretamente.

## Relatório final (a sua última mensagem)

Em português:

1. Para cada item de A a F:
   - **feito**, **feito em parte** ou **não feito**, com o motivo;
   - arquivos;
   - testes;
   - prova, dizendo **em quais APIs**.
2. As decisões de contrato (forma do comando de espera, onde mora o CORS, severidades, motivos novos de `not_tested`) e por quê.
3. O que cada regra **não** cobre: os limites que valem para qualquer API.
4. Recusas ou limites do seu modelo, se houver.
5. Gates e integração com números.
6. Link do PR, branch e último commit.
7. Subagentes e modelos usados.
8. O que o Claude Code precisa saber para revisar e juntar, e o que o dono precisa saber para pedir as rodadas cegas em duas APIs.
