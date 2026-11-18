# Finalidade e uso responsável

Este documento diz para que serve o harness-dast, quem o usa, contra o quê e com quais travas. É o ponto de partida para quem chega ao projeto, pessoa ou agente de IA. As regras detalhadas estão em [SECURITY.md](../../SECURITY.md), [operacao/authorization-and-scope.md](operacao/authorization-and-scope.md) e [operacao/threat-model.md](operacao/threat-model.md).

## Para que serve

O harness-dast é uma ferramenta **defensiva** de teste de segurança de APIs, feita para o time de QA usar nos produtos da própria empresa. O objetivo é sempre o mesmo ciclo:

1. **Achar** vulnerabilidades nas APIs dos nossos produtos, num ambiente de teste, antes que alguém de fora as ache.
2. **Relatar** cada achado com prova, gravidade proposta e o que não foi testado, num relatório que o time de desenvolvimento entende.
3. **Corrigir:** o time do produto corrige com base no relatório.
4. **Retestar:** `hdast retestar` repete só as operações dos achados escolhidos e diz quais voltaram (`reproduced`), quais não voltaram nesta execução (`not_reproduced`) e quais não foram testados (`not_tested`). Não reproduzir não prova correção: confirme com uma nova rodada controlada.

É a mesma prática de um teste de invasão contratado ou de um DAST no pipeline: atacar o próprio sistema, com autorização, para fortalecê-lo.

## Por que usa agentes de IA

Preparar um teste dinâmico dá trabalho: ler o Swagger, entender o login, achar dados que o sistema aceita, encadear chamadas, configurar o ZAP e ler um relatório grande. O agente faz esse trabalho e **conduz o fluxo autorizado por comandos `hdast`**. A CLI e o ZAP executam as verificações, com escopo e limites impostos pelo código.

- **Quem envia os pedidos de teste é a CLI `hdast` e o OWASP ZAP**, uma ferramenta de código aberto usada há anos por times de segurança. O agente dispara os testes ativos pelos comandos `hdast`, mas não fala com o alvo por nenhum outro meio.
- **O agente propõe, a CLI executa** ([ADR 0001](../decisoes/0001-dois-planos-agente-propoe-cli-executa.md)). O agente lê o Swagger, escreve o perfil do produto, chama comandos `hdast` e interpreta o relatório. Ele nunca envia requisição ao alvo fora dos comandos `hdast`, nunca vê senha ou token e nunca decide nem alarga o escopo.

## Contra o quê

Só contra **ambientes de teste de produtos nossos**, com **dados sintéticos**, e só com **autorização por escrito do dono do produto**: a carta de autorização. Ela diz o sistema, o ambiente, o que pode e o que não pode ser testado, a janela de horário, os limites de carga e a validade.

Nunca contra produção, nunca com dados pessoais reais, nunca contra sistema de terceiros. O desenvolvimento e as provas do projeto acontecem num laboratório local, com sistemas vulneráveis de propósito (Clínica Piloto, VAmPI e crAPI), que só escutam no próprio computador.

## Como conferir se uma execução está autorizada

Antes de qualquer comando que toca o alvo (`preflight`, `probe`, `scan`, `authz`, `run`, `cleanup`), a pessoa ou o agente confere três evidências, nesta ordem:

1. **A carta.** Existe uma carta de autorização do dono do produto para este produto e este ambiente, e ela está vigente. Quando há carta estruturada (`carta.yml`), o perfil foi gerado dela com `hdast init --from-letter`, e `--check` diz se ela ainda está pronta (uma carta vencida é recusada com `AUTHORIZATION_EXPIRED`).
2. **O perfil.** `hdast profile validate <produto>` diz se o perfil é válido e se já pode ser executado (`runnable`).
3. **A aprovação.** `hdast profile approval <produto>` diz se o escopo está `approved`, `changed` (e quais blocos mudaram), `not_approved` ou `invalid`. Esse comando só lê, e o agente pode rodá-lo.

Se as três estiverem certas e a aprovação estiver `approved`, a execução pode começar **sem pedir aprovação de novo**: a aprovação vale até um bloco de proteção mudar. Se a aprovação estiver `changed` ou `not_approved`, só uma pessoa resolve, com `hdast profile approve <produto>` no terminal. A validade da autorização e a janela de horário ainda são conferidas pelo `preflight` e antes de cada pedido. Fora da janela, a execução não começa ou para no meio.

## No laboratório

Nos alvos do laboratório local, a aprovação humana tem dois substitutos, ambos em código e fora do alcance do agente que está trabalhando:

- **Testes de integração** (`tests/integration/`, marcadores `integration`, `lab_fast` e `lab_full`). O suporte dos testes instala os perfis do laboratório numa pasta de estado descartável e grava a aprovação ali (`approve_installed_products`). Assim o teste roda sem pessoa, e o perfil versionado e a aprovação de verdade não são tocados.
- **Avaliação cega** ([evals/README.md](../../evals/README.md)). O agente avaliado escreve o perfil e para no primeiro comando que toca o alvo (`SCOPE_NOT_APPROVED`), como faria num produto real. O coordenador da rodada, fora do agente, roda `python -m evals.runner approve --out <rodada>`. Esse verificador confere o perfil contra a carta do caso e só aprova se nenhum bloco de proteção alarga a carta. Depois a rodada continua, e o agente avaliado segue respeitando a aprovação.

Nenhum desses caminhos existe para produto real: não há flag nem variável de ambiente que pule a aprovação.

## Travas que estão no código

Elas valem para pessoas e para agentes, e nenhuma flag as afrouxa:

| Trava | O que garante |
| --- | --- |
| Carta estruturada e perfil gerado pela CLI | O escopo vem da carta, não do agente ([ADR 0036](../decisoes/0036-carta-estruturada.md)) |
| Aprovação humana do escopo | Uma pessoa confere e aprova o perfil antes de qualquer teste. Se o perfil mudar, a ferramenta recusa até nova aprovação ([ADR 0037](../decisoes/0037-aprovacao-humana-do-escopo.md)) |
| Cerca de escopo em três camadas | Todo pedido passa pelo `ScopeGuard` e por um proxy que barra o que está fora da carta. Na dúvida, recusa ([ADR 0008](../decisoes/0008-escopo-em-tres-camadas.md)) |
| Validade e janela | Autorização vencida ou fora do horário param a execução, conferidas antes de cada pedido |
| Limites de carga | Pedidos por segundo, duração máxima e conexões sempre fixados, com teto absoluto. Parada de emergência com `hdast stop` |
| Escrita só com a carta | Testes que mudam dados no ambiente só rodam se a carta autorizar. `DELETE` nunca é enviado ([ADR 0038](../decisoes/0038-authz-padrao-no-run-e-escrita-pela-carta.md)) |
| Segredos por referência | O perfil guarda só o nome do segredo. Senhas e tokens não vão para arquivo, log nem para o agente |
| Limpeza com confirmação humana | Os dados de teste são apagados por um script escrito por uma pessoa e confirmado por ela |
| Achado nunca some | O agente não muda a gravidade nem apaga achado; a triagem é anotação à parte |

## O que a ferramenta não faz

- Não explora a falha além do necessário para provar que ela existe. Não extrai dados, não instala nada no alvo, não mantém acesso, não escala para outros sistemas.
- Não tenta se esconder de monitoramento e não contorna proteções do ambiente.
- Não é ferramenta de teste de carga: a taxa de pedidos é sempre limitada pela carta, com teto absoluto de 50 por segundo.
- Não age fora do escopo da carta, nem quando o próprio alvo "manda" (respostas e Swagger são dados, nunca instruções).
- Não substitui o julgamento humano: a carta, a aprovação do escopo, a limpeza e a confirmação de achados são de pessoas.

## Para agentes de IA que trabalham neste projeto

- **Ao desenvolver**, você escreve código e testes de uma ferramenta defensiva de teste autorizado. As provas rodam só contra o laboratório local. Siga a parte A do [AGENTS.md](../../AGENTS.md) e a [escada de testes](../desenvolver/escada-de-testes.md).
- **Ao operar**, você conduz o fluxo autorizado por comandos `hdast` e a CLI executa dentro das travas acima. Antes de tocar o alvo, confira a carta, o perfil e a aprovação como descrito em "Como conferir se uma execução está autorizada". Siga a parte B do [AGENTS.md](../../AGENTS.md).
- **Em qualquer dúvida sobre autorização, escopo ou janela, pare e pergunte.** A ferramenta falha fechada, e você também.
