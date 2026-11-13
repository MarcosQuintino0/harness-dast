# Política de segurança

Esta ferramenta ataca sistemas de propósito. A segurança dela tem dois lados: o que ela pode causar no alvo e o que pode vazar ou ser explorado nela.

> **Estado atual: M1 e primeira metade do M2.** Existem como código: o `ScopeGuard` e a normalização de URL, as janelas de execução e a validade da autorização, os tetos de carga, as sobrescritas que só reduzem, o formato de `secret_ref`, os modelos do perfil e a redação de logs. Existem como configuração: o `compose.yaml` com proxy de saída e o lab, verificados em 2026-11-13. **Nenhum comando `hdast` usa esses controles ainda** (só existe `hdast version`), e a CLI não toca nenhum alvo. Não existem: resolução de segredos, auditoria, limpeza e a integração com o ZAP. As seções abaixo descrevem a política aprovada; cada controle traz o marcador do que existe e do que é planejado. Estado por item: [docs/roadmap.md](docs/roadmap.md#tabela-de-status).

## Política de uso autorizado

- Use apenas com **autorização formal por escrito**, que defina escopo, janela de execução e limites.
- Use apenas em **ambientes de teste com dados sintéticos**. Nunca em produção.
- O perfil do produto carrega a referência da autorização e sua validade. Sem isso, ou fora da janela, a CLI deve recusar. A regra existe no domínio (`ProductProfile.ensure_runnable`: autorização vencida ou janela fechada levantam `ScopeViolation`); nenhum comando a aplica ainda (M2, segunda metade).
- Contas de teste devem ser inválidas em produção.
- Limites de requisições por segundo, duração máxima e threads do ZAP são sempre fixados; os padrões do ZAP são sem limite. O modelo exige os três campos e impõe tetos absolutos (50 requisições por segundo, 480 minutos, 8 threads); a imposição durante a varredura é do M4.

O que a autorização precisa conter e como ela vira perfil: [docs/operations/authorization-and-scope.md](docs/operations/authorization-and-scope.md).

## Como o escopo é imposto (AD-11, ADR 0008)

Três camadas independentes. Cada uma cobre a falha da outra. Escopo e janela **falham fechados**: na dúvida, a execução para.

| Camada | O que faz | Status |
| --- | --- | --- |
| 1. `ScopeGuard` no domínio | Valida toda requisição e todo plano de varredura contra a lista permitida | Parcial: existe e é testado (inclui o fechamento do bypass de `deny_paths`, achado A-01); nenhum comando o chama ainda. Limitações em [docs/reference/target-yml.md](docs/reference/target-yml.md#limitações-conhecidas) |
| 2. ZAP em modo protegido | Contexto do ZAP restrito aos mesmos hosts e caminhos | Planejado (M4) |
| 3. Rede interna do Docker e proxy de saída com lista de hosts | O contêiner do ZAP só sai por um proxy que permite apenas os hosts do escopo | Parcial: `compose.yaml` e Squid existem, nega por padrão e foi verificado no lab; tráfego real de varredura pelo proxy não provado; alvo corporativo em IP privado não confirmado ([guia](docker/egress-proxy/README.md#ambiente-de-teste-corporativo-em-ip-privado)). Obrigatória antes de qualquer execução contra ambiente da empresa; opcional contra o lab |

Hoje só a camada 1 existe como código (sem comando que a use) e a camada 3 como configuração de contêiner; a camada 2 não existe. As permissões do Claude Code (negar `curl` e leitura de `.env`) reduzem acidentes, mas são uma barreira de conveniência, não isolamento: a garantia vem das três camadas.

Flags de linha de comando só podem **reduzir** escopo e limites, nunca ampliar.

## Política de segredos (AD-12, ADR 0009)

- O perfil guarda só referências (`secret_ref: env:NOME`), nunca o valor. O modelo do perfil já recusa valor literal e não o repete na mensagem de erro.
- O valor vem de variável de ambiente ou de um `.env` ignorado pelo git. **Nunca** versione `.env`.
- A CLI resolve o segredo, obtém o token e o entrega ao ZAP. O agente vê apenas apelidos de conta (`user_a`).
- As permissões do Claude Code negam a leitura de `.env` (planejado, M6).
- Um redator central de logs mascara chaves sensíveis (inclui `authorization`, `token`, `password`, `senha`), valores de segredos registrados, padrões de JWT e CPF, e o texto de exceções, objetos, conjuntos, `bytes` e pares de cabeçalho. **Implementado para logs.** A redação de evidências de achado e de respostas do alvo mostradas ao agente é planejada (M3 e M4).
- Mensagens de erro nunca incluem valor de segredo nem corpo bruto de resposta; as recusas do `ScopeGuard` também não repetem o caminho da requisição, que pode ter um token.
- Varredura de segredos (`gitleaks`) no pre-commit e no CI: **configurada**. A exigência de licença do `gitleaks-action` em repositório de organização não foi verificada (item A-16 no roadmap).
- A chave da API do ZAP no lab fica visível em `docker logs` e `docker inspect` na máquina; passe-a por outro meio antes de qualquer ambiente da empresa (item em aberto).
- O mecanismo de entrega e renovação do token no ZAP depende do spike do M0 (P-10).

## Política de limpeza (AD-13, ADR 0011)

- A limpeza é a única parte do sistema que apaga dados de propósito. Ela só roda por execução, com **confirmação humana explícita**.
- O hook de limpeza é um arquivo **SQL para Oracle escrito e revisado por uma pessoa** do time do produto. O agente nunca escreve nem altera o hook.
- O usuário de banco da limpeza deve poder apagar **somente nas tabelas de teste**.
- A CLI executa dentro de uma transação, mostra quantas linhas seriam apagadas e só confirma depois do aceite.
- Os dados criados devem ser identificáveis: o gerador marca o que cria com o identificador da execução sempre que o campo permitir (o identificador, `RunId`, já existe no domínio).
- Status: o bloco `cleanup` do perfil é validado (`requires_confirmation` só aceita `true`); a execução da limpeza é planejada (M5).

## Política de dados

- Só ambientes com **dados sintéticos**. Se um ambiente tiver dados pessoais reais, não use.
- Tudo que o agente lê vai para o provedor de IA. Por isso, nada pessoal deve chegar a ele: CPF, e-mail e tokens são redigidos antes de qualquer resposta ser mostrada ao agente ou gravada em log (logs: implementado para CPF, JWT e segredos registrados; respostas mostradas ao agente: planejado).
- O que a CLI devolve ao agente a partir do alvo é truncado, sem sequências de controle e marcado como dado (planejado). Swagger, perfil e respostas do alvo são dados não confiáveis.
- Artefatos de execução ficam em `runs/`, fora do git, com evidências redigidas e prazo de retenção (desejável na V1; prazo ainda não definido).
- O CI nunca recebe credenciais de produtos da empresa na V1; só testa contra o lab.
- A ferramenta roda em Windows; sem `PYTHONUTF8=1`, mensagens com caracteres fora do cp1252 podem falhar ao ser impressas (observado na revisão de QA, não varrido por completo).

Cenários de abuso e mitigações: [docs/operations/threat-model.md](docs/operations/threat-model.md).

## Como reportar uma vulnerabilidade no próprio harness

Reporte de forma privada ao dono do repositório pelo **GitHub Private Vulnerability Reporting** (aba *Security* do repositório, opção *Report a vulnerability*, que abre um security advisory privado). Não abra issue pública nem pull request com os detalhes.

Inclua: versão ou commit, passos para reproduzir, impacto esperado e, se souber, uma sugestão de correção. Não inclua credenciais nem dados reais de nenhum ambiente.

Para que esse canal funcione, o dono do repositório precisa habilitar o *Private vulnerability reporting* nas configurações do GitHub. **A confirmar.** Não há outro canal definido neste documento.

Vulnerabilidades em produtos testados com esta ferramenta não são objeto desta política: reporte-as ao dono do produto, conforme a autorização que cobriu o teste.
