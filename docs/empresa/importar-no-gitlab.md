# Importar no GitLab

## Importe e proteja o repositório

1. Crie um projeto privado no namespace da empresa. Use o importador do GitHub, se disponível na instância, ou a importação por URL Git. Confira a chegada do histórico, das branches `main` e `develop` e das tags. [Importação do GitHub](https://docs.gitlab.com/user/project/import/github/) · [Importação por URL](https://docs.gitlab.com/user/project/import/repo_by_url/)
2. Substitua o usuário nas regras ativas do [CODEOWNERS](../../CODEOWNERS) por usuários ou grupos revisores do GitLab. Confirme que eles podem aprovar merge requests. Proteja a `main`, bloqueie push direto e exija merge request, pipeline verde e aprovação dos responsáveis pelos caminhos alterados. Aplique a revisão também na `develop` para as mudanças que entram por ela. Confira se o plano do GitLab oferece aprovação obrigatória de Code Owners. [Code Owners](https://docs.gitlab.com/user/project/codeowners/) · [Branches protegidas](https://docs.gitlab.com/user/project/repository/branches/protected/)
3. Proteja as tags `v*` e permita sua criação apenas aos responsáveis por lançamentos. Mantenha as credenciais de publicação disponíveis apenas aos jobs autorizados. [Tags protegidas](https://docs.gitlab.com/user/project/protected_tags/)

## Migre os workflows para GitLab CI

| GitHub Actions atual | Equivalente no GitLab CI |
| --- | --- |
| [`ci.yml`](../../.github/workflows/ci.yml) | Jobs em merge requests, em pushes para a `main` e sob disparo manual. Preserve análise estática, Gitleaks, auditoria do lock, testes unitários e de contrato em Linux e Windows, e os pisos de cobertura por camada e no diff. |
| [`lab.yml`](../../.github/workflows/lab.yml) | Pipeline manual por nível ou em merge request rotulado `lab`. Use runners isolados com Docker. Planeje os lotes com um pipeline filho gerado, reutilize as imagens da mesma revisão e reúna os resultados JUnit. Preserve a falha do resumo quando faltar um lote ou algum teste falhar. |
| [`images.yml`](../../.github/workflows/images.yml) | Pipeline exclusiva das tags protegidas `v*`. Publique as imagens AMD64 e ARM64 no Container Registry com atestado de procedência do build. Colete os digests, confira as versões e inclua os digests no pacote. Publique o wheel e o pacote-fonte no Package Registry PyPI. Ao final, abra um merge request que fixe a tag e o commit no marketplace. |

Publique no Container Registry do GitLab no lugar do GHCR. Garanta que o arquivo de digests do pacote aponte para as imagens do GitLab. Use o Package Registry PyPI no lugar dos anexos da release do GitHub. A TI deve configurar o acesso de leitura a ambos os registros. [Container Registry](https://docs.gitlab.com/user/packages/container_registry/) · [Registro PyPI](https://docs.gitlab.com/user/packages/pypi_repository/)

Hoje `/hdast:preparar` monta a URL do wheel no GitHub. `HDAST_RELEASE_REPOSITORY` troca apenas o dono e o repositório no GitHub. Antes de distribuir o plugin pelo GitLab, adapte essa etapa na versão corporativa ou faça a TI instalar o wheel correspondente pelo registro PyPI. Confira que a CLI instalada e o plugin tenham a mesma versão. [Instalação atual](../comecar/instalar.md#com-o-plugin)

## Aponte o marketplace para o GitLab

Na cópia da empresa, ajuste a URL interna `plugins[0].source.url` no [manifesto do marketplace](../../.claude-plugin/marketplace.json). Ela deve apontar para o repositório GitLab que contém `plugin/`. Adapte também o contrato que hoje confere a URL do GitHub. Depois de publicar a tag, revise o merge request da CI que fixa `source.ref` e `source.sha`.

Na configuração gerenciada do Claude Code, use a mesma URL GitLab para cadastrar e permitir o marketplace `hdast`. A TI deve confirmar que as estações têm acesso ao repositório privado. [Configuração gerenciada](README.md#configuração-gerenciada)

## Confira a licença do Docker Desktop

Antes da instalação, a TI deve conferir os termos do Docker Desktop. O uso profissional em organizações fora da faixa gratuita exige assinatura paga. Confirme o enquadramento da empresa antes de distribuir o aplicativo. [Licença do Docker Desktop](https://docs.docker.com/subscription/desktop-license/)
