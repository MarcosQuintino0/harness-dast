# Estratégia e prévia local

**Status:** comandos implementados na V1.8. A prévia descreve trabalho previsto e não prova cobertura executada ou detecção. Contexto e passos de cadastro: [guia de personalização](../guides/personalizacao.md). Contratos: [ADR 0071](../adr/0071-estrategia-versionada.md), [ADR 0072](../adr/0072-compilacao-sem-trafego.md) e [ADR 0074](../adr/0074-migracao-estrategia.md).

## Comandos e opções

```text
hdast [--json] strategy validate <produto> [--products-dir <pasta>]
hdast [--json] strategy diff <produto> [--products-dir <pasta>]
hdast [--json] strategy migrate <produto> [--output <nome>] [--products-dir <pasta>]
hdast [--json] plan <produto> --dry-run [--products-dir <pasta>]
```

- `--json` é opção global, antes do comando; seleciona o envelope JSON versionado da CLI.
- `--products-dir <pasta>` escolhe a pasta de produtos para o comando; pode ser omitida quando configurada no ambiente.
- `--output <nome>` escolhe o nome da cópia de migração; o padrão é `strategy.migrated.yml`. O nome segue `strategy.<nome>.yml`, com minúsculas, dígitos e hífen no trecho intermediário. Arquivo existente não é sobrescrito.
- `--dry-run` é obrigatório no comando `plan`; sem ele, a CLI retorna erro de configuração.
- `--help` mostra a ajuda da CLI ou do comando indicado.

`strategy validate` retorna presença e estado da estratégia, estado da aprovação e resumo do envelope derivado do perfil. `strategy diff` acrescenta alterações estruturais em relação ao perfil legado e a classificação `automatic` ou `pending`; não compara a cobertura item por item. Ambos são consultas locais, sem tráfego e sem exigir aprovação. O estado da estratégia não é aprovação do perfil.

`plan --dry-run` produz prévia local sem tráfego. A resposta inclui `executed: false` e `preview`, com operações, contas, dependências, entradas declaradas e política. `body_entries_complete: false` indica que as entradas do corpo são incompletas; `scope_check: template_only` limita a conferência ao modelo do caminho. O catálogo de regras do ZAP, a cobertura e o resultado efetivo do scan permanecem pendentes. Qualquer escolha preenchida impede a compilação e a execução enquanto a versão efetiva do motor estiver indisponível nesse caminho. `choices: []` continua operacional.

`strategy migrate` cria a cópia neutra sem alterar o perfil ou a aprovação e sem ativar a estratégia. Uma estratégia já existente impede a migração. Revise a cópia antes de ativá-la explicitamente como `strategy.yml`. O comando devolve `copy`, `changes`, `classification` e `approval_changed` no resultado.

Uma estratégia mínima usa `schema_version: 1`, referências a `target.yml`, `data-rules.yml` e `flows.yml`, e `choices: []`. A escolha opcional de preservação de cobertura tem campos tipados e não autoriza novo escopo, mudança de ritmo ou redução de cobertura. A escolha aceita `basis` com resumos SHA-256 de `environment`, `authorization`, `accounts`, `planning`, `openapi`, `data_rules`, `flows` e `engine`. Para escolha preenchida, `validate` e `diff` retornam `strategy_state: review_required`, `basis_status: engine_unavailable` e `basis_context` com `engine: null`. O vínculo completo é necessário para compilação; não há reutilização V1.9 demonstrada. Veja o formato no [guia](../guides/personalizacao.md).

Com `--json`, sucesso usa `schema_version: 1`, `ok: true` e `data`, com saída 0. Entrada inválida, escolha não compilável ou destino recusado usam `CONFIG_ERROR`, saída 2. Consultar ou compilar não aprova o produto: os comandos com tráfego continuam sujeitos à aprovação humana e às verificações de escopo. Para os demais erros, consulte [códigos de saída](exit-codes.md).
