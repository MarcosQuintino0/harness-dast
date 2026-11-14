# Painel da execução: design final

> **Status: design aprovado pelo dono em 2026-11-14, ainda não implementado.** Nada nesta pasta é código do produto. São o desenho das telas, o sistema de design e as decisões que ficaram em aberto. Não trate nenhuma tela ou comando citado aqui como existente; o que existe hoje é o `report.html`.

O painel da execução é o conjunto de páginas que a CLI vai gerar para a pessoa de QA e para o dono do produto entenderem um teste: o que foi achado, o que fazer, e o que o agente e a CLI fizeram. Quem lê não domina jargão de segurança, rede ou arquitetura.

## Como ver

Abra qualquer arquivo `.html` desta pasta no navegador. São páginas paradas, sem JavaScript e sem nada de fora, com a mesma política de segurança do `report.html`. Os links entre as telas funcionam.

- Comece por [`screens/products.html`](screens/products.html) e navegue.
- O canvas original, com todas as rodadas de exploração, está em <https://claude.ai/artifact/AWqtPUpgockHhGJCYkwpdV> (privado; só abre para quem o dono compartilhar).

## O que tem nesta pasta

| Arquivo | O que é |
| --- | --- |
| [`tokens.css`](tokens.css) | Cores, espaços, cantos, letras e tempos, com nome. É para copiar. |
| [`screens/products.html`](screens/products.html) | Entrada: todos os produtos testados e os últimos testes. |
| [`screens/product-history.html`](screens/product-history.html) | Um produto: histórico de testes e o que mudou entre eles. |
| [`screens/summary.html`](screens/summary.html) | Um teste, aba Resumo: deu certo? o que faço agora? |
| [`screens/live.html`](screens/live.html) | Aba Ao vivo: só existe durante o teste. |
| [`screens/stages.html`](screens/stages.html) | Aba Etapas: substitui a Ao vivo quando o teste termina. |
| [`screens/findings.html`](screens/findings.html) | Aba Falhas: confiança, o que fazer e como reproduzir à mão. |
| [`screens/coverage.html`](screens/coverage.html) | Aba Cobertura: mapa das funções, a cerca, o que ficou de fora. |
| [`screens/terminal.html`](screens/terminal.html) | Aba Terminal: cada comando do agente, com tradução. |
| [`screens/time-and-tokens.html`](screens/time-and-tokens.html) | Aba Tempo e tokens. |
| [`screens/summary-light.html`](screens/summary-light.html) | O Resumo no tema claro (único desenhado no claro). |
| [`system/colors.html`](system/colors.html) | Paletas escura e clara, com contraste. |
| [`system/typography.html`](system/typography.html) | Letras e escala de tamanhos. |
| [`system/spacing.html`](system/spacing.html) | Espaços, cantos, camadas e como a tela se adapta. |
| [`system/tokens.html`](system/tokens.html) | O `tokens.css` explicado e a troca de tema. |
| [`system/components.html`](system/components.html) | Componentes, parte 1. |
| [`system/components-2.html`](system/components-2.html) | Componentes, parte 2, estados de interação e marcadores de estado. |
| [`system/motion.html`](system/motion.html) | Animações (rodando na página), com tempo e curva. |
| [`system/states.html`](system/states.html) | Estados fora do caminho feliz. |
| [`system/formats.html`](system/formats.html) | Formato de número e data, palavras de estado, casos-limite. |
| [`system/handoff.html`](system/handoff.html) | Acessibilidade, jeito de escrever e de onde vem cada dado. |

## A estrutura

São três níveis, do geral para o detalhe. O caminho fica sempre no alto, à esquerda (`hdast / Clínica Piloto / 13/11/2026 · 20:08`), e cada pedaço é um link.

1. **Produtos.** Um cartão por produto.
2. **Um produto.** O histórico de testes dele.
3. **Um teste.** O painel com o menu de abas, sempre nesta ordem:

| Aba | Pergunta que responde |
| --- | --- |
| Resumo | Deu certo? O que faço agora? |
| Ao vivo (durante) ou Etapas (depois) | Em que passo está? O que aconteceu em cada um? |
| Falhas | O que foi achado e dá para acreditar? |
| Cobertura | O que foi e o que não foi testado? |
| Terminal | O que o agente fez, comando por comando? |
| Tempo e tokens | Quanto tempo e quanto trabalho do agente? |

## Decisões tomadas com o dono

- **Tema escuro é o principal.** O claro é opção e segue o aparelho.
- **Menu de abas em cima**, um assunto por tela.
- **Visual enxuto, mas não vazio:** painéis, etiquetas coloridas, números em destaque e barras.
- **Terminal cru**, com a frase que traduz cada comando ao lado.
- **Quando o teste termina, a aba "Ao vivo" some e vira "Etapas".**
- **Cada falha mostra como reproduzir à mão:** método, endereço, cabeçalhos, corpo e a resposta que o teste recebeu.
- **O token nunca aparece.** O painel mostra o apelido da conta (`user_a`) e deixa o lugar do token marcado. A ferramenta não grava senha nem token.
- **Histórico por produto**, com data, hora, o que rodou, quantas funções, falhas, duração e tokens.
- **Sem tela de glossário.** Palavra técnica vem explicada na própria tela, na primeira vez em que aparece.

## Regras do desenho que não podem se perder

1. **Estado nunca só por cor.** Cada estado tem forma própria e palavra. Ver `system/components-2.html`.
2. **Quatro cores com significado:** verde feito, azul agora e clicável, vermelho grave, amarelo atenção. Gráfico de quantidade usa branco e cinza.
3. **Uma palavra para cada estado.** A lista fechada está em `system/formats.html`.
4. **O medidor de confiança são três degraus, não nota:** a confirmar, prova forte, confirmada. A terceira barra só enche quando uma pessoa confirma.
5. **Sem JavaScript obrigatório e sem recurso externo.** Tudo que vem do sistema testado entra como texto.
6. **Nunca "seguro" nem "aprovado".** Sem falha grave não é atestado.

## Sobre os números das telas

- **Reais:** os totais da rodada cega de 2026-11-13 na Clínica Piloto (40 funções, 30 tentadas, 27 alcançadas em 4 tentativas, 26 varreduras, 19 min de varredura, 16.854 pedidos, 8.651 barrados, 91 achados, 28 min, 151 mil tokens) e a prova da falha de injeção de SQL. Fonte: [`docs/reviews/2026-11-13-rodada-cega-v1-1.md`](../../reviews/2026-11-13-rodada-cega-v1-1.md).
- **Marcados "ex." ou "exemplo" na tela:** tempo e tokens por etapa e por comando, horários, saídas do terminal, tipos de teste, quase todas as linhas do histórico, o segundo produto. A marca existe só no desenho e some na página de verdade.
- **De exemplo, sem marca:** a distribuição função a função no mapa da Cobertura (os totais batem; a lista exata viria do `scan.json`) e o motivo de "Entrar (login)" e "Alterar meu perfil" não terem sido atacadas.

## O que falta para implementar

### Dados que as telas pedem e ainda não existem

| O que a tela mostra | De onde viria | Situação |
| --- | --- | --- |
| Lista de comandos do agente, com hora, resultado e resposta | diário de comandos gravado durante o teste | não existe |
| Nome simples de cada função e a "parte do sistema" | campo novo no perfil do produto | não existe |
| Explicação simples da falha, "o que fazer" e "quem faz" | catálogo fixo por tipo de falha | não existe |
| Páginas de Produtos e de Histórico | comando novo que lê as pastas de teste e monta os índices | não existe |
| Tempo por etapa e por regra do ZAP | `metrics.json`, `rule-stats.json` (ADR 0031) | em construção |
| Tokens por etapa e por comando | `agent-metrics.json` | em construção, hoje só na avaliação cega |
| Validade da carta | janela de autorização no `target.yml` | a conferir |

### Decisões que pedem ADR

- **Como o "ao vivo" funciona.** Sem JavaScript, a CLI regrava a página e ela se recarrega sozinha a cada 15 s: simples, mas a tela pisca. Com JavaScript, o terminal rola de verdade, e isso quebra a regra atual de não ter script na página.
- **Várias páginas por teste** (uma por aba, uma por falha grave) em vez de um arquivo só.
- **Comando novo** para gerar os índices de produtos e histórico, e o contrato do diário de comandos.
- **Mascarar CPF, e-mail e telefone na prova**, mesmo em ambiente de teste. O dono ainda não respondeu.

### Desenho que ainda falta

- **Celular e tema claro:** só há exemplos (Resumo no claro; Resumo e Falhas no celular, no canvas). As outras telas não foram desenhadas nesses formatos.
- **Estados fora do caminho feliz:** `system/states.html` mostra o pedaço da tela que muda, não a tela inteira.
- **Texto para leitor de tela:** está especificado em `system/components-2.html`, mas não foi posto no HTML destas telas.
- A tabela "Estados de cada tela" em `system/handoff.html` ainda marca "falta" em linhas que `system/states.html` já cobre.

## Como foi feito

- Cinco rodadas com o dono: duas direções rejeitadas (laudo de vistoria e bula), a "sala de controle", três ideias de organização e, por fim, o painel com menu em cima. As rodadas antigas estão só no canvas.
- Um segundo agente revisou o resultado e apontou 15 problemas. Foram corrigidos: tokens com nome, componentes que faltavam no catálogo, marcadores de estado com forma própria, "como reproduzir à mão" refeito para leigo, números que não batiam entre telas, vocabulário de estados e cor neutra para gráficos.
- As telas foram conferidas em navegador no tamanho de computador (1440 px). Não foram conferidas dentro do canvas nem em celular de verdade.
