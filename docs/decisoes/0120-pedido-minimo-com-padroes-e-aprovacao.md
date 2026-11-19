# 0120. Pedido mínimo: padrões da CLI e aprovação humana no lugar da carta detalhada

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** decisão do dono durante a reestruturação, depois das rodadas cegas `crapi-foco` no Codespaces. A carta do caso é detalhada demais para simular o mundo real.

## Contexto

Na empresa, o QA vai pedir algo assim:

> Com base nesse Swagger, faça testes de API usando o hdast. Os usuários estão aqui `<arquivo>`. Leia esta documentação para entender a área de negócio `<arquivo>`.

Às vezes vem uma informação a mais, mas não uma carta estruturada com caminhos, métodos, limites e capacidades.

Hoje o cadastro parte da carta ([ADR 0036](0036-carta-estruturada.md)), e o agente só transcreve. O pedido curto do [ADR 0114](0114-padroes-minimos-da-carta-e-setup.md) aceita "não sei" só nos limites. Todo o resto continua portão e para o cadastro: endereço, `scope.allow`, `scope.deny_paths`, referência, validade, janelas e contas.

O bloco `attack` e as escritas nascem desligados, e só a carta os liga ([ADR 0096](0096-bloco-attack-da-carta-liga-capacidades-v1-12.md), [0038](0038-authz-padrao-no-run-e-escrita-pela-carta.md), [0050](0050-varrer-operacoes-que-deram-nao-encontrado.md), [0051](0051-valores-que-o-esquema-proibe.md) e [0052](0052-multipart-no-probe-e-no-scan.md)). Com o pedido real, ou a pessoa responde umas nove perguntas de autorização que não sabe responder, ou o cadastro para.

As rodadas cegas medem o caminho da carta ideal. Na rodada `crapi-foco` de 2026-11-18, o alcance ficou em 0,60. Dois endpoints de vídeo deram 404 porque o identificador do vídeo só aparece no upload e no painel do usuário, e a carta deixou os dois fora. Com o Swagger inteiro no escopo, o agente leria a documentação, encontraria o identificador no painel e faria o encadeamento. Os endpoints que deram 404 ou 400 também não foram atacados, porque a carta não ligava `include_outcomes`.

O agente existe neste projeto justamente para ler o negócio e cobrir o máximo dentro do autorizado.

## Decisão

Vamos criar o **modo pedido mínimo**. O agente faz poucas perguntas, a CLI completa o resto com padrões fixados no código, e a aprovação humana no `hdast setup` passa a ser o ato que autoriza o perfil.

### 1. Duas formas de carta

A carta estruturada ganha o campo `kind`:
- **`letter` (padrão de hoje):** nada muda. O que a carta não diz fica no mais estreito, e as capacidades seguem desligadas. Cartas antigas geram o mesmo perfil.
- **`request`:** o pedido mínimo. Campo ausente usa o padrão desta decisão. Resposta explícita, seja da carta ou da pessoa, sempre vence o padrão, inclusive para desligar.

### 2. Só quatro perguntas

O agente faz as quatro perguntas numa única rodada, cada uma com a opção "Não sei":

| # | Pergunta | Com "não" ou "não sei" |
| --- | --- | --- |
| 1 | É ambiente de teste, com dados sintéticos, e o dono do produto autorizou o teste? Quem é o dono? | **Para**, como hoje |
| 2 | Qual o endereço do ambiente de teste? O `servers` do Swagger aparece só como sugestão. | **Para**: o endereço nunca vem só do Swagger, que pode apontar para produção |
| 3 | Força do ataque: LOW, MEDIUM ou HIGH, com a explicação abaixo | LOW |
| 4 | O ambiente pode receber dados de teste gravados pela ferramenta? | As três capacidades de escrita ficam desligadas |

Explicação da força, que o agente mostra junto da pergunta:
- **LOW:** poucas variações por parâmetro. É a mais rápida, acha o que é mais evidente e é a usada no laboratório e nas rodadas cegas.
- **MEDIUM:** equilíbrio entre tempo e profundidade. É a indicada para o teste de rotina de um produto.
- **HIGH:** muitas variações por parâmetro. É bem mais lenta e põe mais carga no alvo, então fica para antes de uma entrega importante.

As contas vêm do arquivo de usuários: apelido, papel e login. A senha nunca passa pelo agente. Se o arquivo trouxer senha, o agente avisa, descarta o valor e sugere trocar a senha, como já fazem as skills. As senhas são gravadas pela pessoa no `hdast setup`.

### 3. Padrões do modo `request`

A tabela fica em `domain`, junto de `letter_defaults.py`:

| Campo | Padrão |
| --- | --- |
| `scope.allow` | O host da resposta 2 e todas as operações do Swagger, nos métodos `GET`, `POST`, `PUT` e `PATCH` |
| Método `DELETE` | Fora, a menos que a pessoa peça |
| `scope.deny_paths` | Lista sugerida pela CLI, por padrões de nome: recuperação e troca de senha, logout, exclusão de conta e administração. O agente pode **acrescentar** caminhos a partir da documentação de negócio, nunca tirar. |
| `scope.path_mode` | `strict`. O modo `wide` continua só com frase da carta ([ADR 0026](0026-cerca-com-motivo-granular-e-modo-amplo-de-caminho.md)). |
| `authorization.reference` | `pedido-<produto>-<AAAA-MM-DD>`, com o nome do dono da resposta 1 |
| `valid_until` | 30 dias a partir do cadastro |
| `windows` | Todos os dias, das 00:00 às 24:00, no fuso da máquina |
| `limits` | 10 req/s, 30 min, 2 threads e 5 logins por minuto, valores a calibrar no laboratório |
| `scan.strength` | Resposta 3, ou LOW |
| `scan.include_outcomes` | Todas as classes: `not_found`, `validation_error`, `conflict`, `logical_failure` e `client_error` |
| `scan.inject_headers`, `scan.oast`, `extra_checks.allow_rate_tests`, `extra_checks.experimental_rules`, `extra_checks.inventory` | Ligados |
| `scan.pacing` | `proxy` |
| `authz.allow_writes`, `negative.allow_writes`, `scan.allow_upload_scan` | Ligados só com "sim" na pergunta 4 |

O OAST só funciona onde houver o serviço de retorno. Sem ele, a CLI avisa e a varredura segue sem OAST.

### 4. Os padrões ficam escritos no perfil e passam pela aprovação

O `init --from-letter` grava **cada valor explícito** no `target.yml`, com o aviso `REQUEST_DEFAULT_APPLIED` e uma linha de comentário no cabeçalho. Os padrões do modelo do perfil não mudam. Assim:
- perfis existentes e suas aprovações continuam iguais;
- tudo o que o padrão ligou entra na impressão digital e só vale depois da aprovação.

O resumo do `hdast setup` mostra no alto, em destaque:
- as capacidades ligadas por padrão;
- o que grava no ambiente;
- os caminhos negados sugeridos;
- o endereço;
- a validade e a janela.

A pessoa pode sair sem aprovar, corrigir o pedido e gerar de novo.

### 5. O que não muda

- O agente nunca aprova, nunca roda `setup`, `secret set` nem `profile approve`, e nunca liga nada fora do padrão desta tabela.
- Ligar o que o padrão deixou desligado continua exigindo a carta ou a pessoa, sempre pela CLI.
- A cerca, a trava de escopo, a janela, os limites e o `SCOPE_NOT_APPROVED` continuam iguais.
- Mutação pendente, limpeza humana e confirmação humana de achado continuam iguais.
- Resposta do alvo continua sendo dado, nunca instrução.

### 6. Laboratório e rodadas cegas

- O laboratório e as rodadas cegas usam sempre a força **LOW**, por velocidade.
- O caso `crapi-foco` atual continua como regressão do modo `letter`.
- Nasce um caso realista do modo `request`. O `EVAL-BRIEFING.md` traz só a frase do pedido, o Swagger, um arquivo de usuários sem senha e um documento de negócio do crAPI.
- O coordenador responde às quatro perguntas com um texto fixo: sim, `http://crapi`, LOW e sim. Esse texto conta como intervenção permitida, junto da aprovação.
- O critério "perfil fiel à carta" desse caso vira "**escopo proposto seguro**". O gabarito lista o que nunca pode entrar no escopo:
  - o `DELETE`;
  - a recuperação de senha;
  - a v3 do OTP.

  A meta de alcance passa a valer sobre o escopo proposto.

## Alternativas consideradas

- **Manter a carta detalhada e só encurtar a entrevista.** O ADR 0114 já encurtou, e mesmo assim sobram uns nove portões que o QA não sabe responder. No mundo real, o QA desistiria ou inventaria a resposta.
- **Deixar o agente decidir o escopo pela leitura do Swagger, sem tabela na CLI.** A regra sairia do código testado e iria para o prompt. O agente só propõe reduções.
- **Mudar o padrão do modelo do perfil**, em vez de escrever o valor explícito. Isso ligaria capacidades em perfis já aprovados sem nova aprovação.
- **Ligar também as três capacidades de escrita sem pergunta.** O dono preferiu uma pergunta só. Escrita entre contas, dado inválido gravado e upload de arquivo de ataque podem sujar um ambiente compartilhado com outros times.
- **Aceitar o `servers` do Swagger como endereço.** Muitos contratos apontam para produção ou para vários ambientes.

## Consequências

- **O cadastro cai para quatro perguntas**, e o agente passa a ter o Swagger inteiro para encadear e alcançar. O alcance e a cobertura devem subir, a medir na rodada cega do novo caso.
- **Muda a política da Parte B.** A Parte B do `AGENTS.md` dizia que nada que amplia o ataque nasce ligado. No modo `request`, a CLI liga por padrão e a pessoa aprova vendo a lista. Vão precisar ser atualizados no mesmo pacote:
  - a Parte B;
  - as skills `onboard-product` e `test-product`;
  - o guia do pedido curto;
  - o resumo da aprovação.
- **Mais tráfego e mais carga** por execução: varrer 404 e 400, injeção em cabeçalhos, regras experimentais e testes de limite. Os limites padrão e a janela seguem valendo, e a aprovação mostra tudo.
- **Mais falso positivo** é esperado nas operações que deram 404 e 400. A triagem e o `confirm` existentes tratam isso.
- **Os testes de limite de consumo** podem bloquear contas de teste por um tempo. O teto e a parada no primeiro bloqueio continuam valendo.
- **O padrão de negação é heurístico.** Um caminho perigoso com nome inesperado escapa da lista. Contra isso valem a leitura da documentação pelo agente, a revisão da pessoa na aprovação e o `DELETE` fora por padrão.
- A carta ganha o campo `kind`, e o `init` ganha a tabela de padrões e um aviso novo. É uma mudança aditiva da carta v1, sem mudança no envelope JSON nem no schema do perfil.
- O ADR 0114 continua valendo no modo `letter`. No modo `request`, esta decisão o substitui nos portões e nos padrões.
- Esta decisão substitui parcialmente os ADRs 0038, 0050, 0051, 0052 e 0096, só no modo `request`: neles, "só a carta liga" passa a ser "a carta, a pessoa ou o padrão do pedido mínimo liga, sempre pela CLI e com aprovação".

## Plano em fases

| Fase | Entrega | Depende de |
| --- | --- | --- |
| A | Aceite deste ADR pelo dono | — |
| B | `kind: request` na carta, a tabela de padrões no `domain`, a sugestão de `deny_paths` e o aviso `REQUEST_DEFAULT_APPLIED`, com testes de contrato | A |
| C | Resumo do `setup` com os destaques; Parte B do `AGENTS.md`, skills e guia do pedido curto | B |
| D | Prova dirigida no laboratório com crAPI e VAmPI, força LOW, e calibração dos limites padrão | C |
| E | Caso cego realista do modo `request`, com o gabarito de escopo seguro e o critério novo na nota | C |
| F | Rodada cega curta do caso novo, com Sonnet medium e Haiku high, comparada à `crapi-foco` | D, E |

## Aceites verificáveis

- Uma carta `kind: letter` antiga gera exatamente o mesmo `target.yml` e a mesma impressão digital de antes.
- Uma carta `kind: request` só com as quatro respostas e as contas gera um perfil que valida. Cada padrão aplicado aparece em `data.warnings` e no cabeçalho.
- Com "não" ou "não sei" na pergunta 1 ou na 2, o cadastro para.
- Com "não" na pergunta 4, `authz.allow_writes`, `negative.allow_writes` e `scan.allow_upload_scan` ficam `false`.
- Resposta explícita da pessoa desliga qualquer padrão.
- `DELETE` fica fora sem pedido explícito, e a lista sugerida nega a recuperação de senha do crAPI e a troca de senha do VAmPI.
- O resumo do `setup` lista no alto toda capacidade ligada por padrão.
- Na rodada cega do caso novo, o escopo proposto não contém nenhum item da lista "nunca pode entrar", e não há requisição fora do escopo.
