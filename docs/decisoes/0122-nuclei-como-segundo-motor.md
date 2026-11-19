# 0122. Nuclei como segundo motor, atrás de uma cerca básica

- **Status:** Aceito
- **Data:** 2026-11-19
- **Origem:** Spike do Nuclei de 2026-11-19 ([relatório na branch `spike/nuclei`](https://github.com/MarcosQuintino0/harness-dast/blob/spike/nuclei/docs/reviews/2026-11-19-spike-nuclei.md)) e decisões do dono na mesma data. Altera o [ADR 0102](0102-inventario-de-versoes-e-documentacao.md) (inventário), o [ADR 0120](0120-pedido-minimo-com-padroes-e-aprovacao.md) (pedido mínimo) e o [ADR 0121](0121-digests-empacotados-e-build-so-no-clone.md) (digests empacotados).

## Contexto

O ZAP ataca o que o contrato descreve. Ele não procura falhas conhecidas de produtos de prateleira (CVE de Spring, Tomcat, nginx, Jenkins), configurações erradas nem o que ficou exposto fora do contrato, como o Actuator aberto, arquivos de configuração e painéis. O Nuclei, da ProjectDiscovery (licença MIT), traz milhares de modelos de assinatura para essas classes.

O spike mediu o Nuclei atrás da cerca nos três alvos do laboratório e num alvo Spring Boot com Actuator aberto:

| Critério | Medida | Resultado |
| --- | --- | --- |
| Ganho real | 0 achados exclusivos na Clínica Piloto, no VAmPI e no crAPI. No alvo Spring: 13 exposições do Actuator, com a seleção relaxada | Só em parte |
| Escopo | Pedidos iguais às linhas da auditoria em 13 execuções e nenhum fora da cerca. `Host` divergente e redirecionamento para fora foram negados. A rede interna não resolve nomes externos | Atendido |
| Ruído | 0 achados médios ou maiores falsos no VAmPI e no crAPI | Atendido |
| Tempo | No máximo 10 s (321 modelos, 329 pedidos, `-rl 50`) | Atendido |
| Custo-benefício | O ZAP com as regras 40034 e 40035 religadas deu 0 achados nos 4 alvos, inclusive no Actuator aberto | O Nuclei ganha onde o ZAP não olha |
| Login | Token ausente de argumentos, logs e artefatos nos dois caminhos medidos | Atendido, com ressalvas |

**Por que a seleção estrita rendeu pouco.** O ganho no laboratório foi pequeno porque os alvos são APIs de estudo, sem os produtos que os modelos conhecem. Além disso, a seleção exigia que cada modelo coubesse inteiro no escopo do Swagger: só 0 a 53 modelos rodavam por alvo, dos 7.852 que passaram nos vetos. A maioria dos modelos de CVE consulta endereços que nenhum Swagger declara, como `/manager/html` e `/admin`.

**A decisão do dono.** O Nuclei é útil em produtos reais, e o dono decidiu adotá-lo como segundo motor completo, atrás de uma cerca básica que segura só o que evita dano.

**O que o spike corrigiu no desenho:**
- os modelos de Actuator ficam em `http/misconfiguration/`;
- `stop-at-first-match` é inofensivo;
- o contêiner trava na partida se a entrada padrão ficar aberta;
- o login pelo Replacer do ZAP prende o Nuclei à janela do `scan` e gerou 77% dos alertas passivos do ZAP.

## Decisão

Vamos acrescentar o Nuclei como **segundo motor** do hdast. A CLI decide, o contêiner executa e a cerca confere cada pedido.

### Imagem e manifesto
- A imagem `docker/nuclei` traz o binário do Nuclei e os modelos `nuclei-templates` em versões fixas.
  - Cada versão tem pelo menos duas semanas de publicação e SHA-256 conferido contra o arquivo de checksums da própria release. O spike usou o Nuclei v3.11.1 e os modelos v10.5.1.
  - O usuário não é root e não há atualização em execução.
- A imagem entra no `images.lock.json`, que passa ao `schema_version` 2 (estende o ADR 0121).
- O build gera um **manifesto** com o arquivo, o SHA-256, o protocolo, os métodos (inclusive os da primeira linha dos pedidos `raw`), as flags e as etiquetas de cada modelo. A CLI decide pelo manifesto e nunca lê os modelos em tempo de execução.

### Modelos admitidos
- **Admitidos:** todos os modelos HTTP do catálogo, inclusive os `raw`, desde que nenhum veto se aplique.
- **Vetados sempre:**
  - `unsafe`: pedidos malformados de propósito, que podem confundir a cerca;
  - `code` e `headless`: rodam código ou navegador na máquina;
  - OAST (`interactsh`): manda dados para servidores públicos;
  - modelos DAST e de fuzz, que repetem o ZAP;
  - as etiquetas `dos`, `intrusive`, `bruteforce`, `fuzz` e `default-logins`, que derrubam o ambiente ou bloqueiam contas.
- **Pelos métodos de cada modelo, a CLI escolhe** os que o escopo do Nuclei permite:
  - modelos que gravam não entram sem a permissão de escrita;
  - modelos com `DELETE` só entram com o pedido explícito da pessoa.

### Cerca básica do Nuclei
Durante a etapa `nuclei`, a CLI aplica à cerca uma **política própria do Nuclei**, derivada do perfil aprovado e restaurada no fim, inclusive após falha:

| Regra | Valor |
| --- | --- |
| Hosts | Só as origens aprovadas do produto. Redirecionamento e `Host` divergente continuam negados |
| Caminhos | Qualquer caminho dessas origens, dentro ou fora do Swagger |
| `scope.deny_paths` | Continuam valendo |
| Leitura (`GET`, `HEAD`, `OPTIONS`) | Liberada |
| Escrita (`POST`, `PUT`, `PATCH`) | Só com a permissão de escrita de dados (a pergunta 4 do pedido mínimo, `attack.allow_data_writes`, ou a frase da carta) |
| `DELETE` | Só a pedido explícito da pessoa |
| Ritmo | `limits.requests_per_second` do perfil |
| Auditoria | Todos os pedidos, como hoje |

Esta é uma forma de modo amplo de caminho restrita ao Nuclei. Como exige o [ADR 0026](0026-cerca-com-motivo-granular-e-modo-amplo-de-caminho.md), ela só vale com autorização explícita. O ZAP e as outras etapas continuam com o escopo estrito.

### Execução
- O Nuclei roda num contêiner de uso único na rede interna `zap_net`, atrás da cerca.
  - **Opções:** `-ni` (sem OAST), `-duc`, `-pt http`, `-rl` igual a `limits.requests_per_second`, concorrência baixa, `-jsonl -omit-raw`, `-proxy` para a cerca e sem `-fr`.
  - **Contêiner:** `cap_drop: ["ALL"]`, `read_only`, `no-new-privileges`, `tmpfs` e limites de memória e de processos.
- O runner liga a entrada padrão a `/dev/null`, impõe um prazo e derruba o contêiner se ele estourar. O `hdast stop` e o `KILL` também o derrubam.
- **No `run`:** vira a etapa `nuclei`, depois do `scan` e antes do `authz`, com `--nuclei/--no-nuclei`. O `run --only` a pula.
- **Sozinho:** ganha um comando próprio, `hdast nuclei`, como `scan`, `authz` e `negative`.

### Login
- Usa o arquivo de segredos do Nuclei (`-sf`):
  - gravado pela CLI em `tmpfs`, com modo `0400`, dono igual ao usuário do contêiner e montagem só leitura;
  - apagado no fim, inclusive quando o runner falha;
  - consome o mesmo orçamento de logins (`login_budget`).
- O token nunca vai para argumento, variável de ambiente nem log.
- Com login, só rodam modelos de leitura (`GET`, `HEAD`, `OPTIONS`).

### Saída e relatório
- A saída passa por uma projeção por **lista branca**. Do valor extraído ficam só o tipo, a contagem e o tamanho em bytes; `curl-command`, `request`, `response` e `extracted-results` são descartados (o Nuclei traz `curl-command` mesmo com `-omit-raw`).
- Os achados ficam em `nuclei.json` e numa seção própria do relatório:
  - modelo `NucleiFinding`, com `origin: "nuclei"`, identificador com prefixo `U-` e `NUCLEI_FINGERPRINT_VERSION` próprio;
  - impressão digital = modelo + método + caminho.
- **Gravidade fixa no domínio:** `critical` e `high` viram alta, `medium` vira média, `low` vira baixa, `info` e `unknown` viram informativa. O agente não a altera.
- **Tecnologias:** o que é só identificação vai para a seção "Tecnologias identificadas" e não vira achado.
- **Integração com o resto:**
  - o gate de severidade soma os achados do Nuclei;
  - a triagem casa pela impressão digital;
  - o `confirm` repete o modelo e o relatório chama isso de reprodução;
  - o reteste roda só os modelos dos achados abertos.

### Carta, pedido mínimo e aprovação
- **Chaves novas**, falsas por padrão no perfil para manter as aprovações antigas:
  - `extra_checks.nuclei` liga o motor;
  - `extra_checks.nuclei_login` liga o login;
  - `extra_checks.nuclei_wide_paths` libera caminhos fora do Swagger.

  Na carta, elas aparecem como `attack.nuclei`, `attack.nuclei_login` e `attack.nuclei_wide_paths`.
- **No pedido mínimo:**
  - `nuclei` e `nuclei_login` vêm ligados por padrão;
  - uma 5ª pergunta pede o "sim" para `nuclei_wide_paths`: "O Nuclei pode testar qualquer endereço do produto, inclusive fora do Swagger? Escrita só se você disse sim à pergunta 4."

  Isso altera o ADR 0120.
- **Na carta assinada,** cada chave só vale com a frase do dono.
- **Na impressão digital da aprovação** entram as três chaves, a versão do manifesto e a política do Nuclei. O resumo do `setup` mostra em linguagem simples:
  - a versão dos modelos;
  - quantos rodam;
  - se há login;
  - se os caminhos são amplos;
  - se há escrita.
- **Fora do Swagger,** a cerca libera os endereços de exposição conhecidos por inteiro. Neste ponto este ADR substitui o ADR 0102, que nunca ampliava o escopo.
- O agente nunca liga essas chaves sozinho. O `AGENTS.md` e o `CLAUDE.md` as acrescentam à lista.

### Decisões sobre as opções levantadas pelo dono
1. **Comando `hdast nuclei` próprio:** sim, decidido acima.
2. **Seleção pela lacuna do ZAP:** fica fora. O spike mediu sobreposição zero: as regras de arquivos ocultos do ZAP não acharam nada nos 4 alvos. A lacuna seria o motor inteiro. Pode ser reaberta se o uso real mostrar sobreposição.

## Alternativas consideradas

- **Nuclei só para exposições conhecidas** (versão anterior desta proposta). Descartada pelo dono: deixa de fora os modelos de CVE, que são o maior ganho esperado em produto real.
- **Nuclei sem cerca.** Descartada:
  - sem a cerca, um redirecionamento ou `Host` trocado leva o tráfego a sistemas não autorizados, e o spike mostrou que o Nuclei segue esses saltos;
  - os caminhos negados pela carta deixariam de valer;
  - a auditoria perderia a prova do que foi testado.
- **Cerca estrita igual à do ZAP.** Descartada: só 0 a 53 modelos rodariam por alvo.
- **Login pelo Replacer do ZAP.** Descartada: prende o Nuclei à janela do `scan` e à conta da operação varrida, e 77% dos alertas passivos do ZAP vieram do tráfego do Nuclei.
- **Religar as regras 40034 e 40035 do ZAP.** Descartada: 0 achados nos 4 alvos, com 53 pedidos a mais por varredura.
- **Não fazer nada.** Descartada: CVE de prateleira e exposições seguem sem cobertura.

## Consequências

- **Mais fácil:** achar CVE de produtos de prateleira, configurações erradas e exposições, com confirmação por conteúdo e custo de segundos a minutos por alvo.
- **Mais difícil:**
  - mais uma imagem para manter;
  - atualizar os modelos exige novo censo, novo manifesto e novos SHA-256;
  - a aprovação ganha mais o que explicar.
- **Risco aceito:** com caminhos amplos e escrita ligada, um modelo de CVE pode gravar dados no ambiente de teste. A cerca não impede isso, só o restringe às origens aprovadas, aos caminhos não negados e ao ritmo do perfil. Por isso a escrita depende da mesma permissão das escritas do ZAP.
- **Gravidade:** a tabela fixa marca como baixa o `/actuator/env` com valores de configuração, o que subestima o risco. O ajuste fica para decisão própria se o uso real pedir.
- **Dependência nova:** o Nuclei (MIT, mantido ativamente pela ProjectDiscovery) e o `nuclei-templates` (MIT), travados por versão e SHA-256.
- **Limites da prova:**
  - o ganho em produto real não foi medido;
  - o login por `-sf` só foi provado com marcador sintético;
  - não houve captura de pacotes;
  - a causa da partida travada não foi isolada, só contornada.

### Aceites verificáveis
1. O manifesto é reproduzível, e um teste unitário cobre cada veto, os métodos dos pedidos `raw` e a escolha por métodos permitidos.
2. Durante a etapa `nuclei`, a cerca aplica a política do Nuclei e volta à política anterior no fim e após falha forçada. O ZAP nunca roda com a política do Nuclei.
3. No laboratório:
   - o alvo Spring rende pelo menos os 13 achados do Actuator sem seleção manual;
   - os pedidos do Nuclei batem com a auditoria;
   - nenhum sai das origens aprovadas nem acerta um `deny_paths`.
4. Sem a permissão de escrita, nenhum `POST`, `PUT`, `PATCH` ou `DELETE` do Nuclei passa a cerca.
5. Com login por `-sf`, o token real não aparece em `docker inspect`, na lista de processos, nos logs, no `nuclei.json` nem no relatório, e o arquivo some no fim, inclusive após falha forçada.
6. O runner encerra o contêiner ao estourar o prazo, e um teste verifica a entrada padrão fechada.
7. Aprovações antigas continuam válidas com as chaves novas desligadas, e ligar qualquer uma delas exige nova aprovação.
