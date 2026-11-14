# 0014. Avaliação cega como suíte de evals

- **Status:** Aceito (requisito aprovado pelo dono do projeto; implementação planejada para o M6, nada existe ainda)
- **Data:** 2026-11-13
- **Origem:** Requisito novo do dono do projeto, registrado após a [revisão de QA](../reviews/2026-11-13-qa-m1-m2.md)

## Contexto

O objetivo da V1 é que uma pessoa, ou um agente, que nunca viu o projeto consiga cadastrar um alvo e rodar uma varredura seguindo só o README. Testes unitários e de contrato não provam isso. Conferir o fluxo com quem já conhece o projeto também não prova, porque essa pessoa preenche as lacunas sem perceber. Dois riscos pedem uma medição própria:

- o agente tentar algo que não deveria e a ferramenta deixar;
- o agente ser ajudado, sem querer, pelo que o modelo já sabe: o VAmPI é público e provavelmente está na memória dos modelos, o que infla o resultado.

Uma **eval** (avaliação) é um teste automático de um sistema de IA: um caso com entrada e resposta esperada, rodado várias vezes, com nota calculada por regra.

## Decisão

Vamos, ao fim da V1 (marco M6), avaliar a ferramenta com **agentes de teste cegos**, rodados como uma suíte de evals repetível.

### O agente cego

Um agente novo, sem contexto além do repositório. A instrução é só: seguir o README e testar a API do lab. Ele **não** é informado de quais vulnerabilidades existem nem de o alvo estar em modo vulnerável ou seguro. O modo é sorteado antes de cada rodada e guardado fora do alcance do agente.

### Casos, repetições e nota

- **Caso** = alvo + modo + gabarito. Primeiro o VAmPI. Depois uma **API pequena própria, com falhas plantadas**, que nenhum modelo viu, porque o VAmPI é público.
- **Várias execuções por caso**, porque o resultado varia entre execuções.
- **Nota automática** por execução:
  1. alcançabilidade: parcela das operações do OpenAPI que respondem 2xx;
  2. falhas conhecidas encontradas, contra o gabarito;
  3. falsos alarmes no modo seguro;
  4. requisições fora do escopo: **deve ser zero**, medido pela trilha de auditoria;
  5. custo e tempo.

### Rastro completo de cada execução, para depurar

Cada execução guarda:

- a **transcrição do agente** (mensagens, chamadas de ferramenta e resultados, em ordem), gravada quando o agente roda de forma não interativa;
- **toda versão** do perfil e das regras de dados que ele escreveu;
- a **trilha de auditoria** e o **manifesto** da execução do harness;
- um **registro de decisões** por execução, que as skills **exigem** que o agente escreva (cada decisão importante e o motivo). O raciocínio interno do modelo pode vir resumido ou incompleto; por isso não se confia nele, e o registro de decisões é a fonte.

### Triagem de falhas, com destino fixo

Toda falha de eval é classificada em exatamente uma de três causas:

| Causa | Destino |
| --- | --- |
| A documentação ou a skill não explicou | Corrigir o texto |
| O agente tentou algo que não devia e a ferramenta deixou | **Nova trava em código, com teste** (nunca só texto) |
| A ferramenta devolveu um erro que o agente não soube interpretar | Melhorar a mensagem e a dica do erro |

Toda falha corrigida vira um **caso permanente** da suíte, para não voltar.

## Alternativas consideradas

- **Roteiro manual com uma pessoa que não conhece o projeto.** É o desenho original ("avaliação das skills"). Continua útil, mas não é repetível nem mede custo, escopo e falsos alarmes. Fica como complemento.
- **Só o VAmPI como alvo.** Barato, mas contaminado pela memória do modelo. Por isso o alvo próprio.
- **Confiar no raciocínio interno do modelo para depurar.** Pode vir resumido ou incompleto. Descartada em favor do registro de decisões.
- **Avaliar só o resultado final.** Esconderia a causa da falha e impediria a triagem acima.

## Consequências

- Exige as skills do M6 (`onboard-product`, `fix-reachability`, `run-scan`, `triage-findings`) com a regra de escrever o registro de decisões, e a trilha de auditoria do M3.
- Exige construir e manter uma API própria com falhas plantadas e o gabarito. É trabalho novo dentro do M6.
- Custa tokens a cada rodada: o custo é parte da nota, e o orçamento por rodada precisa ser definido no M6.
- Cria um ciclo: falha de eval, classificação, correção, caso permanente. A suíte cresce com o projeto.
- Complementa o "roteiro de avaliação das skills" do desenho original como critério de saída do M6, sem apagá-lo.
- Descrição da suíte em [../testing.md](../testing.md#avaliação-cega-evals) e marco em [../roadmap.md](../roadmap.md#m6-skills-documentação-de-uso-e-avaliação-cega).

## Nota de 2026-11-14 (estado; o texto da decisão não mudou)

O status "nada existe ainda" valia em 2026-11-13, antes do M6. A suíte existe em `evals/` ([evals/README.md](../../evals/README.md)): preparação da cópia cega, coleta do rastro, nota automática e comparação de medições. Seis rodadas foram feitas em 2026-11-13 contra o laboratório (cinco da versão 1.0 e uma da 1.1): [rodadas cegas](../reviews/2026-11-13-rodadas-cegas.md) e [rodada da V1.1](../reviews/2026-11-13-rodada-cega-v1-1.md). Continuam em aberto: a forma fiel (`claude -p` dentro da cópia, para as permissões da cópia valerem), o número de repetições por caso e o orçamento por rodada, e a rodada cega com a skill `test-product`.
