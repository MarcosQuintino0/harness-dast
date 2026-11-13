# Pacote `cli`

Caminho: `src/harness_dast/cli/`. Decisões: [ADR 0004](../adr/0004-portas-e-adaptadores-em-tres-camadas.md) e [ADR 0010](../adr/0010-contrato-json-da-cli-e-codigos-de-saida.md).

## Responsabilidade

Ser a entrada do programa. Lê argumentos, monta as dependências, chama o caso de uso e formata a saída. A CLI usa Typer, que gera a ajuda e a validação a partir das anotações de tipo.

| Módulo | Conteúdo |
| --- | --- |
| `app.py` | Aplicação Typer, ponto de entrada `hdast` e o **tratador único de erros**, que converte `HarnessError` em envelope JSON e código de saída |
| `commands/` | Um módulo por comando; só traduz argumentos |
| `composition.py` | Único lugar que instancia adaptadores concretos (montagem manual, sem contêiner de injeção) |
| `output.py` | Único lugar onde `print` é permitido: envelope JSON, saída humana e códigos de saída |

## Pode importar

Tudo do projeto.

## Nunca deve

- Conter regra de negócio. Se uma decisão aparece na CLI, ela pertence ao `domain`.
- Usar `print` fora de `output.py`.
- Escrever em `stdout` algo além do resultado do comando (no modo `--json`, só o envelope).
- Ampliar escopo ou limites por flag. Flags só reduzem.
- Capturar exceção genérica fora do tratador único em `app.py`.

## Status

| Item | Status |
| --- | --- |
| Aplicação Typer, tratador único de erros, envelope JSON, `hdast version` | Implementado (M1). `--json` vale antes ou depois do subcomando; `hdast` sem argumentos mostra a ajuda e sai com `0`; Ctrl+C sai com `130` e `INTERRUPTED` |
| `hdast init <produto>` e `hdast profile validate <produto>` | Implementados (M2), em `commands/init.py` e `commands/profile.py`; ambos aceitam `--products-dir` (sobrepõe `HDAST_PRODUCTS_DIR`). A saída humana é um resumo em português; o JSON é `ProfileReport` / `ScaffoldedProduct` em `data` |
| `composition.py` | Implementado (M2): `build_init_product` e `build_validate_profile` ligam as portas aos adaptadores reais |
| Saída em UTF-8 | `main()` reconfigura stdout e stderr para UTF-8, para as mensagens acentuadas não quebrarem em página de código antiga |
| Demais comandos | Planejados; **não existem**. Veja [../reference/cli.md](../reference/cli.md) |
