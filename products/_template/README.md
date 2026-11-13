# Modelo de perfil de produto

> **Schema em evolução (M2).** Os modelos do perfil já existem em
> `src/harness_dast/domain/profile.py` e um teste de contrato garante que
> `target.yml` é aceito por eles. O leitor de YAML e os comandos `hdast init`
> e `hdast profile validate` existem desde o M2. Nomes e
> campos podem mudar até o fim do M2.

Um **perfil de produto** é a pasta que diz ao `hdast` o que pode ser testado
em um produto, com quais limites, contas e regras de dados. Esta pasta é o
modelo para criá-lo.

## Onde ficam os perfis reais

**Fora deste repositório.** Este repositório é genérico e **nunca deve conter
dados de empresa**: hostnames, contas, tickets de autorização, SQL de produto.
Os perfis reais ficam em um repositório privado da empresa, e a variável de
ambiente `HDAST_PRODUCTS_DIR` aponta para ele. Copie `products/_template` para
lá, renomeando a pasta para o nome do produto.

## Arquivos

| Arquivo | Para quê |
|---|---|
| `target.yml` | Ambiente, escopo, autorização, limites, autenticação e limpeza. É o arquivo mais sensível: `scope`, `limits` e `authorization` vêm da autorização formal do dono do produto. |
| `data-rules.yml` | Como gerar valores válidos e únicos por campo ou operação, para a API não responder 400 ou 409. |
| `flows.yml` | Quais operações produzem valores que outras consomem (por exemplo, o `id` devolvido ao criar). |
| `cleanup/README.md` | Regras do hook de limpeza. |
| `cleanup/cleanup.sql.example` | Exemplo fictício de script de limpeza. O real é `cleanup/cleanup.sql`. |

O OpenAPI do produto (`openapi.json`) também mora na pasta do produto.

## Regras que valem aqui

- **Segredos nunca entram nos arquivos.** Só `secret_ref: "env:NOME"`; o valor
  fica em variável de ambiente da máquina de quem executa.
- O agente só vê **apelidos** de conta (`user_a`), nunca credenciais.
- Só ambiente de teste, com dados sintéticos.
- Escopo, limites e autorização não se ampliam por conveniência. Se o escopo
  parecer curto, peça ao dono do produto.
- O script de limpeza é de **autoria humana**.

## Passo a passo (quando o leitor de perfil existir)

1. Copie esta pasta para `$HDAST_PRODUCTS_DIR/<produto>/`.
2. Preencha `target.yml` com os dados da autorização formal.
3. Coloque o OpenAPI em `openapi.json`.
4. Deixe o agente propor `data-rules.yml` e `flows.yml`; revise.
5. Peça ao time do produto o `cleanup/cleanup.sql`.
6. Rode `hdast profile validate`.
