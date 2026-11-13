# 0005. Perfil de produto versionado

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** AD-05, P-01, P-04

## Contexto

A decisão do agente sobre como testar um produto não é determinística. Se ele reconfigurar tudo a cada execução, o resultado varia, custa caro e não é revisável.

## Decisão

Vamos tratar o perfil de produto como artefato versionado. Cada produto tem uma pasta com `target.yml` (ambiente, escopo, autenticação, limites, limpeza), `data-rules.yml`, `flows.yml` e o hook de limpeza. O agente escreve esses arquivos; a CLI os valida contra um schema e recusa o que for inválido.

- O schema tem `schema_version` desde o primeiro dia.
- O perfil aceita várias contas com papel, embora a V1 use só uma, para não mudar o schema quando o teste de autorização chegar na V2.
- A V1 suporta dois tipos de autenticação (P-04): login com usuário e senha que devolve token, e chave fixa de API. Os demais tipos ficam para depois.
- Perfis reais ficam **fora** deste repositório, em pasta apontada por `HDAST_PRODUCTS_DIR`, de preferência um repositório privado da empresa (P-01). Este repositório fica genérico.

## Alternativas consideradas

- **O agente reconfigura a cada execução.** Caro, varia, não é revisável.
- **Configuração só por flags de linha de comando.** Não escala para vários produtos.

## Consequências

- O schema vira contrato público e evolui só por adição, com migração quando houver quebra. Mudança no schema exige ADR e atualização do teste de contrato.
- A segunda execução de um produto não precisa do agente se o Swagger não mudou.
- O formato exato dos campos podia evoluir até o fim do M2. O schema v1 como implementado está em [../reference/target-yml.md](../reference/target-yml.md) e foi fixado pelo [ADR 0013](0013-schema-v1-do-perfil-de-produto.md) (nota de estado de 2026-11-13, antes do primeiro commit).
- Vale registrar por escrito com a liderança que a ferramenta é do mantenedor e sob qual licença a empresa a usa (P-01); a licença do projeto segue indefinida (P-14).
