# QA que testa

Use apenas o laboratório local ou um ambiente de teste autorizado. Use dados sintéticos e registre a autorização escrita do dono do produto. [Finalidade e uso responsável](../como-funciona/finalidade-e-uso-responsavel.md)

## Prepare a máquina

Você precisa de Claude Code com o plugin `hdast` habilitado, Git, `uv` e Docker. Mantenha o Docker aberto durante o teste. A TI distribui o plugin pela configuração gerenciada. [Configuração gerenciada](README.md#configuração-gerenciada)

Se o `uv` estiver ausente, instale-o no seu terminal e reabra o Claude Code. Digite `/hdast:preparar` no Claude Code para diagnosticar a máquina. A skill pede sua permissão para cada instalação. Se a máquina exigir administração ou bloquear a instalação, acione a TI. [Guia de instalação](../comecar/instalar.md#com-o-plugin)

## Faça o primeiro teste pelo pedido mínimo

1. **Pasta.** Crie uma pasta de trabalho separada e abra o Claude Code nela. O plugin instalado dispensa o clone da ferramenta. Os arquivos gerados ficam em `products/`, `cartas/` e `runs/`.
2. **Arquivos.** Separe o Swagger ou OpenAPI, um arquivo de usuários de teste com apelido, papel e login, e a documentação de negócio. Guarde as senhas para o terminal. A CLI precisa do OpenAPI ao lado da carta gerada em `cartas/`.
3. **Pedido.** Indique ao Claude os três arquivos. Você pode usar este pedido.

   > Use o pedido mínimo do hdast para cadastrar este produto a partir de `openapi.yml`, `usuarios.md` e `negocio.md`. Pare antes do teste para eu revisar e aprovar o perfil.

4. **Quatro perguntas.** O Claude faz todas numa rodada. Cada uma aceita “não sei”.

   | Pergunta | Como responder |
   | --- | --- |
   | É ambiente de teste, com dados sintéticos e autorização do dono? Quem é o dono? | Confirme as condições e informe o nome. “Não” ou “não sei” encerra o cadastro. |
   | Qual é o endereço do ambiente de teste? | Informe o endereço confirmado pelo dono. O campo `servers` do Swagger é só uma sugestão. Sem endereço confirmado, o cadastro para. |
   | Qual é a força do teste? | `LOW` faz menos variações e é mais rápida. `MEDIUM` equilibra tempo e profundidade. `HIGH` faz mais variações e aumenta tempo e carga. “Não sei” usa `LOW`. |
   | O ambiente pode receber dados de teste gravados pela ferramenta? | Responda conforme a autorização. “Não” ou “não sei” mantém desligadas as três capacidades de escrita sujeitas a essa pergunta. |

5. **Aprovação.** Quando o perfil estiver pronto, rode você mesmo `hdast setup <produto>` no seu terminal, na pasta de trabalho. Informe ali as senhas que faltam. Confira o endereço, o escopo, os caminhos negados, as capacidades, as escritas, a validade e a janela. Se houver divergência com a autorização, saia sem aprovar e peça a correção do pedido. Depois da aprovação, peça ao Claude que continue com o perfil aprovado.
6. **Relatório.** Abra `runs/<run_id>/report.html` no navegador. Veja os achados e as lacunas de cobertura. O relatório em texto fica na mesma pasta, em `report.md`. [Como ler o relatório](../referencia/relatorio.md)

[Decisão do pedido mínimo](../decisoes/0120-pedido-minimo-com-padroes-e-aprovacao.md)

## Repita ou reteste

Com o mesmo perfil aprovado e vigente, mantenha o Docker aberto e peça ao Claude para repetir o teste dentro da janela autorizada. Para repetir pelo terminal, suba a pilha com `hdast stack up <produto>` e rode `hdast run <produto>`. Após uma correção, use `hdast retestar <produto> --run <run_anterior>` com a pilha desse produto para voltar às operações dos achados selecionados. O resultado fica em `retest.json`. [Referência do reteste](../referencia/cli.md#hdast-retestar)

A validade padrão do pedido mínimo é de 30 dias. Quando vencer, pare e peça a renovação escrita ao dono do produto. Atualize o cadastro com base na renovação. Você precisa revisar e aprovar o perfil regenerado no seu terminal com `hdast profile approve <produto>` ou com `hdast setup <produto>` se também faltarem senhas. Retome dentro da janela autorizada. [Autorização e escopo](../como-funciona/operacao/authorization-and-scope.md)
