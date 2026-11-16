# Plano: varredura mais rápida sem perder qualidade, e personalização persistente

Data: 2026-11-16, revisão 2. **Status: proposta de desenvolvimento; nada deste plano está implementado.** Nenhum tráfego de teste é autorizado por este documento.

A primeira versão deste plano foi escrita sobre a V1.5.4 e criticada por um Terra 6.1 medium independente (seção 12). A cópia dela está fora do repositório, em `C:\harness-dast-artefatos\planos\`. Esta revisão, feita a pedido do dono do projeto, muda três coisas:

1. **Qualidade não se troca por velocidade.** Toda aceleração precisa provar que acha as mesmas falhas. Quando a prova não for possível, a aceleração não entra ou fica desligada.
2. **Testes de cada versão sem dezenas de varreduras.** A prova passa a ser em camadas, da mais barata para a mais cara. Cada versão tem um orçamento fechado: cerca de 1 a 2 horas de laboratório, rodando sozinho, em vez das 8 a 12 horas da primeira versão.
3. **Ordem e tamanho.** A velocidade vem primeiro, porque é medível e barata. A personalização vem depois, em fatias. O paralelismo vira **opcional**, só se a medição mostrar que ainda compensa.

O resultado pretendido continua o mesmo: o agente transforma informações do produto em uma estratégia reutilizável, e a CLI valida, executa e registra cada decisão.

## 1. Pré-requisitos e ordem

### 1.1 Antes da primeira versão deste plano

- **A V1.5.5 integrada à `develop`.** Ela traz:
  - o comando que espera a execução sem consultas repetidas;
  - a releitura da atribuição em massa com a conta que escreveu;
  - a verificação de CORS;
  - o par automático entre contas do mesmo papel;
  - a conferência final da triagem.

  Este plano **não** reimplementa nada disso; usa como base.
- **As rodadas cegas da V1.5.5 em duas APIs** (Clínica Piloto e VAmPI), pedidas pelo dono. Elas viram a **referência de qualidade** das versões seguintes.
- **A V1.6 (confirmação e reteste) e o piloto num produto real (M7)** continuam no [ciclo anterior](2026-11-14-ciclo-v1-3-a-v1-8.md) e não são cancelados. A ordem entre elas e este plano é decisão do dono. Recomendação: o piloto real antes da V1.9 deste plano, porque a personalização precisa aprender com um produto que não foi feito por nós.

### 1.2 Versões

Os rótulos V1.7 a V1.10 são propostos e serão reconciliados com a numeração vigente ao abrir as branches.

| Versão | Entrega | Ganho esperado | Condição para avançar |
| --- | --- | --- | --- |
| V1.7: Velocidade serial sem perda | Medição por regra e por operação; ritmo único no proxy, sem atraso duplicado no ZAP; seleção de regras por tecnologia declarada na carta (opcional, decisão do dono) | Varredura mais curta com a mesma cobertura; a meta é pelo menos 15% na mediana | Equivalência de cobertura provada e as falhas de controle achadas nas duas APIs |
| V1.8: Base da personalização | Envelope autorizado, `strategy.yml` versionado, compilação e validação sem tráfego, migração | Preparar e reaproveitar escolhas sem reentrevistar tudo | Perfil antigo equivalente; nenhuma estratégia alarga o envelope |
| V1.9: Conhecimento executável do produto | Contas, dados, fluxos, observação de efeito, autenticação e reutilização validada | Menos tentativas inválidas e configurações incoerentes; segunda execução sem retrabalho | Primeira execução e reexecução em contextos separados, nas duas APIs, sem perder detecção |
| V1.10: Paralelismo (opcional) | Até dois executores isolados, fila comum, reserva de conta e recurso, exclusividade para testes de tempo | Sobrepor trabalho independente dentro do mesmo teto | Só começa se a V1.7 mostrar que o trabalho paralelizável ainda pesa (seção 6.1) |

Cada versão só começa depois do aceite da anterior. Dentro de uma versão, os PRs são pequenos e seguem a ordem indicada.

## 2. Evidência que orienta o desenho

Rodada Terra 6.1 da V1.5.4, semente 20, Clínica Piloto, modo vulnerável. Evidência em `C:\harness-dast-artefatos\rodadas-cegas\piloto-terra61-v154-random-2026-11-15\`.

- **Tempos:** varredura de 1.283 s, `run` de 1.362 s (a varredura é 94% do `run`), 28 operações varridas.
- **Pedidos:** 13.905 pedidos liberados na varredura, média de 10,8 por segundo, com teto de 20. O piso aritmético a 20 por segundo seria 695 s. Esse número é um limite otimista, não uma previsão.
- **Tempo por regra do ZAP** (soma das operações, `metrics.json` da execução). As regras mais caras:

| Regra | Tempo | Observação |
| --- | --- | --- |
| 90036 SSTI cega | 101 s | Depende de tempo |
| 40018 SQL Injection | 100 s | Genérica, todos os bancos |
| 90020 Injeção de comando do SO | 84 s | |
| 40019 SQL por tempo, MySQL | 83 s | Específica de um banco |
| 40027 SQL por tempo, MsSQL | 83 s | Específica de um banco |
| 6 Travessia de caminho | 82 s | |
| 40021 SQL por tempo, Oracle | 58 s | Específica de um banco |
| 40022 SQL por tempo, PostgreSQL | 58 s | Específica de um banco |
| 40020 SQL por tempo, Hypersonic | 51 s | Específica de um banco |

As cinco regras de SQL por tempo, cada uma de um banco, somam **333 s (26% da varredura)**. Num produto que usa um banco só, quatro delas testam bancos que não existem nele.

O código atual mostra onde intervir:
- `application/scan_runner.py` percorre as operações em série;
- `application/scan_tokens.py` troca a conta pelo Replacer do ZAP, que é global, então dois trabalhos simultâneos na mesma sessão misturariam identidades;
- `domain/scan_policy.py` aplica um atraso fixo no ZAP, calculado da taxa, **além** do limitador do proxy.

A [documentação do ZAP](https://www.zaproxy.org/docs/desktop/ui/dialogs/options/ascan/) recomenda controle de taxa no lugar do atraso fixo e alerta para anti-CSRF com várias threads. As [regras ativas](https://www.zaproxy.org/docs/desktop/addons/active-scan-rules/) de SQL por tempo pedem pouca concorrência. Por isso o primeiro ganho é tentado no executor serial.

## 3. Regra de qualidade: o que é "sem perder qualidade"

"Sem perder qualidade" é um critério sobre o **trabalho feito** e a **capacidade de detectar**, não sobre o número bruto de alertas. Uma aceleração só entra se cumprir todos os itens abaixo. Cada item é eliminatório.

| Dimensão | Critério |
| --- | --- |
| Autorização | Zero pedido fora do escopo, da janela ou dos limites. Zero aprovação, limpeza ou segredo executado pelo agente |
| Cobertura planejada | As mesmas operações, contas, pontos de entrada, regras, força e pré-condições. Nenhuma exclusão nova escondida |
| Cobertura executada | Cada trabalho contado. Regra truncada, pulada ou interrompida conta como lacuna, mesmo com saída 0 do ZAP |
| Detecção | Toda falha de controle achada na referência continua achada, nas duas APIs |
| Falsos positivos | O modo seguro não ganha achado reproduzível causado pela mudança |
| Estado e identidade | Nenhuma troca de conta; recursos criados registrados; evidência atribuída à operação certa |

Não acelerar desligando regra, reduzindo força, encurtando o tempo útil de uma regra, removendo evidência ou usando o gabarito para escolher rotas.

**A única exceção controlada é a seleção por tecnologia (seção 5.3).** Ela pula regras que testam uma tecnologia que o produto não usa, e só quando o **dono do produto declara a tecnologia na carta**. Sem declaração, ou com "não sei", tudo roda como hoje. O relatório lista cada regra pulada e o motivo. Para o produto como declarado, a detecção é a mesma; o risco é a declaração estar errada, e a seção 5.3 diz como a ferramenta se protege disso.

## 4. Estratégia de testes enxuta (vale para todas as versões)

A primeira versão do plano pedia de 24 a 36 varreduras completas por versão, de 8 a 12 horas de laboratório. Esta revisão troca isso por **camadas**: cada mudança é provada no degrau mais barato que a prova, e só sobe se precisar. Ela segue a [escada de testes](../escada-de-testes.md).

### 4.1 As camadas

| Camada | O que prova | Como | Custo |
| --- | --- | --- | --- |
| T1. Equivalência sem alvo | Que o trabalho **planejado** é o mesmo: operações, contas, regras, força, pontos de entrada e pré-condições | Testes de unidade e de contrato com ZAP falso e relógio falso. Compara a matriz de cobertura da referência com a da mudança, item por item, não só o hash | Segundos; roda no CI |
| T2. Controles direcionados | Que cada **classe de falha** continua sendo achada, e o modo seguro continua limpo | Testes de integração `lab_fast`: para cada classe de falha de controle, uma ou duas operações, na Clínica Piloto (dois modos) e no VAmPI | 2 a 5 min por grupo; uns 20 a 30 min no total |
| T3. Varredura de controle | O **ganho de tempo** e a cobertura **executada** | Uma varredura reduzida e fixa: um subconjunto de 6 a 10 operações por API que contém pelo menos uma operação de cada classe de falha de controle. Mesma política de regras e mesma força da varredura completa. É escolhida uma vez, versionada em `tests/integration/`, e usada por todas as versões | 4 a 6 min por execução |
| T4. Varredura completa | Que nada quebrou fora do subconjunto | Uma varredura completa por API, só no modo vulnerável, no fechamento da versão | ~25 min por API, rodando sozinha |
| T5. Rodada cega | Que o **agente** consegue usar a versão sozinho | O [protocolo da rodada cega](../../evals/protocolo-da-rodada-cega.md), uma rodada por API, modo sorteado | ~35 min por rodada |

### 4.2 Como medir velocidade sem dezenas de varreduras

- **Pares na varredura de controle (T3), não na completa.** São 3 pares A/B por API, em ordem alternada, com reset do laboratório entre eles: 12 execuções de ~5 min, cerca de **1 hora**.
- **Extrapolação pela soma por regra.** Em execução serial, o tempo da varredura é a soma dos tempos por regra e por operação, que o `metrics.json` já registra. A extrapolação do subconjunto para a varredura completa é feita por esses tempos e **confirmada** pela única varredura completa do fechamento (T4). Se a confirmação divergir da previsão em mais de 10 pontos percentuais, a alegação de ganho fica inconclusiva.
- **Ampliar só se houver dúvida.** Se os três pares divergirem no sinal do ganho, ou a diferença entre eles passar de 10 pontos percentuais, faz-se mais dois pares. Com cinco ainda inconclusivos, a aceleração não é ligada por padrão e a hipótese é revista.
- **Meta registrada antes de medir, sem ajuste depois.** A meta da V1.7 é pelo menos 15% de redução na mediana por API, com todos os critérios de qualidade da seção 3.

### 4.3 Quando a rodada cega é obrigatória

A rodada cega mede o agente, não o motor. Ela só é obrigatória quando a versão muda o que o agente lê ou faz: skills, mensagens, comandos, fluxo de cadastro e alcance.

| Versão | Rodada cega |
| --- | --- |
| V1.7 (velocidade no motor) | **Não**, salvo se mudar skill ou mensagem. Basta T1 a T4 |
| V1.8 (personalização: contratos) | Sim, uma por API, no fechamento |
| V1.9 (personalização: reutilização) | Sim, uma por API, mais o estudo de reutilização da seção 6.3 |
| V1.10 (paralelismo) | **Não**, salvo se mudar skill ou mensagem |

### 4.4 Orçamento de laboratório por versão

| Item | Tempo aproximado, rodando sozinho |
| --- | --- |
| T2 controles direcionados | 30 min |
| T3 pares A/B (só versões de velocidade) | 60 min |
| T4 varredura completa, duas APIs | 50 min |
| T5 rodadas cegas, duas APIs (só quando obrigatória) | 70 min |
| **Total** | **~2 h 20 min** nas versões de velocidade (sem T5); **~2 h 30 min** nas de personalização (sem T3) |

Além disso, só com replanejamento explícito e registrado.

### 4.5 Validador independente, mais leve

Cada versão continua com um validador novo, GPT 6.1 Terra medium, que não implementou a entrega. Ele:
- revisa o código, os ADRs e as evidências;
- reproduz **os controles direcionados (T2) que escolher** e confere T1, T3 e T4 pelos artefatos;
- não refaz a varredura completa nem as rodadas cegas;
- decide **continuar**, **corrigir** ou **bloqueado**, com motivos.

Prova ausente nunca conta como sucesso. O parecer não substitui a revisão humana do `CONTRIBUTING.md`.

## 5. V1.7: velocidade serial sem perda

### 5.1 Medir onde o tempo vai

Instrumentar, por execução: fila local, espera de concessão do proxy, atraso do ZAP, tempo de rede, autenticação e CPU e memória. O tempo da regra e o tempo de parede ficam separados, porque podem se sobrepor. Parte disso já está no `metrics.json` (ADR 0031); completar o que faltar.

### 5.2 Ritmo único

Hoje o ZAP espera um atraso fixo **e** o proxy limita a taxa. A hipótese é que o atraso do ZAP seja redundante com o limitador.
- **Variante A:** como hoje.
- **Variante B:** atraso do ZAP reduzido ou retirado, com o limitador do proxy como única trava, no mesmo teto da carta.
- Todas as fontes de pedido (ZAP, `probe`, `authz`, `negative`, login, saúde) continuam passando pelo mesmo limitador.
- Pedido negado pela cerca é contado à parte.
- Um 429 provoca recuo temporário naquela execução, com `Retry-After` validado, número de tentativas limitado e prazo máximo. Ele nunca vira limite permanente, e a ausência de 429 nunca aumenta a taxa.

A variante B só é ligada por padrão se passar a seção 3 e a meta da seção 4.2.

### 5.3 Seleção de regras por tecnologia declarada (opcional)

- **Campo novo da carta**, com a frase do dono: as tecnologias do produto (por exemplo, o banco de dados). O campo vira um campo do perfil gerado por `hdast init --from-letter` e **muda a aprovação**.
- **Sem o campo, ou com "não sei":** todas as regras rodam, como hoje.
- **Com o campo:** as regras específicas de **outra** tecnologia da mesma família são puladas. Por exemplo, SQL por tempo para outros bancos. As regras genéricas (como a 40018) rodam sempre.
- **Proteção contra declaração errada:**
  - Se a ferramenta observar sinal de outra tecnologia (por exemplo, uma mensagem de erro de outro banco, nos sinais da cerca ou numa resposta), a execução registra a contradição, roda as regras puladas daquela família e avisa no relatório.
  - O mapeamento regra → tecnologia é uma tabela fixa no `domain`, com teste. Nunca vem do alvo.
- **Relatório e painel:** listam cada regra pulada e o motivo ("a carta declara o banco X").

Prova:
- T1: o plano de regras muda só nas regras daquela família.
- T2: as falhas de SQL da Clínica continuam achadas com a tecnologia declarada certa, e a contradição é detectada com uma declaração errada.
- T3: o ganho é medido.

Exige ADR, porque muda a carta, o perfil e a aprovação.

### 5.4 Aceite da V1.7

- T1: com a variante B, a matriz de cobertura é igual à da A. Com seleção por tecnologia, a matriz é igual exceto pelas regras declaradas como puladas.
- T2: todos os controles passam nas duas APIs e nos dois modos da Clínica.
- T3: meta de 15% atingida, ou a aceleração fica desligada por padrão com o motivo registrado.
- T4: a varredura completa confirma a previsão (seção 4.2) e acha o mesmo conjunto de falhas de controle da referência.
- Relógio falso prova pausas, recuo, bordas da janela e cancelamento. A auditoria do proxy prova o teto real de saída.

## 6. Personalização (V1.8 e V1.9) e paralelismo (V1.10)

### 6.1 O que continua valendo da primeira versão do plano

Os contratos de segurança da primeira versão continuam como requisitos e entram nos ADRs de cada versão. Em resumo:

- **Quatro camadas separadas:**
  - fatos do produto (pessoa, contrato ou observação com proveniência);
  - envelope autorizado (carta e aprovação);
  - estratégia persistente (o agente propõe, a CLI valida);
  - estado da execução (temporário).

  Observação nunca concede permissão.
- **Três classes de alteração:**
  - **automática**, dentro da faixa autorizada e sem reduzir qualidade;
  - **proposta pendente**, quando muda contrato, interpretação ou cobertura;
  - **decisão humana**, quando muda permissão, escopo, teto, janela ou política protegida.

  "Não sei / não está na carta" mantém o comportamento conservador.
- **`strategy.yml`** referencia `target.yml`, `data-rules.yml` e `flows.yml`, sem duplicar valores. Conflito ambíguo é recusado.
  - Cada escolha registra origem, justificativa, validade e estado (`proposed`, `validated`, `review_required`).
  - Mudança de ambiente, contrato, conta, autorização ou motor invalida as partes dependentes.
  - Nunca persistir tokens, cookies, respostas inteiras, credenciais, IDs de recursos ou gabarito.
  - Texto do contrato e do alvo é dado, nunca instrução.
- **Plano compilado e imutável**, vinculado à impressão digital da autorização. Revalidar a autorização, a janela, o prazo e o `stop` a cada concessão. Mudança de arquivo em disco não altera uma execução em andamento.
- **Mutações:** a intenção e o estado anterior são gravados antes do envio. Resultado desconhecido nunca é repetido às cegas nem tratado como sucesso.
- **V1.10:**
  - no máximo dois executores, cada um com ZAP, sessão, Replacer, CSRF e evidência próprios;
  - um coordenador dono da trava da pilha e um limitador global único;
  - reservas de conta e recurso com geração crescente (epoch);
  - testes de tempo em exclusividade global;
  - diário durável dos trabalhos.

**Condição nova para a V1.10 começar:** depois da V1.7, medir quanto da varredura é trabalho que **pode** rodar em paralelo, isto é, sem regras de tempo, sem mutação compartilhada e sem dependência entre regras. Se for menos de 40% do tempo da varredura, a V1.10 não começa: o ganho máximo não pagaria o risco. Hoje as regras de tempo e cegas somam mais de 8 dos 21 minutos, e um ZAP com a Clínica chegou a 2,5 GiB de memória para 6,7 GiB do Docker.

### 6.2 Aceite da V1.8 e da V1.9

Os aceites específicos da primeira versão continuam valendo:
- perfil antigo equivalente sem estratégia;
- alargamento recusado;
- corrida entre compilar, revogar e enviar coberta por teste;
- reutilização sem estado efêmero;
- invalidação seletiva;
- falha entre envio e gravação preservando intenção e estado anterior;
- dois produtos de vocabulário diferente sem nomes da Clínica no algoritmo ou na skill.

A prova segue as camadas da seção 4. **Não há pares A/B de velocidade** nessas versões, a menos que elas mexam no executor.

### 6.3 Estudo de reutilização (V1.9)

Uma rodada cega por API produz a estratégia. Depois da coleta, o coordenador aplica a lista de arquivos exportáveis e o verificador de segredos e vazamento. Uma segunda rodada, em contexto novo, recebe **só** esses arquivos, declarados na carta, e mede o retrabalho poupado. O protocolo da rodada cega precisa declarar e auditar esse canal antes de chamar o estudo de cego. Sem isso, o estudo é registrado como assistido.

## 7. Papéis na prova de cada versão

1. **Coordenador:** integra, prepara o ambiente, roda T2 a T5, guarda os artefatos e aprova o caso só pelo executor de avaliação.
2. **Validador:** Terra 6.1 medium novo, como na seção 4.5.
3. **Operador cego:** processo novo, sem esta conversa, sem o plano, sem o gabarito e sem resultados anteriores. Recebe só o pedido padrão e o `EVAL-BRIEFING.md`.

O validador nunca orienta o operador cego. Os planos e relatórios do coordenador, inclusive este documento, ficam fora da cópia cega (`evals/runner/exclusions.py` já exclui `docs/plans` e `docs/reviews`).

## 8. Organização do trabalho e riscos

- **PRs:** cada versão é dividida em PRs de contrato e domínio, aplicação e adaptadores, CLI e skills, e provas e documentação. De preferência, abaixo de ~400 linhas cada.
- **Delegação:** com delegação, cada um trabalha com arquivos exclusivos e worktree própria.
- **Coordenador:** mantém changelog, versão, índice de ADRs e roadmap.

| Risco | Medida |
| --- | --- |
| Acelerar e perder detecção | Seção 3 eliminatória; T1 compara a matriz item por item; T2 cobre cada classe de falha nas duas APIs |
| Varredura de controle não representar a completa | Subconjunto com todas as classes de falha; extrapolação por regra conferida pela varredura completa do fechamento |
| Declaração de tecnologia errada esconder falha | Padrão é rodar tudo; contradição observada reativa as regras da família; relatório lista o que foi pulado |
| Agente reduzir cobertura ao personalizar | Matriz mínima protegida, diff legível, aprovação humana para o que muda cobertura |
| Configuração antiga ganhar autoridade nova | Migração explícita e teste de recusa |
| Estratégia contaminada pelo laboratório | Proveniência, teste de vazamento e prova em duas APIs de vocabulário diferente |
| Token ou estado vazar na persistência | Lista de exportáveis, redação e teste de segredos |
| Paralelismo sem ganho real | Condição de entrada da V1.10 (seção 6.1) |

Ficam para um ciclo posterior: mais de dois executores, vários produtos no mesmo orçamento, técnicas novas de ataque, outros motores, novas formas de limpeza e teste contra produto real fora do piloto M7.

## 9. Entregáveis de cada versão

- ADRs novos, com contratos, aprovação, migração e falhas.
- Código, testes, skills e referências coerentes; nenhuma função futura descrita como existente.
- Gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run mypy --platform linux`, `uv run lint-imports`, `uv run vulture`, `uv run pytest`, mais as camadas T2 a T5 que a versão exige.
- Relatório da versão em `docs/reviews/`, parecer do validador e decisão de avanço.
- Medições em `evals/measurements/`; artefatos redigidos em `C:\harness-dast-artefatos\`.

O estado real continua no [roadmap](../roadmap.md). Este documento não altera a versão instalada, não aprova escopo e não declara nenhuma entrega validada.

## 10. Metas registradas antes de medir

| Versão | Meta | Se não atingir |
| --- | --- | --- |
| V1.7 | Pelo menos 15% menos tempo de varredura na mediana por API, com a seção 3 cumprida | A aceleração fica desligada por padrão; registrar o motivo e o gargalo |
| V1.8 | Perfil antigo idêntico; nenhuma estratégia alarga o envelope | Não avança |
| V1.9 | Segunda execução sem reentrevista nem retrabalho de alcance, com a mesma detecção | Reutilização fica como proposta, não automática |
| V1.10 | Pelo menos 10% menos que a V1.7 na mediana por API, sem mistura de identidade | Paralelismo não é ligado por padrão |

## 11. O que mudou em relação à primeira versão

| Primeira versão | Esta revisão | Por quê |
| --- | --- | --- |
| Personalização primeiro (V1.7), velocidade na V1.9 | Velocidade primeiro (V1.7) | É medível, barata e não depende da personalização |
| 24 a 36 varreduras completas por versão, 8 a 12 h | Camadas T1 a T5, ~2 h por versão | Prova no degrau mais barato; varredura completa só para confirmar |
| Rodada cega da Clínica em cada versão e modo | Uma por API, só quando o agente é afetado | A rodada cega mede o agente; o motor é medido por T1 a T4 |
| Rodada cega só na Clínica | Clínica e VAmPI | Evitar que a ferramenta aprenda uma API só |
| Seleção de regras por tecnologia proibida | Opcional, só por declaração do dono na carta, com proteção contra declaração errada | Cerca de 26% da varredura é SQL por tempo de bancos diferentes |
| Paralelismo como etapa certa | Opcional, com condição de entrada medida | As regras de tempo, que não podem rodar em paralelo, pesam muito |
| Escrito sobre a V1.5.4 | Base é a V1.5.5 | A V1.5.5 já entrega a espera sem consultas e as correções de BOLA, atribuição em massa e triagem |

## 12. Crítica independente da primeira versão

A primeira versão foi criticada em 2026-11-16 por um subagente novo GPT 6.1 Terra medium, sem herdar a conversa, só lendo. Ele apontou sete lacunas, que foram incorporadas e continuam valendo nos ADRs (seção 6.1):
- autorização mudar depois de compilar;
- executor voltar depois de perder a reserva;
- limitador global sem semântica de falha e reinício;
- hash do plano parecer prova de cobertura;
- estratégia reutilizada contaminar a rodada cega;
- métrica que permite escolher o resultado depois;
- falha entre a mutação e o registro.

Na segunda revisão, o mesmo crítico confirmou a incorporação.

Esta revisão 2 muda a estratégia de prova e a ordem. **Antes de abrir a branch da V1.7, ela deve passar por uma nova crítica independente**, focada em três pontos: a varredura de controle representa a completa? A extrapolação por regra é válida? A proteção da seleção por tecnologia basta?
