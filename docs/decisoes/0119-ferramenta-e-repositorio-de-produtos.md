# 0119. Código mexido só roda no laboratório e o agente de teste só edita produtos

- **Status:** Proposto
- **Data:** 2026-11-18
- **Origem:** pergunta do dono durante a reestruturação. O agente que edita o perfil de um produto pode editar a ferramenta? E como levar a ferramenta, com o código-fonte inteiro, para o GitLab da empresa sem que alguém estrague o que importa?

## Contexto

Hoje a mesma pasta serve para desenvolver a ferramenta e para operar contra produtos:

- Os perfis ficam em `products/<produto>/`, dentro do clone e ignorados pelo Git, ou na pasta indicada por `HDAST_PRODUCTS_DIR`. A aprovação fica fora do clone, em `<estado>/approvals/<produto>.json` (ADR 0037).
- A aprovação guarda a impressão digital dos blocos de proteção (`domain/scope_fingerprint.py`). Se escopo, limites, autorização ou outro bloco protegido mudar, a CLI recusa com `SCOPE_NOT_APPROVED` até uma pessoa aprovar de novo. **O perfil já está protegido.**
- O `guard.py` e o `settings.json` barram escrita em aprovações, confirmações humanas, `.claude/settings.json`, hooks, `.mcp.json` e scripts de limpeza. É uma lista do que é proibido: o agente que opera ainda pode editar `src/`, `docker/`, `compose.yaml` e as skills.
- O `stack up` usa as imagens publicadas (ADR 0113). Com `HDAST_STACK_BUILD=1` ou `--build`, ele constrói a cerca a partir do clone. A conferência da imagem lê só o rótulo de versão, que pode ser forjado.
  Na rodada cega de 2026-11-18 no Codespaces, o agente avaliado ligou o `HDAST_STACK_BUILD=1` sozinho quando o `stack pull` falhou.
- O domínio já distingue os endereços do laboratório (`Host.is_lab_address`, `application/lab_targets.py`) dos alvos de verdade.
- O dono quer levar o código-fonte inteiro para a empresa, para que outros possam evoluir a ferramenta, sem que uma mudança descuidada chegue a um teste de produto. Ele também quer rodar de novo o teste de um produto com um clique, num job de pipeline.

## Decisão

Vamos separar **onde se desenvolve** de **onde se testa**, e pôr no código a regra de que só a versão lançada testa produto.

1. **O código-fonte inteiro vai para a empresa.**
   - O repositório da ferramenta é importado como está, com o laboratório, os testes e a CI.
   - A `main` fica protegida: só entra por merge request com a CI verde.
   - Um `CODEOWNERS` cobre o núcleo de segurança e exige a revisão do responsável: cerca, escopo, aprovação, impressão digital, carta, `guard.py` e `settings.json`.
   - A versão sai só por tag criada a partir da `main`.
2. **Manifesto de integridade por versão.** Na tag, a CI gera um manifesto com:
   - o hash de cada arquivo da ferramenta: `src/`, `docker/`, `compose.yaml`, hooks, `settings.json` e skills de uso;
   - o digest das imagens.

   O manifesto é publicado com atestado de origem.
3. **Código mexido só roda no laboratório.**
   - Antes de qualquer comando que toque um alvo, a CLI confere os próprios arquivos contra o manifesto da sua versão.
   - Se houver diferença, ou não houver manifesto, ela aceita só alvos do laboratório e recusa os demais com `TOOL_MODIFIED`, citando os arquivos diferentes.
   - Fora do laboratório, a cerca é sempre a imagem do manifesto, por digest, e o build local fica restrito ao laboratório.
   - A regra fica no núcleo testado, junto da decisão de escopo.
4. **O agente de teste trabalha numa pasta de produtos.**
   - Pode ser um repositório por time: `hdast-produtos`, com `products/`, `runs/`, `hdast-version`, as instruções de operação (Parte B), as cinco skills de uso, `guard.py`, `settings.json`, `CODEOWNERS` e a pipeline.
   - O QA abre o Claude Code nessa pasta.
   - A ferramenta fica instalada a partir da tag, fora dela.
   - Nessa pasta, o `guard.py` e o `settings.json` trabalham por lista permitida: escrita só em `products/` e `runs/`.
5. **Um job por produto, no repositório de produtos.**
   - O job baixa a ferramenta da tag num runner limpo e lê as senhas das variáveis protegidas, pelo `secret_ref` `env:`, que já existe.
   - Ele só roda com uma aprovação válida para a impressão digital atual.
   - Uma skill de uso nova, `create-pipeline`, gera o job sem gravar aprovação, sem ligar capacidade de ataque e sem mudar escopo.
   - Onde a aprovação fica para a pipeline ler terá ADR próprio.

## Alternativas consideradas

- **Distribuir só o pacote e as imagens, sem o código-fonte.** Fecha a brecha, mas impede a empresa de evoluir a ferramenta. O dono quer o código lá.
- **Manter `products/` dentro do repositório da ferramenta e barrar o resto pelo guard.** O agente de teste operaria dentro do código, e a proteção dependeria só da lista do guard sobre centenas de arquivos. Com uma pasta própria, o Claude Code já limita o agente à pasta aberta, e o guard só reforça.
- **Confiar só na revisão do repositório.** Ela protege a `main`, mas não impede rodar uma cópia local mexida contra um produto. A trava de integridade cobre esse caso.
- **Jobs de produtos na CI da ferramenta.** Misturaria o teste da ferramenta com a operação e poria dados de produtos no mesmo repositório do código.

## Consequências

- Quem desenvolve continua livre: com código mexido, o laboratório funciona normalmente. Para testar um produto, a mudança precisa virar versão.
- O agente de teste não alcança o código da ferramenta. Se a cópia instalada mudar, a CLI recusa o alvo real.
- **Limite:** uma conferência que roda dentro do próprio código pode ser desligada por quem edita esse código. Contra o agente valem a pasta separada e o guard. Contra uma pessoa com má intenção valem a revisão do repositório e a pipeline em runner limpo. A trava de integridade pega o descuido, não a fraude de quem tem acesso de escrita.
- Nasce trabalho novo:
  - o manifesto e o atestado;
  - a trava na CLI;
  - o modo de lista permitida do guard;
  - o modelo do repositório de produtos;
  - o `CODEOWNERS`;
  - o guia de importação no GitLab, com a CI adaptada;
  - a skill `create-pipeline`;
  - o ADR do armazenamento da aprovação.

## Plano em fases

| Fase | Entrega | Depende de |
| --- | --- | --- |
| A | Imagens publicadas por tag e `compose.yaml` com `tag@sha256` | Tag `v1.12.2` (publicada em 2026-11-18) |
| B | Manifesto de integridade gerado e atestado na tag | A |
| C | Trava na CLI: código diferente do manifesto só roda no laboratório; build local só no laboratório | B |
| D | Modelo `hdast-produtos` com guard e settings em lista permitida | C |
| E | `CODEOWNERS` do núcleo e guia de importação no GitLab, com a CI adaptada | — |
| F | ADR de onde a aprovação fica para a pipeline; skill `create-pipeline` | D |
| G | Rodada cega dentro do `hdast-produtos` | D |

## Aceites verificáveis

- Com um arquivo de `src/` ou `docker/` alterado, `hdast run <produto real>` falha com `TOOL_MODIFIED` e cita o arquivo. O mesmo comando contra a Clínica Piloto, o VAmPI ou o crAPI roda.
- Fora do laboratório, `--build` e `HDAST_STACK_BUILD=1` são recusados.
- Sem manifesto, a CLI trata a cópia como modificada.
- No modelo `hdast-produtos`, o guard barra escrita fora de `products/` e `runs/`, por ferramenta de edição e por shell.
- Um job de produto falha quando a impressão digital do perfil não tem aprovação válida.
- O `CODEOWNERS` cobre todos os arquivos do núcleo de segurança, e um teste de contrato confere a lista.
