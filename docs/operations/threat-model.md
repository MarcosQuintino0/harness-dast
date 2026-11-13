# Modelagem de ameaças

A ferramenta ataca sistemas de propósito. A segurança dela tem dois lados: o que ela pode causar no alvo e o que pode vazar ou ser explorado nela. Este documento lista os cenários de abuso e a mitigação aprovada para cada um. Deve ser revisado a cada versão.

> **Status geral:** as mitigações são parte código de domínio já existente, parte configuração de contêiner verificada no lab, e o restante planejado. Existem: hierarquia de erros, envelope JSON, configuração, logs com redação, `ScopeGuard` e modelos do perfil (sem comando que os use), `compose.yaml` com proxy de saída. A coluna "Status" diz o que vale para cada linha. Estado dos componentes: [../roadmap.md](../roadmap.md#tabela-de-status).

## Fronteira de confiança

O agente é tratado como **não confiável por construção**: pode errar ou ser enganado por texto vindo do alvo. Swagger, perfil e respostas do alvo são **dados**, nunca instruções. A garantia vem de código determinístico na CLI e da rede, não de prompt. Veja [ADR 0001](../adr/0001-dois-planos-agente-propoe-cli-executa.md).

## Cenários de abuso

| # | Cenário | Mitigação | Status |
| --- | --- | --- | --- |
| 1 | O agente ou a varredura envia requisição fora do escopo (host, caminho ou método não autorizados), por erro ou por redirecionamento | Escopo em três camadas: `ScopeGuard`, ZAP em modo protegido e proxy de saída com lista de hosts. Falha fechada. Flags só reduzem escopo | Camada 1: existe no domínio, sem comando que a chame. Camada 2: planejada (M4). Camada 3: existe como configuração e foi verificada no lab; falta provar tráfego real de varredura e o caminho para IP privado de empresa (M7) ([ADR 0008](../adr/0008-escopo-em-tres-camadas.md)) |
| 2 | Texto plantado na resposta da API, no Swagger ou em mensagem de erro tenta instruir o agente (injeção de instruções) | O que a CLI devolve ao agente a partir do alvo é truncado, sem sequências de controle e marcado como dado. O agente não tem ferramenta que amplie escopo | Planejado (M3). Regra já vale em [CLAUDE.md](../../CLAUDE.md) |
| 3 | Segredo ou token vaza para o provedor de IA, para log ou para o repositório | Segredos só por referência; o agente vê apelidos; redator central de logs; permissão que nega leitura de `.env`; varredura de segredos (`gitleaks`) no commit e no CI | Redação de logs e formato de `secret_ref` implementados; `gitleaks` no pre-commit e no CI; demais planejados ([ADR 0009](../adr/0009-segredos-por-referencia.md)) |
| 4 | Dado pessoal real chega ao modelo ou a um relatório | Só ambientes com dados sintéticos; redação de CPF, e-mail e tokens antes de mostrar resposta ao agente ou gravar em log | Planejado (M3). A restrição de ambiente é regra de uso, desde já |
| 5 | A varredura sobrecarrega o ambiente compartilhado | Limites sempre fixados (requisições por segundo, duração máxima, threads do ZAP); janela de execução conferida a cada lote; parada de emergência | Tetos absolutos e janela existem no domínio; a imposição durante a varredura é do M4, a parada de emergência do M5 |
| 6 | A limpeza apaga dados que não eram da execução ou de outros times | Hook de limpeza escrito e revisado por pessoa, só SQL em tabelas de teste, transação com contagem de linhas e confirmação humana; o agente nunca escreve nem altera o hook; dados marcados com o identificador da execução | Planejado (M5) ([ADR 0011](../adr/0011-limpeza-por-sql-oracle-com-python-oracledb.md)) |
| 7 | Uso sem autorização, ou com autorização vencida ou fora da janela | O perfil carrega a referência e a validade da autorização; sem isso, ou fora da janela, a CLI recusa | Validade e janela existem no domínio (`ensure_runnable`); nenhum comando as aplica ainda (M2, segunda metade) |
| 8 | Código gerado por IA e executado na máquina do QA (scripts de dados) | Regras declarativas validadas por schema; script só como exceção, com revisão humana obrigatória | Planejado (M3) ([ADR 0006](../adr/0006-regras-de-dados-declarativas.md)) |
| 9 | O agente amplia escopo ou limites, altera severidade de achado ou apaga achado | O agente não tem comando que faça isso; flags só reduzem; skill de triagem só anota. Mudança em escopo, segredos, limpeza e permissões exige segundo revisor humano | Regras escritas em [CLAUDE.md](../../CLAUDE.md). Em código: sobrescritas que só estreitam (`overrides.py`), sem comando ainda; o restante a partir do M4 |
| 10 | Entrada maliciosa ou malformada (Swagger, YAML, resposta do ZAP) explora o parser | Validação por schema na fronteira, YAML em modo seguro, limites de tamanho e de profundidade | Validação por pydantic desde a fundação e modelo do perfil completo; carregadores de YAML e OpenAPI planejados (M2, M3) |
| 11 | Vulnerabilidade ou adulteração na cadeia de dependências ou na imagem do ZAP | Versões travadas em `uv.lock`, `pip-audit`, imagem do ZAP fixada por digest, atualização por pull request, ADR para dependência nova | `uv.lock`, dependência nova com ADR, `pip-audit` no CI e imagens fixadas por digest no `compose.yaml`: vigentes. Ações do GitHub fixadas por tag, não por SHA: item em aberto (A-16) |
| 12 | Mensagem de erro ou artefato expõe segredo ou corpo bruto de resposta | Mensagens nunca incluem valor de segredo nem corpo bruto; `runs/` fora do git, com evidências redigidas e prazo de retenção | Regra de erro vigente; retenção ainda sem prazo definido |
| 13 | ZAP exposto na máquina ou na rede | ZAP sem portas expostas fora da máquina e com chave de API | Parcial: a porta do ZAP escuta só em `127.0.0.1` e exige chave (verificado no lab). A chave fica visível em `docker logs` e `docker inspect`: item em aberto |
| 14 | Bloqueio pelos classificadores de segurança do provedor interrompe o fluxo | O agente fica na configuração; quem ataca é o ZAP. Medir a taxa de bloqueio no spike do M0 (P-08) | Em aberto (M0) |

## Limite do que as permissões do agente garantem

Negar `curl` e a leitura de `.env` nas permissões do Claude Code reduz acidentes, mas é barreira de conveniência, não isolamento. A garantia de escopo vem das três camadas do [ADR 0008](../adr/0008-escopo-em-tres-camadas.md). O formato exato das regras de permissão precisa ser conferido na documentação do Claude Code ao escrever o arquivo (M6).

## Riscos residuais conhecidos

- A forma de entregar o token ao ZAP e de renová-lo em varreduras longas depende do spike do M0 (P-10).
- O proxy de saída existe no `compose.yaml`, mas só foi provado com uma chamada `accessUrl` do ZAP; a varredura real pelo proxy não foi exercitada. Ele é condição para qualquer execução contra ambiente da empresa, e um alvo corporativo em IP privado provavelmente não passa pela regra atual (A-08, [docker/egress-proxy/README.md](../../docker/egress-proxy/README.md#ambiente-de-teste-corporativo-em-ip-privado)).
- O `ScopeGuard` não resolve DNS, não confere cabeçalhos nem corpo e recusa a mais em alguns casos ([../reference/target-yml.md](../reference/target-yml.md#limitações-conhecidas)).
- O fluxo de uma execução depende do mecanismo de `probe`, ainda a confirmar no spike ([ADR 0007](../adr/0007-zap-alimentado-por-requisicoes-validas.md)).

Para reportar uma falha do próprio harness, veja [../../SECURITY.md](../../SECURITY.md).
