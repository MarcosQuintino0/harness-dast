# Usar o hdast na empresa

- [QA que testa](qa-que-testa.md) prepara a máquina e testa a partir de uma pasta de produtos.
- [QA que melhora](qa-que-melhora.md) trabalha no clone da ferramenta e revisa mudanças.
- [Importar no GitLab](importar-no-gitlab.md) orienta a migração e a publicação pela TI.

## Configuração gerenciada

O [JSON de exemplo](configuracao-gerenciada.json) é ilustrativo. Troque a URL de exemplo pela URL Git da empresa nos dois pontos. `extraKnownMarketplaces` cadastra o marketplace `hdast`. `enabledPlugins` habilita `hdast@hdast`. `strictKnownMarketplaces` permite somente esse marketplace.

A TI deve consultar a documentação oficial do Claude Code para escolher o formato e o mecanismo de distribuição adequados à organização. Confira também o acesso ao repositório privado e o efeito da lista restrita sobre os outros marketplaces da empresa. [Configuração do Claude Code](https://code.claude.com/docs/en/settings) · [Marketplaces de plugins](https://code.claude.com/docs/en/plugin-marketplaces)
