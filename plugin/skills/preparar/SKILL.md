---
name: preparar
description: "Use quando a máquina não tem o que o hdast precisa ou quando o hook de início do plugin avisar sobre uma pendência. Só diagnostica e instala o necessário, com permissão da pessoa; não cadastra nem testa produto."
---

# Preparar a máquina para o hdast

Restrinja o trabalho à instalação e ao diagnóstico local, usando só as fontes da tabela do passo 2. Esta skill não cadastra nem testa produto, então não há diário de decisões (`decision-log.md`) a manter.

## Passos

1. **Diagnosticar sem instalar.**
   - Identifique o sistema operacional.
   - Confira `uv` e `hdast` no PATH e consulte `uv --version` e `hdast --version` quando existirem.
   - Compare a versão da CLI com a do manifesto `.claude-plugin/plugin.json` do plugin ativo, informada pelo `SessionStart`. Se o hook não mostrar a versão, peça à pessoa que confira o campo `version` do manifesto no terminal dela.
   - Confira o Docker com `docker --version` e teste o motor com `docker info`, com prazo curto. No Windows, confira o WSL 2 com `wsl --status` e `wsl --list --verbose`.
   - Consulte o espaço livre na unidade dos dados do Docker: `Get-PSDrive -PSProvider FileSystem` no Windows, `df -h` no Linux e no macOS.
   - Se a CLI existir, rode `hdast doctor` sem produto e use o resultado para listar as pendências. A verificação das imagens conta a do Nuclei (o segundo motor, [ADR 0122](../../../docs/decisoes/0122-nuclei-como-segundo-motor.md)), que ocupa mais espaço em disco: o `hdast stack pull` baixa as três. Se o aviso disser que a instalação não traz o Nuclei (`images.lock.json` versão 1), a solução é reinstalar a CLI numa versão que o inclua, pelo passo 3, e não há imagem a baixar. Você não liga nem desliga o Nuclei no perfil: isso é da carta.
2. **Corrigir uma pendência por vez.** Para **cada instalação**:
   1. mostre o comando exato e a fonte;
   2. faça uma pergunta separada e aguarde o **sim explícito** da pessoa;
   3. só então peça a permissão do Claude Code para executar aquele comando;
   4. confira o resultado antes de propor a próxima instalação.

   Nunca encadeie instalações.

   | Pendência | Comando ou ação e fonte fixa |
   | --- | --- |
   | `uv` no Windows | `winget install --id astral-sh.uv -e` |
   | `uv` no Linux ou macOS | O instalador do [guia oficial do uv](https://docs.astral.sh/uv/getting-started/installation/), rodado pela pessoa no terminal dela |
   | Docker no Windows | `winget install --id Docker.DockerDesktop -e` |
   | Docker no Linux ou macOS | No Linux, o [guia oficial do Docker Engine](https://docs.docker.com/engine/install/), com o Engine e o Compose v2 da distribuição identificada. No macOS, o instalador da arquitetura certa no [guia do Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/), aberto pela pessoa. |
   | CLI ausente ou de outra versão | `uv tool install --python 3.12 <URL do wheel>`, com a URL do passo 3 |
   | Imagens ausentes (ZAP, proxy de escopo e Nuclei), com a CLI certa e o motor aberto | `hdast stack pull` |
3. **Montar a URL do wheel.**
   - O repositório vem de `HDAST_RELEASE_REPOSITORY` (`dono/repositório` no GitHub), com `MarcosQuintino0/harness-dast` como padrão. Se não puder consultar a variável, peça à pessoa só o valor dela ou a confirmação do padrão.
   - Molde: `https://github.com/<dono/repositório>/releases/download/v<versão>/harness_dast-<versão>-py3-none-any.whl`, com a versão do manifesto do plugin ativo.
   - Aceite só uma versão numérica com pontos e um identificador com um único `/` e componentes ASCII alfanuméricos, `.`, `-` ou `_`. Rejeite componentes vazios, `.` e `..`.
   - Mostre a URL já preenchida quando pedir o sim. Se o `uv` pedir para substituir a CLI existente, mostre o mesmo comando com `--force` e peça um novo sim.
4. **Avisar antes das instalações pesadas.**
   - No Windows, o Docker Desktop e o WSL 2 pedem administrador, e a janela de elevação é da pessoa.
   - Pode ser preciso reiniciar. Retome as verificações depois do reinício.
   - O Docker Desktop tem licença paga em empresa grande, e a TI precisa confirmar os termos antes da instalação.
   - Em máquina sem `winget`, com instalação bloqueada ou que precisa do WSL 2, entregue a lista para a TI (sistema, o que falta e os comandos ou guias da tabela). Não tente contornar o bloqueio.
5. **Abrir o Docker e conferir.**
   - Se o Docker estiver instalado e fechado, ofereça abrir o Docker Desktop, ou iniciar o serviço da distribuição, e aguarde o sim.
   - Se a abertura depender da interface do sistema ou de elevação, peça que a pessoa a faça.
   - Consulte `docker info` a cada alguns segundos, por no máximo dois minutos.
   - No fim, rode `hdast doctor` sem produto e informe se ficou verde ou o que ainda falta, com a ação da pessoa ou da TI.

## Se der X, faça Y

| Situação | Ação |
| --- | --- |
| O guard bloqueia tudo porque falta o `uv` | Mostre o comando de instalação do `uv` para o sistema e peça que a pessoa o rode no terminal dela; retome depois de reabrir o Claude Code |
| O guard barra uma consulta ou instalação | Mantenha o bloqueio e entregue o comando para a pessoa rodar no terminal dela |
| A versão do `hdast` difere da do plugin | Reinstale pela URL do wheel da versão do plugin, com `--force` e um novo sim |
| O `docker info` não responde em dois minutos | Registre a pendência e encerre as etapas que dependem do motor |
| A URL do wheel não existe ou a fonte não foi confirmada | Registre a pendência para a pessoa; não procure outra fonte |

## Nunca

- Ler arquivos de variáveis de ambiente, o cofre ou qualquer segredo.
- Rodar os comandos reservados à pessoa: aprovação do escopo, gravação ou remoção de segredo, liberação de mutação e confirmação de achado.
- Tocar em alvo: nenhum comando que envie tráfego ao produto, nem `curl`, `wget` ou script contra produto. Também não rode `cleanup` nem qualquer limpeza.
- Desligar antivírus ou firewall, ou mudar a configuração de segurança da máquina.
- Baixar ou instalar de fonte fora da tabela, ou instalar sem o sim da pessoa.
