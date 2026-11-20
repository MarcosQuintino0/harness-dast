# Política de segurança

Esta ferramenta ataca sistemas de propósito. A segurança dela tem dois lados: o que ela pode causar no alvo e o que pode vazar ou ser explorado nela.

> **Estado atual: fluxo completo implementado (M1 a M5).** O `ScopeGuard` (camada 1), o proxy de escopo (camadas 2 e 3 no lab), a validade da autorização e a janela, os tetos de carga (impostos no `probe`, no `scan` e no ZAP), a resolução de segredos por referência, a trilha de auditoria, a limpeza com confirmação humana, a trava de emergência (`hdast stop`) e o encadeamento `hdast run` existem e foram verificados contra o ZAP 2.17 real e dois alvos de laboratório ([relatório](docs/arquivo/reviews/2026-11-13-e2e-lab.md)). Ainda **não** existem as skills e permissões do Claude Code (M6) e a avaliação cega (M6). A execução contra ambiente da empresa continua exigindo o M7. Estado por item: [docs/roadmap.md](docs/roadmap.md#tabela-de-status).

## Política de uso autorizado

- Use apenas com **autorização formal por escrito**, que defina escopo, janela de execução e limites.
- Use apenas em **ambientes de teste com dados sintéticos**. Nunca em produção.
- O perfil do produto carrega a referência da autorização e sua validade. Sem isso, ou fora da janela, a CLI deve recusar. A regra existe no domínio (`ProductProfile.ensure_runnable`: autorização vencida ou janela fechada levantam `ScopeViolation`) e é aplicada na partida e antes de cada requisição do `preflight`, do `probe` e do `scan` (`RunGate`).
- Contas de teste devem ser inválidas em produção.
- Limites de requisições por segundo, duração máxima e threads do ZAP são sempre fixados; os padrões do ZAP são sem limite. O modelo exige os três campos e impõe tetos absolutos (50 requisições por segundo, 480 minutos, 8 threads); o `scan` os fixa no ZAP antes da primeira varredura e o proxy de escopo impõe a taxa; o relatório mostra a taxa observada no proxy (`coverage.traffic`).

O que a autorização precisa conter e como ela vira perfil: [docs/como-funciona/operacao/authorization-and-scope.md](docs/como-funciona/operacao/authorization-and-scope.md).

## Como o escopo é imposto (AD-11, ADR 0008)

Três camadas independentes. Cada uma cobre a falha da outra. Escopo e janela **falham fechados**: na dúvida, a execução para.

| Camada | O que faz | Status |
| --- | --- | --- |
| 1. `ScopeGuard` no domínio | Valida toda requisição e todo plano de varredura contra a lista permitida | Implementado: `preflight`, `probe` e `scan` só enviam ou varrem o que o guarda aprova, sobre a URL concreta. Limitações em [docs/referencia/target-yml.md](docs/referencia/target-yml.md#limitações-conhecidas) |
| 2. ZAP em modo protegido | Contexto do ZAP restrito aos mesmos hosts e caminhos | Implementado (M4): `contextId` em toda varredura; o proxy de escopo nega o que o varredor inventa fora do escopo (centenas de pedidos por execução, contados em `scan.json`) |
| 3. Rede interna do Docker e proxy de escopo (mitmproxy com o mesmo `ScopeGuard`, [ADR 0017](docs/decisoes/0017-proxy-de-escopo-com-scopeguard.md)) | O contêiner do ZAP só sai por um proxy que decide host, caminho e método | Implementado e exercitado no lab (varredura ativa real, [relatório](docs/arquivo/reviews/2026-11-13-e2e-lab.md)); alvo corporativo em IP privado não confirmado ([guia](docker/scope-proxy/README.md#o-que-isto-não-garante-riscos-residuais)). Obrigatória antes de qualquer execução contra ambiente da empresa; opcional contra o lab |

As três camadas existem e foram exercitadas por varreduras ativas reais no lab (o proxy negou, sem derrubar a varredura, todo pedido fora de `scope.allow`). As permissões do Claude Code (negar `curl` e leitura de `.env`) reduzem acidentes, mas são uma barreira de conveniência, não isolamento: a garantia vem das três camadas.

Flags de linha de comando só podem **reduzir** escopo e limites, nunca ampliar.

## Política de segredos (AD-12, ADR 0009)

- O perfil guarda só referências (`secret_ref: env:NOME`), nunca o valor. O modelo do perfil já recusa valor literal e não o repete na mensagem de erro.
- O valor vem de variável de ambiente (`env:NOME`), de um `.env` ignorado pelo git ou do cofre de credenciais do sistema operacional (`keyring:NOME`, [ADR 0030](docs/decisoes/0030-cofre-de-credenciais-do-sistema-keyring.md)). **Nunca** versione `.env`. O cofre só é gravado por uma pessoa (`hdast secret set`, prompt oculto, só em terminal interativo; o agente não o roda) e só aceita backends do próprio sistema: nunca um arquivo em texto claro. Ele protege contra histórico de shell e arquivo esquecido, **não** contra um programa na mesma conta de usuário, que lê o cofre. Os valores do cofre entram no mesmo mascaramento dos de ambiente.
- A CLI resolve o segredo, obtém o token e o entrega ao ZAP. O agente vê apenas apelidos de conta (`user_a`).
- As permissões do Claude Code negam a leitura de `.env` (`.claude/settings.json`, M6; camada 0, de conveniência).
- Depois de uma execução completa, os testes de integração procuram as senhas, os tokens Bearer, o token XSRF e a chave do ZAP reais da execução em todos os artefatos da pasta, na auditoria do proxy, no `stdout` e no `stderr` da CLI: zero ocorrências é o critério (`tests/integration/test_lab_run.py`).
- Um redator central de logs mascara chaves sensíveis (inclui `authorization`, `token`, `password`, `senha`), valores de segredos registrados, padrões de JWT e CPF, e o texto de exceções, objetos, conjuntos, `bytes` e pares de cabeçalho. **Implementado para logs.** A redação de evidências de achado e de respostas do alvo mostradas ao agente é planejada (M3 e M4).
- Mensagens de erro nunca incluem valor de segredo nem corpo bruto de resposta; as recusas do `ScopeGuard` também não repetem o caminho da requisição, que pode ter um token.
- Varredura de segredos (`gitleaks`) no pre-commit e no CI: **configurada**. A exigência de licença do `gitleaks-action` em repositório de organização não foi verificada (item A-16 no roadmap).
- A chave da API do ZAP no lab fica visível em `docker logs` e `docker inspect` na máquina; passe-a por outro meio antes de qualquer ambiente da empresa (item em aberto).
- O token chega ao ZAP por regras do Replacer (nome `hdast-`, restritas à origem do alvo), renovadas antes de vencer e **removidas ao fim**, também depois de erro e de Ctrl+C. Um processo morto à força deixa as regras no ZAP até o próximo `scan` (que as varre na partida) ou `stack up`.

## Política de limpeza (AD-13, ADR 0011)

- A limpeza é a única parte do sistema que apaga dados de propósito. Ela só roda por execução, com **confirmação humana explícita**.
- O hook de limpeza é um arquivo **SQL para Oracle escrito e revisado por uma pessoa** do time do produto. O agente nunca escreve nem altera o hook.
- O usuário de banco da limpeza deve poder apagar **somente nas tabelas de teste**.
- A CLI executa dentro de uma transação, mostra quantas linhas seriam apagadas e só confirma depois do aceite.
- Os dados criados devem ser identificáveis: o gerador marca o que cria com o identificador da execução sempre que o campo permitir (o identificador, `RunId`, já existe no domínio).
- Status: implementado (M5). `hdast cleanup` só apaga com uma pessoa digitando o nome do produto num terminal interativo (sem flag, arquivo nem variável que confirme no lugar dela; [ADR 0025](docs/decisoes/0025-limpeza-confirmacao-so-em-terminal-e-correcoes-do-qa-m2-m5.md)), portão de SQL (a amarração exige uma coluna real), tabelas permitidas e teto de linhas definidos pela pessoa dona do produto ([guia](docs/como-funciona/operacao/cleanup.md)). O `hdast run` nunca a executa: só mostra o comando.

## Política de dados

- Só ambientes com **dados sintéticos**. Se um ambiente tiver dados pessoais reais, não use.
- Tudo que o agente lê vai para o provedor de IA. Por isso, nada pessoal deve chegar a ele: CPF, e-mail e tokens são redigidos antes de qualquer resposta ser mostrada ao agente ou gravada em log (logs: implementado para CPF, JWT e segredos registrados; respostas mostradas ao agente: planejado).
- O que a CLI devolve ao agente a partir do alvo é truncado, sem sequências de controle e marcado como dado (`strip_control` e `sanitize_excerpt`, implementados; a regra para o agente está na Parte B do `CLAUDE.md`). Swagger, perfil e respostas do alvo são dados não confiáveis.
- Artefatos de execução ficam em `runs/`, fora do git, com evidências redigidas e prazo de retenção (desejável na V1; prazo ainda não definido).
- O CI nunca recebe credenciais de produtos da empresa na V1; só testa contra o lab.
- A ferramenta roda em Windows; sem `PYTHONUTF8=1`, mensagens com caracteres fora do cp1252 podem falhar ao ser impressas (observado na revisão de QA, não varrido por completo).

Cenários de abuso e mitigações: [docs/como-funciona/operacao/threat-model.md](docs/como-funciona/operacao/threat-model.md).

## Como reportar uma vulnerabilidade no próprio harness

Reporte de forma privada ao dono do repositório pelo **GitHub Private Vulnerability Reporting** (aba *Security* do repositório, opção *Report a vulnerability*, que abre um security advisory privado). Não abra issue pública nem pull request com os detalhes.

Inclua: versão ou commit, passos para reproduzir, impacto esperado e, se souber, uma sugestão de correção. Não inclua credenciais nem dados reais de nenhum ambiente.

Para que esse canal funcione, o dono do repositório precisa habilitar o *Private vulnerability reporting* nas configurações do GitHub. **A confirmar.** Não há outro canal definido neste documento.

Vulnerabilidades em produtos testados com esta ferramenta não são objeto desta política: reporte-as ao dono do produto, conforme a autorização que cobriu o teste.
