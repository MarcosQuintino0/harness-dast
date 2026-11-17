# 0084. Localização da apresentação do painel e do relatório

- **Status:** Proposto
- **Data:** 2026-11-16
- **Origem:** organização V1.9.4

## Contexto

HTML, CSS, tokens e textos de tela vivem junto de regras e modelos puros em `domain/panel/`
e nos módulos `domain/report_*` (agrupados em `domain/report/` nesta entrega).
A pureza torna a renderização determinística e testável, mas não faz de HTML e CSS regras de negócio.
Alterar uma tela hoje exige navegar pela mesma camada que decide escopo, severidade e cobertura.

## Decisão proposta

Vamos recomendar a migração futura da **renderização** para `adapters/reporting`, mantendo
modelos semânticos, cálculo de cobertura, agrupamento de achados e decisões em `domain`.
Nesta entrega, só agrupamos módulos dentro da camada atual. Nenhuma apresentação muda de camada.
O aceite desta proposta e a migração exigem uma entrega própria.

Textos específicos de tela, templates HTML, CSS e tokens acompanham o renderizador.
Vocabulário de estados e mensagens que expressem um contrato do domínio permanecem no domínio.
A separação deve ser feita por responsabilidade, e não movendo toda a pasta do painel de uma vez.

## Alternativas consideradas

| Alternativa | Vantagem | Custo |
| --- | --- | --- |
| Manter apresentação no domínio | Pureza, testes rápidos, nenhuma fronteira nova | Acopla tecnologia de tela e regras; dilui o significado da camada |
| Renderizar em `adapters/reporting` | Localiza decisões de HTML/CSS, preservando domínio sem tecnologia de saída | Exige distinguir modelos semânticos de formatação e coordenar geração sem importação inversa |

Recomendamos a segunda alternativa. Testes puros podem continuar testando renderizadores do adaptador,
sem navegador, rede ou Docker. Testabilidade não exige que o código esteja no domínio.

## Migração futura

1. Inventariar os módulos que só formatam e as dependências dos modelos de visão e de relatório.
2. Preservar modelos e regras no domínio; extrair HTML/CSS e textos exclusivos de tela para reporting.
3. A aplicação recebe o renderizador pela composição da CLI; se a fronteira exigir uma porta nova,
   registrar o contrato e seus dublês antes de implementar. Não criar importação de adaptador pela aplicação.
4. Mover testes de renderização, mantendo os mesmos golden, escape de texto hostil, CSP,
   paridade de tokens, navegação, estados e acessibilidade já verificados.
5. Rodar os seis gates sem enfraquecer os contratos de camada; conferir páginas no navegador
   e preservar byte a byte as saídas quando nenhuma mudança visual tiver sido aprovada.

## Consequências

A migração localizará a tecnologia de apresentação e manterá regras testáveis no domínio.
Pode revelar módulos mistos que precisarão ser divididos antes da movimentação.
Não autoriza mudar CLI, envelope JSON, perfil, códigos de saída ou conteúdo dos relatórios.
O custo e a prova visual ficam para essa entrega futura; a V1.9.4 não os declara realizados.
