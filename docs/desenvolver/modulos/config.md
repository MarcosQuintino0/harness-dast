# Pacote `config`

Caminho: `src/harness_dast/config/`. Referências: [../../referencia/env-vars.md](../../referencia/env-vars.md) e [../../referencia/target-yml.md](../../referencia/target-yml.md).

## Responsabilidade

Carregar e validar a configuração que vem de fora, na partida.

- **Settings da ferramenta**: variáveis `HDAST_*` lidas e validadas com pydantic-settings. Cobertas: endereço do ZAP, chave de API do ZAP, pasta de execuções, pasta de produtos e nível de log.
- **Carregador de perfil**: lê `target.yml` e os arquivos de regras, em modo seguro, e os converte em modelos de `domain`. Implementado (M2): `adapters/storage/profile_repository.py` e `adapters/storage/strict_yaml.py`.

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

Settings da ferramenta: parte da fundação do M1; o M3 acrescentou `zap_proxy_url`, `auth_proxy_url` e `zap_ca_file` (veja [../../referencia/env-vars.md](../../referencia/env-vars.md)). O carregador de perfil está em `adapters/storage` (M2); os modelos estão em `domain/` ([../../referencia/target-yml.md](../../referencia/target-yml.md)). Veja a [tabela de status](../../roadmap.md#tabela-de-status).
