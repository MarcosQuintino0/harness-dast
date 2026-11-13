# Pacote `config`

Caminho: `src/harness_dast/config/`. Referências: [reference/env-vars.md](../reference/env-vars.md) e [reference/target-yml.md](../reference/target-yml.md).

## Responsabilidade

Carregar e validar a configuração que vem de fora, na partida.

- **Settings da ferramenta**: variáveis `HDAST_*` lidas e validadas com pydantic-settings. Cobertas: endereço do ZAP, chave de API do ZAP, pasta de execuções, pasta de produtos e nível de log.
- **Carregador de perfil**: lê `target.yml` e os arquivos de regras, em modo seguro, e os converte em modelos de `domain`. **Planejado** (segunda metade do M2); não existe.

Precedência geral: flag, depois ambiente, depois perfil. Exceção deliberada: escopo e limites só podem ser reduzidos por flag, nunca ampliados.

## Pode importar

`domain`, pydantic, pydantic-settings e bibliotecas de leitura de arquivo.

## Nunca deve

- Ter regra de negócio. Validação de significado (por exemplo, o que é um escopo válido) é do `domain`.
- Guardar valor de segredo no perfil. O perfil só carrega `secret_ref`.
- Ler `.env` por conta própria além do mecanismo de settings, nem ler segredos de produtos.
- Expor settings como variável de módulo mutável. As settings são criadas na partida e passadas por parâmetro.

## Observação sobre o desenho

O contrato do import-linter em `pyproject.toml` proíbe `config` de importar `cli`, `application` e `adapters`, e proíbe `domain` e `application` de importar `config`. Em caso de divergência entre esta página e o `pyproject.toml`, vale o `pyproject.toml` e esta página deve ser corrigida.

## Status

Settings da ferramenta: parte da fundação do M1. Carregador de perfil: **não existe**, planejado para a segunda metade do M2; os modelos que ele preencherá já existem em `domain/` ([../reference/target-yml.md](../reference/target-yml.md)) e a dependência de leitura de YAML (`pyyaml`) já está declarada ([ADR 0012](../adr/0012-dependencias-tzdata-e-pyyaml.md)). Veja a [tabela de status](../roadmap.md#tabela-de-status).
