# QA que melhora

## Trabalhe no clone

Clone o repositório da empresa com Git. Na raiz do clone, rode `uv sync --locked` e abra o Claude Code com `claude --plugin-dir plugin/`. O comando carrega o plugin local para desenvolvimento. [Regras do projeto](../../AGENTS.md)

Use apenas a Clínica Piloto, o VAmPI e o crAPI em contêineres com dados sintéticos para provas do laboratório. Consulte a escada de testes para escolher a menor prova que cobre a mudança. [Laboratório](../../lab/README.md) · [Escada de testes](../desenvolver/escada-de-testes.md)

Abra um merge request para `develop`. Mudanças nos caminhos protegidos passam pela revisão do responsável indicado no [CODEOWNERS](../../CODEOWNERS). Exija CI verde antes de integrar. A promoção de `develop` para `main` precisa do aval do dono.

## Lance pela tag

Alinhe as versões do pacote, do lock, do manifesto do plugin e da referência do marketplace. Depois que a versão revisada chegar à `main`, o responsável pelo lançamento cria e envia a tag protegida `v<versão>`. [Passos do lançamento](../desenvolver/lancar-versao.md)

Hoje a CI do GitHub publica as imagens do ZAP e do proxy de escopo para Linux AMD64 e ARM64, coleta seus digests e os inclui no pacote da CLI. A release recebe o wheel e o pacote-fonte. A CI abre um pull request para fixar a tag e o commit do plugin no marketplace. A atualização passa por revisão antes de chegar à `main`. Para o GitLab, siga o plano de migração. [Importar no GitLab](importar-no-gitlab.md)
