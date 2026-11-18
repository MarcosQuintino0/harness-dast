# 0115. Demonstração local com `hdast demo`

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** Pacote 2.2 da fase de simplificação do uso

## Contexto

O primeiro contato com o harness exige preparar um perfil, configurar as contas do laboratório, aprovar o escopo e subir a pilha. O VAmPI já tem perfil e OpenAPI versionados. A aprovação humana continua obrigatória para qualquer execução da demonstração.

## Decisão

Vamos oferecer `hdast demo [--keep]` em **Comece por aqui**. O comando exige TTY na entrada e no stderr e recusa `--json`. O diagnóstico de Docker, imagens e portas usa as mesmas conferências do `doctor`. Todas as imagens precisam estar disponíveis localmente e o Compose roda sem downloads. A pilha usa o socket local do Docker e portas de loopback.

A CLI copia o perfil embutido para uma sessão temporária com pastas próprias de produtos, estado e execuções. A sessão usa um projeto Compose exclusivo. A pessoa vê o resumo fixo e digita `demo` pelo mesmo prompt de `profile approve`. A confirmação gera a aprovação normal dos blocos de proteção do perfil, vinculada ao estado da sessão. O hook e as permissões do Claude Code barram a execução por agentes. [ADR 0037](0037-aprovacao-humana-do-escopo.md)

A CLI reutiliza `stack up`, `run` e `stack down` em subprocessos com ambiente isolado. O `run` recebe um prazo reduzido de cinco minutos para a varredura. O encerramento tenta desmontar a pilha mesmo após falha ou interrupção. `--keep` mantém uma pilha iniciada com sucesso. O relatório e os arquivos da sessão permanecem na pasta temporária após a execução. Quando o relatório existe, a pessoa pode abri-lo no navegador.

## Alternativas consideradas

- Pedir que a pessoa faça todos os passos do laboratório. Preserva a aprovação, mas repete o cadastro já distribuído para um alvo fixo.
- Distribuir uma aprovação pronta. O registro deixaria de demonstrar a confirmação da pessoa que está executando.
- Usar a pilha e o diretório de produtos da instalação. Uma demonstração poderia substituir a pilha gerenciada de outro produto.

## Consequências

A preparação das imagens é uma etapa anterior ao primeiro uso. A demo requer as portas 8080 e 3128 livres. Se `--keep` for usado ou a desmontagem falhar, a localização do estado permite encerrar a pilha depois. O resultado do `run` segue o contrato existente. O cancelamento por texto diferente retorna 0, sem aprovação, como em `profile approve`. O código da desmontagem sinaliza falha quando a execução chegou a um resultado bem-sucedido.

## Aceites verificáveis

- Em TTY, digitar outro texto cancela antes de subir a pilha. Sem TTY ou com `--json`, o comando retorna 2. Docker ausente, imagens ausentes ou porta ocupada impedem a aprovação.
- A aprovação e as execuções ficam na sessão temporária. O perfil só autoriza o VAmPI local e os subprocessos usam os controles existentes.
- A pilha cai após a execução e em caso de falha, salvo quando `--keep` mantém uma pilha iniciada com sucesso. O relatório local, quando gravado, permanece disponível.
- O hook e as oito negações de shell cobrem Bash e PowerShell, chamada direta e via `uv run`, com e sem `--json`.
