# Instalar o Docker e preparar a pilha

O Docker é obrigatório para a pilha do harness-dast. Reserve cerca de 4 GiB de memória para o Docker Desktop. [Instale a CLI](instalar.md) antes de baixar as imagens. Se instalou pelo wheel da release, use `hdast` no lugar de `uv run hdast` nos passos de download e diagnóstico. No clone, execute esses passos na raiz do repositório.

## Windows com WSL 2

1. Confira `wsl --status` no PowerShell. Se o WSL ainda não estiver instalado, abra um PowerShell como administrador e rode `wsl --install`. Reinicie se o Windows pedir. Rode `wsl --update` e confira novamente o status. [Instalação do WSL](https://learn.microsoft.com/windows/wsl/install)
2. Instale o Docker Desktop. Nas configurações gerais, deixe **Use the WSL 2 based engine** ativado e use contêineres Linux. Abra o Desktop e espere o motor ficar pronto. [Docker Desktop para Windows](https://docs.docker.com/desktop/setup/install/windows-install/)

## macOS

Baixe o Docker Desktop para **Apple silicon** ou **Intel**, conforme o processador. Abra o `.dmg`, mova o Docker para Aplicativos e abra-o. Siga os passos do primeiro início e espere o motor ficar pronto. [Docker Desktop para Mac](https://docs.docker.com/desktop/setup/install/mac-install/)

## Linux

Instale o Docker Engine e o plugin **Docker Compose v2** pelo guia da sua distribuição. Inicie o serviço do Docker conforme o guia. O usuário que executa `hdast` precisa conseguir consultar o Docker com `docker version`. [Docker Engine no Linux](https://docs.docker.com/engine/install/)

## Baixar e conferir as imagens

> **Enquanto a primeira publicação no GHCR não acontece**, o `stack pull` ainda não encontra as imagens. Nesse período, comece pela seção [Construir a partir do código local](#construir-a-partir-do-código-local) e depois volte ao `doctor`.

```bash
docker version
docker compose version
uv run hdast stack pull
uv run hdast doctor
```

`docker version` deve mostrar as seções Client e Server. O `stack pull` baixa as imagens do ZAP, do proxy de escopo e do Nuclei (o segundo motor, [ADR 0122](../decisoes/0122-nuclei-como-segundo-motor.md)) do GHCR, sem iniciar contêineres. Com `images.lock.json` na instalação, `stack pull` e `stack up` usam os digests publicados para a versão da CLI. Um `images.lock.json` de esquema 1, publicado antes do Nuclei, baixa só as duas primeiras: o Nuclei fica indisponível e a CLI avisa ao usá-lo. O `doctor` indica se as imagens estão locais e se o proxy tem a versão da CLI. O Docker ainda pode baixar imagens auxiliares e imagens do alvo de laboratório no primeiro `stack up`.

Se os pacotes tiverem acesso restrito, autentique o Docker no GHCR com uma conta autorizada antes do download. [Autenticação no GHCR](https://docs.github.com/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-to-the-container-registry)

## Preparar as imagens da demo

A demonstração usa apenas imagens locais do Docker. Baixe as imagens próprias (ZAP, proxy de escopo e Nuclei) com `uv run hdast stack pull`, com os nomes padrão do Compose. Para preparar as imagens auxiliares e a do VAmPI, use na raiz do repositório um terminal novo conectado ao Docker local, com as variáveis de Compose nos valores padrão.

```powershell
$env:HDAST_ZAP_API_KEY = 'preparo-local'
try {
    docker compose --profile lab pull zap-gateway proxy-gateway vampi
} finally {
    Remove-Item Env:HDAST_ZAP_API_KEY
}
```

No Bash ou Zsh, use `HDAST_ZAP_API_KEY=preparo-local docker compose --profile lab pull zap-gateway proxy-gateway vampi`. O valor serve para o Compose interpretar o arquivo durante a preparação. Nenhum contêiner é iniciado.

Se as imagens próprias ainda aguardam publicação, construa as três em um clone de desenvolvimento usando os nomes padrão do Compose. No PowerShell, substitua a linha de `pull` no bloco acima por estas linhas. No Bash ou Zsh, use a mesma atribuição temporária de `HDAST_ZAP_API_KEY` antes de `docker compose build`.

```powershell
$hdastImageVersion = uv run python -c "from harness_dast import __version__; print(__version__)"
docker compose build --build-arg "HDAST_IMAGE_VERSION=$hdastImageVersion" zap scope-proxy nuclei
```

Depois, prepare também as imagens auxiliares e a do VAmPI. O diagnóstico da demo aponta imagens ausentes ou incompatíveis e conflitos nas portas 8080 e 3128. Libere as duas portas antes de continuar. [Primeiro uso](primeiro-uso.md)

## Construir a partir do código local

Use a construção local em um clone de desenvolvimento ao modificar o proxy, o ZAP, o Nuclei ou seus Dockerfiles, ou enquanto as imagens da versão ainda aguardam publicação. Fora do clone, a CLI recusa `--build` e `HDAST_STACK_BUILD=1` antes de chamar o Docker. O primeiro build pode precisar de rede para baixar bases e dependências. Rode `uv sync --locked` ao trocar de versão do repositório.

No PowerShell, substitua `vampi` pelo produto aprovado que você vai subir.

```powershell
$env:HDAST_STACK_BUILD = '1'
try {
    uv run hdast stack up vampi
} finally {
    Remove-Item Env:HDAST_STACK_BUILD
}
```

No Bash ou Zsh, o valor abaixo vale só para esse comando.

```bash
HDAST_STACK_BUILD=1 uv run hdast stack up vampi
```

A opção `--build` também habilita a construção local em uma única subida.

## Problemas comuns

| Sintoma | O que fazer |
| --- | --- |
| O Docker Desktop não abre e o erro cita um socket antigo, como `sailor-ingest.sock` | Feche completamente o Docker Desktop. Renomeie para `run.old` a pasta `run` que contém o socket indicado no erro e abra o Desktop novamente. Ele recria a pasta. |
| O WSL 2 está desligado ou desatualizado | Confira `wsl --status` e rode `wsl --update`. Se o Windows indicar que falta habilitar o WSL, siga o passo de instalação acima e reinicie. |
| As portas 8080 ou 3128 estão ocupadas | O `doctor` aponta a porta em conflito. Libere-a ou configure `HDAST_ZAP_HOST_PORT` ou `HDAST_PROXY_HOST_PORT` antes de subir. [Variáveis de ambiente](../referencia/env-vars.md) |
| O proxy corporativo bloqueia o download | Configure o proxy no Docker Desktop ou no serviço do Docker Engine conforme a orientação da empresa. Confirme o acesso a `ghcr.io`. O Docker Hub também pode ser necessário para imagens auxiliares. [Proxy do Docker Desktop](https://docs.docker.com/desktop/settings-and-maintenance/settings/#proxies) · [Proxy do Docker Engine](https://docs.docker.com/engine/daemon/proxy/) |
| A CLI diz que a imagem do Nuclei falta, ou que a instalação foi publicada sem ela | Se só falta baixar, rode `uv run hdast stack pull`. Se a mensagem citar `images.lock.json` versão 1, a instalação é anterior ao Nuclei: reinstale a CLI numa versão que o inclua ([instalar](instalar.md)) ou peça ao dono que a carta não ligue `extra_checks.nuclei`. Não edite o perfil por conta própria. |
| O Docker informa falta de espaço | Confira o uso com `docker system df`. Libere espaço no disco que armazena os dados do Docker e repita o download. |
| O proxy está sem rótulo ou tem versão diferente da CLI | Rode `uv sync --locked`, confira se `HDAST_SCOPE_PROXY_IMAGE` aponta para a versão desejada e repita `uv run hdast stack pull`. Em um checkout de desenvolvimento, faça a construção local com `HDAST_STACK_BUILD=1`. |
