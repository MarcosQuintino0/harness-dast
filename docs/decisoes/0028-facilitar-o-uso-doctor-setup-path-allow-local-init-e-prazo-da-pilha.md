# 0028. Facilitar o uso: `hdast doctor`, `probe.setup_path`, mensagem do `allow_local`, `init` sem `cleanup/` e prazo da pilha separado do da execução

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** [rodadas cegas de 2026-11-13](../arquivo/reviews/2026-11-13-rodadas-cegas.md) (atritos da rodada 3, de todas as rodadas com `allow_local`, das três com a pasta `cleanup/` e da rodada 1 com o prazo); altera o contrato de [ADR 0013](0013-schema-v1-do-perfil-de-produto.md) (campo novo do perfil), [ADR 0010](0010-contrato-json-da-cli-e-codigos-de-saida.md) (comando novo), [ADR 0017](0017-proxy-de-escopo-com-scopeguard.md) e [ADR 0019](0019-pilha-gerenciada-politica-por-execucao-e-login-pelo-proxy.md) (prazo da política do proxy). Sem dependência nova.

## Contexto

Quem usa a ferramenta é uma pessoa de QA que não é especialista em rede. As cinco rodadas cegas mostraram cinco atritos que não são falha de segurança, mas custam tempo ou travam:

1. Não há como saber, antes de começar, se a máquina está pronta (Docker parado, porta ocupada, variável de segredo esquecida). O erro aparece no meio do `stack up` ou do `preflight`.
2. A única maneira de preparar os dados do alvo antes dos logins era apontar `probe.health_path` para um GET que recria os dados. Truque não óbvio; uma rodada parou nele.
3. Todo agente só descobriu pelo erro que host de rótulo único (`clinica-piloto`, `vampi`) exige `allow_local: true`, e a mensagem não dizia o que fazer.
4. `hdast init` copiava `products/_template/cleanup/` para todo produto; três agentes tentaram apagá-la e a permissão barrou.
5. Os 30 minutos de `limits.max_duration_minutes` contavam desde o `stack up`: o tempo gasto ajustando o `probe` consumia o da varredura (um agente teve de usar `--max-minutes 23`).

A causa do item 5 está no proxy de escopo, não na CLI. A CLI já conta o prazo de cada `run`, `probe` e `scan` do início DELE (`run_support.RunGate`, `scan`, `RunPipeline._deadline`). Mas o proxy recebe um `not_after` calculado no `stack up` como `agora + max_duration_minutes` (limitado pela autorização e pela janela) e, além disso, calcula na partida `início do proxy + max_duration_minutes` (`policy.deadline_of`). Passado esse instante o proxy nega tudo, mesmo que a execução em curso tenha começado há pouco.

## Decisão

Vamos fazer cinco mudanças, uma por atrito.

### 1. Comando `hdast doctor [produto]`

Um comando novo que responde "está tudo pronto para começar?" sem tocar o alvo, sem subir contêiner e sem mostrar valor de segredo. O nome segue o costume de outras ferramentas de linha de comando (`brew doctor`, `flutter doctor`) e diz o que a pessoa quer: um diagnóstico com receita. Outros nomes (`check`, `ready`, `env`) foram descartados por ficarem vagos ou colidirem com `preflight` e `profile validate`.

- **Conferências:** `python` (3.12 ou mais novo), `uv` (no PATH, só aviso), `products_dir`, `docker` (responde), `images` (as do `compose.yaml` presentes; ausência é só aviso, porque o `stack up` baixa e constrói), `port:<n>` (8080 e 3128, ou as de `HDAST_ZAP_HOST_PORT` e `HDAST_PROXY_HOST_PORT`; para a Clínica Piloto, também 28080 e 29091; com pilha gerenciada no ar, porta em uso é esperada), `stack` (só avisa se a pilha atual venceu) e, com produto, `profile` (estrutura e pendências do modelo, via o mesmo caso de uso do `profile validate`), `authorization`, `window` e `secrets:<apelido>`.
- **Regra compartilhada com o `preflight`:** autorização, janela e presença de segredos vivem em `application/preflight_checks.py` e os dois comandos usam o mesmo código e os mesmos textos. O `doctor` não duplica regra; o `preflight` continua sendo a conferência COM rede (ZAP, saúde do alvo, logins).
- **Porta nova** `HostInspector` (`application/ports.py`): só leitura da máquina (versão do Docker, imagem presente, imagens do `compose.yaml`, porta livre, versão do `uv`, pasta existe). Há fronteira com sistema externo e dublê de teste (`tests/fakes/host.py`), o que justifica a porta. Adaptador: `adapters/docker/host.py`.
- **Envelope e saída:** `data` = `{product, ready, checks: [{id, status, detail, kind}], summary: {ok, warn, fail}}`. Sucesso sai `0` (avisos não reprovam). Se algo reprova, o envelope de falha traz `error` e `data` juntos (como no `preflight`) e o código vem da primeira reprovação na ordem `scope` = `3` (`SCOPE_VIOLATION`), `config` = `2` (`CONFIG_ERROR`), demais = `4` (`PREFLIGHT_FAILED`). Nenhum código nem `error.code` novo.
- **Segredos:** o JSON diz o apelido e o campo (`user_a.password`), nunca o valor nem o nome da variável; o nome da variável só aparece no texto para a pessoa (`operator_detail`), como no `preflight`.

### 2. `probe.setup_path`: preparar os dados antes do login

Campo novo e opcional do bloco `probe` (aditivo no schema v1, como o ADR 0021): caminho literal de um GET **idempotente** que prepara os dados do alvo. O `preflight` o chama uma vez, depois de `target_health` e antes dos logins, como verificação `target_setup`; o `run` herda porque começa pelo `preflight`. Passa pelo mesmo `ScopeGuard`, limitador de taxa, trilha de auditoria e proxy que os outros envios, e o perfil só é válido se o GET estiver em `scope.allow` (e fora de `deny_paths`). Ausente, nada é chamado. Resposta 4xx ou 5xx reprova a verificação. O `probe` avulso não o chama: o caminho de uso é `preflight` antes do `probe`, como já era. `health_path` continua funcionando como hoje (inclusive como truque de semeadura). A dica do erro de login e a documentação passam a apontar para `setup_path`.

### 3. `allow_local`: só mensagem e dica

A regra não muda. A mensagem do perfil passa a dizer que o host "conta como local", lista o que conta (IP literal, `localhost`, nome sem ponto como `vampi` ou `clinica-piloto`, `.local`, `.internal`) e a correção; a dica do erro traz a receita do laboratório (`allow_local: true`, `scheme: http`) e a do ambiente real (nome DNS completo, com ponto). O modelo `products/_template/target.yml` e `docs/reference/target-yml.md` ganham o exemplo.

### 4. `hdast init` não cria `cleanup/` por padrão

A porta `ProductScaffolder.scaffold` ganha o parâmetro `with_cleanup` (padrão `False`). `hdast init <produto>` não copia `products/_template/cleanup/`; `hdast init <produto> --with-cleanup` copia (README e exemplo do script). O envelope não muda (`files` simplesmente não lista `cleanup/...` por padrão). Ninguém precisa apagar uma pasta que não usa, e quem tem limpeza pede a pasta de forma explícita. O bloco `cleanup` do `target.yml` do modelo continua lá, com o comentário dizendo para removê-lo se não houver limpeza. `docs/guides/limpeza-de-dados.md` e a skill `onboard-product` foram atualizados.

### 5. Prazo da pilha separado do prazo da execução

- **Prazo da execução (`run`, `probe`, `scan`):** continua na CLI, conta do início da execução e nunca passa de `limits.max_duration_minutes` (o `--max-minutes` só reduz). Já era assim; um teste novo fixa que o `run` conta do início dele, não de quando a pilha subiu.
- **Validade da pilha:** o `not_after` da política do proxy passa a ser a validade da pilha: `min(subida + max_duration_minutes + 60 minutos de folga, fim do último dia da autorização, primeiro minuto sem janela aberta)`. A folga de 60 minutos (`STACK_MARGIN_MINUTES`) é para o ajuste do `probe` antes do `run`. Nenhuma execução passa do limite da carta (a CLI a corta em `max_duration_minutes`) e nenhuma pilha envia fora da janela ou depois da autorização (o proxy nega a partir do `not_after`).
- **Política do proxy:** campo novo, opcional, `stack_minutes` (1 a 540). O proxy usa `min(not_after, início do proxy + (stack_minutes ou max_duration_minutes))`. Sem o campo, vale o comportamento antigo (cerca de `max_duration_minutes` desde a partida), o que protege política escrita à mão. `limits` continua igual ao do perfil, nunca mais largo. O schema da política segue na versão 1 porque o campo é aditivo.
- **O KILL (`hdast stop`) não muda.** A trava continua independente do ZAP e do prazo.

## Alternativas consideradas

- **`doctor` como flag do `preflight`.** O `preflight` exige o ZAP no ar e toca o alvo; o `doctor` existe justamente para antes disso. Descartada.
- **`doctor` reprovar quando falta imagem.** O `stack up` baixa e constrói sozinho; reprovar faria o comando acusar o que o fluxo normal resolve. Fica como aviso.
- **`setup_path` em POST ou com corpo.** Mudar dados do alvo por escrita pede decisão humana e entra no escopo de escrita da carta; o GET idempotente cobre o caso observado. Descartada.
- **`setup_path` chamado também pelo `probe` avulso.** Cada `probe` repetiria a semeadura (e o `probe` já apaga e troca dados); o contrato "o `preflight` prepara, o `probe` usa" é mais previsível. Descartada.
- **Mudar a regra do `allow_local` (por exemplo, aceitar nome de contêiner sem a marca).** É a defesa contra SSRF; o problema era só a mensagem. Descartada.
- **`init` perguntar se quer `cleanup/`.** Pergunta interativa quebra o uso por agente e por script. Uma flag explícita é igual para os dois.
- **Tirar o prazo do proxy e deixar só a CLI.** Perderia a cerca de segurança que independe do processo da CLI (um ZAP largado varrendo depois de a CLI morrer). Fica com validade própria, limitada.
- **Pilha sem folga fixa, com validade igual a `max_duration_minutes` mais o tempo gasto.** Exigiria a CLI renovar a política em execução; o proxy só lê a política na partida (ADR 0017). Descartada por complexidade e por abrir um caminho de alargar prazo em voo.
- **Folga configurável no perfil.** Campo novo que alarga limite de segurança por escolha de quem edita o perfil; os limites vêm da carta. Descartada: a folga é constante do código, com ADR.

## Consequências

- Quem começa tem um comando para rodar antes de tudo, e cada reprovação diz o que fazer.
- A pilha agora vale mais tempo que uma execução (até 60 minutos a mais), sempre limitada por autorização e janela. Pilha esquecida no ar envia por até `max_duration_minutes + 60` minutos em vez de `max_duration_minutes`; o `hdast stop` e o `stack down` seguem iguais.
- Se uma execução começa perto do fim da validade da pilha, o proxy pode cortá-la antes dos `max_duration_minutes` da execução. O `doctor` avisa quando a pilha venceu e o `stack status` mostra `not_after`; a recomendação é refazer o `stack up` antes de um `run` longo. A CLI não lê o estado da pilha para encurtar o prazo da execução (ficou de fora de propósito).
- O perfil do laboratório VAmPI (`lab/vampi/product-profile/target.yml`) ainda usa `health_path: /createdb`; migrar para `setup_path` ficou para a prova em laboratório, que exige Docker.
- O `HostInspector` é a primeira porta que olha a máquina em vez do alvo; qualquer conferência nova do `doctor` passa por ela.
- A pasta `cleanup/` deixa de existir em produto novo; quem já tem produto criado não é afetado.
