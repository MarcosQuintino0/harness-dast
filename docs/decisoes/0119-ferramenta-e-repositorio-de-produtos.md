# 0119. Ferramenta distribuída por versão e repositório de produtos separado

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** pergunta do dono durante a reestruturação: o agente que edita o perfil de um produto pode editar a própria ferramenta? E como levar a ferramenta para o GitLab da empresa sem o laboratório?

## Contexto

Hoje a mesma pasta serve para desenvolver a ferramenta e para operar contra produtos:

- Os perfis ficam em `products/<produto>/`, dentro do clone, ignorados pelo Git. A pasta pode mudar com `HDAST_PRODUCTS_DIR`. A aprovação fica fora do clone, em `<estado>/approvals/<produto>.json` (ADR 0037).
- A aprovação guarda a impressão digital dos blocos de proteção (`domain/scope_fingerprint.py`). Se o agente alterar escopo, limites, autorização ou outro bloco protegido, a CLI recusa com `SCOPE_NOT_APPROVED` até uma pessoa aprovar de novo. Editar dados e fluxos não alarga nada e não pede aprovação. **O perfil já está protegido.**
- O `guard.py` e o `settings.json` barram escrita em aprovações, confirmações humanas, `.claude/settings.json`, hooks, `.mcp.json` e scripts de limpeza.
  O agente que opera continua podendo editar `src/`, `docker/`, `compose.yaml` e as skills.
- O `stack up` usa as imagens publicadas (ADR 0113). Com `HDAST_STACK_BUILD=1` ou `--build`, ele constrói o ZAP e o proxy de escopo a partir do código do clone. Até a primeira publicação, na tag `v1.12.2`, construir localmente era o caminho normal.
  Na rodada cega de 2026-11-18 no Codespaces, o próprio agente avaliado ligou o `HDAST_STACK_BUILD=1` quando o `stack pull` falhou.
  Um agente que alterasse a cerca em `docker/scope-proxy/` teria a mudança construída na subida seguinte. A conferência da imagem lê só o rótulo de versão, que pode ser forjado (limite residual do ADR 0113).
- O repositório também traz o laboratório, as avaliações cegas e seus gabaritos, o Codespaces, os vídeos e a documentação de desenvolvimento. Para usar na empresa, nada disso é necessário, e parte não deveria ir (gabaritos, histórico de rodadas).
- O dono quer rodar de novo o teste de um produto com um clique: um job por produto numa pipeline, ou um botão no painel. A CI deste repositório testa a ferramenta, e misturar nela jobs de produtos exporia dados de produtos num repositório público.

Sem decisão, operar continua dentro do código da ferramenta. Levar para a empresa passaria a significar clonar o laboratório junto.

## Decisão

Vamos separar **a ferramenta** de **os produtos**.

1. **Este repositório continua sendo o da ferramenta**, com o laboratório, as avaliações e o Codespaces. Eles provam a ferramenta e servem de portfólio. A CI dele continua só testando a ferramenta.
2. **A ferramenta é distribuída por versão.** Cada tag `v<versão>` publica:
   - o pacote Python (wheel anexado ao release);
   - as imagens do ZAP e do proxy de escopo no registro, com atestado (ADR 0113).
   O `compose.yaml` do pacote referencia as imagens por `tag@sha256:<digest>`. A distribuição não leva `lab/`, `evals/`, `.devcontainer/`, `tests/` nem `docs/desenvolver/`.
3. **Operar acontece num repositório de produtos**, criado a partir de um modelo novo (`hdast-produtos`), um por time. Ele contém:
   - `products/<produto>/`: perfil, regras de dados, fluxos, carta e OpenAPI;
   - `hdast-version`: a versão da ferramenta e os digests das imagens;
   - as instruções de operação (a Parte B do `AGENTS.md`), as cinco skills de uso daquela versão, o `guard.py` e o `settings.json`;
   - a pipeline, com um job por produto.

   O agente trabalha só nesse repositório. O código da ferramenta não está lá para ser editado.
4. **Sem código-fonte, a CLI não constrói a cerca.** Quando a ferramenta roda instalada como pacote, `--build` e `HDAST_STACK_BUILD=1` falham com mensagem clara. A subida usa só as imagens fixadas por digest.
5. **Uma pipeline por produto, no repositório de produtos.** Os jobs são manuais ou agendados (GitLab CI na empresa, GitHub Actions no repositório pessoal). Cada job:
   - instala a versão de `hdast-version`;
   - lê as senhas das variáveis protegidas da CI, pelo `secret_ref`;
   - roda `hdast run` e publica o relatório como artefato.

   Ele só roda com uma aprovação válida para a impressão digital atual do perfil, e qualquer mudança nos blocos de proteção faz o job falhar até uma pessoa aprovar de novo. Onde a aprovação fica para a CI ler (arquivo versionado sob proteção de branch e de revisão, ou outro meio) é um contrato novo e terá ADR próprio antes de implementar.
6. **Uma skill de uso nova, `create-pipeline`.** Ela gera o job de um produto a partir de um modelo. Ela não grava aprovação, não liga capacidade de ataque e não muda escopo. O painel pode, depois, disparar o mesmo job.

## Alternativas consideradas

- **Manter tudo junto e barrar `src/` e `docker/` no `guard.py` durante a operação.** Quem desenvolve precisa dessas pastas abertas, e a fronteira entre desenvolver e operar no mesmo clone dependeria de modo ou de prompt. Isso contraria a regra de que a trava fica em código.
- **Levar agora o laboratório para outro repositório.** A segunda opinião da reestruturação recomendou mantê-lo junto, porque ele prova a ferramenta a cada mudança. A distribuição por versão resolve a empresa sem dividir o desenvolvimento.
- **A empresa clonar este repositório inteiro.** Levaria laboratório, gabaritos, histórico e Codespaces, e o agente continuaria operando junto do código.
- **Jobs de produtos na CI deste repositório.** Misturaria o teste da ferramenta com a operação e exporia dados de produtos num repositório público.

## Consequências

- A brecha de operar junto do código fecha pela estrutura. A cerca que roda é a imagem publicada e conferida por digest.
- Cada versão nova da ferramenta vira um passo explícito no repositório de produtos (trocar `hdast-version`), com a impressão digital conferida de novo.
- Nasce trabalho novo:
  - publicar o pacote;
  - fixar os digests;
  - criar o modelo do repositório de produtos;
  - recusar o build sem código-fonte;
  - criar a skill `create-pipeline`;
  - escrever o ADR do armazenamento da aprovação para a CI.
- A rodada cega continua usando uma cópia preparada do repositório da ferramenta. Ela pode passar a usar o modelo do repositório de produtos, o que deixaria a avaliação mais perto do uso real.
- O GitLab da empresa recebe só o modelo do repositório de produtos e o espelho das imagens e do pacote.

## Plano em fases

| Fase | Entrega | Onde | Depende de |
| --- | --- | --- | --- |
| A | Imagens publicadas e `compose.yaml` com `tag@sha256` | Este repositório | Tag `v1.12.2` (publicada em 2026-11-18) |
| B | Wheel no release e instalação por `uv tool install` | Este repositório | A |
| C | `--build` e `HDAST_STACK_BUILD=1` recusados sem código-fonte, com teste | Este repositório | B |
| D | Modelo `hdast-produtos`: `products/`, `hdast-version`, Parte B, cinco skills, guard e settings | Repositório novo | B |
| E | ADR do armazenamento da aprovação para a CI | Este repositório | D |
| F | Skill `create-pipeline` e job de exemplo (GitHub Actions e GitLab CI) | Modelo | E |
| G | Rodada cega dentro do modelo de produtos | Codespaces | D |

## Aceites verificáveis

- O pacote instalado não contém `lab/`, `evals/`, `tests/`, `.devcontainer/` nem `docs/desenvolver/`.
- Com a ferramenta instalada como pacote, `hdast stack up --build` e `HDAST_STACK_BUILD=1` falham com mensagem que manda usar as imagens publicadas.
- O `compose.yaml` distribuído só referencia imagens por digest.
- No modelo de produtos, o agente não acha código da ferramenta para editar. O `guard.py` e o `settings.json` do modelo barram escrita fora de `products/` e dos arquivos de trabalho.
- Um job de produto falha quando a impressão digital do perfil não tem aprovação válida.
- A CI deste repositório não ganha nenhum job de produto.
