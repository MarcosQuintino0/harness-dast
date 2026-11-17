# 0090. crAPI na pilha gerenciada

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** L1 da V1.12

## Contexto

O crAPI é um alvo local intencionalmente vulnerável, sem modo seguro. Seu cadastro requer contas e veículos criados pela API e um PIN recebido no MailHog. A pilha deve ser descartável e não fornecer acesso direto do ZAP ao alvo.

## Decisão

Vamos anexar `lab/crapi/compose.yaml` como projeto Compose próprio, com o mesmo sufixo restrito da pilha principal. A CLI recusa `--secure` antes de alterar a pilha e gera credenciais sintéticas no estado protegido, respeitando valores fornecidos pela pessoa. Após a subida, um adaptador cadastra as duas contas e seus veículos por portas fixas em loopback e lê o PIN no MailHog local. Erros omitem respostas e credenciais; o estado é salvo antes da subida para permitir recuperação por `stack down`. O projeto crAPI usa `down --volumes` para remover seus volumes descartáveis. O ZAP continua fora da rede do alvo.

Os caminhos usados no cadastro são extraídos do OpenAPI indicado pelo perfil, com os `operationId` `signup`, `login`, `vehicle_resend_email` e `add_vehicle`. Antes de alterar a pilha, a CLI exige operações POST explicitamente identificadas e caminhos literais locais, distintos e sem segmentos relativos. Arquivo ausente ou inválido, operação ausente ou caminho incompatível impede a subida. Isso também permite que o OpenAPI esteja em `inputs/` na cópia cega, sem incluir respostas da carta no código distribuído.

O nginx exige resolver o serviço do chatbot ao iniciar. Apontamos o upstream ao identity, já presente na mesma rede, sem baixar a imagem de chatbot de cerca de 1,5 GB. As rotas do chatbot não são implementadas por essa substituição e não fazem parte da prova L1. O overlay OAST é independente e opcional, fora desta decisão.

## Alternativas consideradas

- Manter subida e semeadura manuais: exige passos externos e deixa a pilha sem um ciclo único de recuperação.
- Manter o chatbot original: baixa uma imagem grande para um serviço fora do escopo da prova.
- Adicionar uma imagem mínima só para DNS: aumenta a quantidade de imagens e serviços sem oferecer funcionalidade necessária.

## Consequências e aceites

As portas locais 28888 e 28025 precisam estar livres; a pilha é restrita ao laboratório local. Em caso de falha do cadastro, `stack down` ainda dispõe dos projetos e credenciais necessárias. O ensaio do coordenador deve demonstrar subida e descida, remoção de volumes, login das duas contas em `preflight`, uma operação em `probe` e isolamento do ZAP e do alvo. Testes com dublês não provam o funcionamento das imagens; a prova Docker permanece pendente. A revisão do ADR e sua aceitação cabem ao dono.

`application/stack.py` já excedia 300 linhas antes desta alteração por concentrar os quatro comandos da pilha. A implementação específica de cadastro fica em adaptador separado; a extração mais ampla dos comandos existentes fica fora desta mudança.
