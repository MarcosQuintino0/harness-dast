# Relatório da versão 1.5.0

Preparado em 2026-11-14. Branch `feat/v1-5`.
Plano do ciclo [V1.3 a V1.8](../plans/2026-11-14-ciclo-v1-3-a-v1-8.md).

## 1. Resumo

A V1.5 acrescenta diagnósticos de entrada, erros e cobertura ao fluxo offline do `hdast`.
A candidata reúne as quatro entregas do recorte defensivo, mais a portabilidade para Codex.

## 2. Alterações

| Item do plano | Estado nesta entrega | Decisão |
| --- | --- | --- |
| Sinais de erro interno | Entregue como análise passiva das evidências redigidas já disponíveis | [ADR 0045](../adr/0045-sinais-passivos-de-erro-interno.md) |
| Operações que responderam 404 | Entregue a explicação da lacuna de cobertura. Inclusão automática dessas operações na varredura fica fora da entrega | [ADR 0046](../adr/0046-cobertura-de-operacoes-com-404.md) |
| Valores que o esquema proíbe | Entregue diagnóstico dos exemplos locais do OpenAPI. Envio automatizado de valores inválidos fica fora da entrega | [ADR 0047](../adr/0047-validacao-offline-de-exemplos-openapi.md) |
| Multipart | Entregues identificação de operações e ensaio de codificação e leitura de um arquivo sintético em memória. Aplicação ao probe e ao scan fica fora da entrega | [ADR 0048](../adr/0048-multipart-funcional-offline.md) |
| Portabilidade do Codex | Entregue o guia e isolamento dos briefings ao preparar a cópia cega | [AGENTS.md](../../AGENTS.md) |

Os quatro ADRs estão no estado Proposto.

## 3. Evidências

Em `C:\harness-dast-artefatos\v1.5\`:

- `relatorio-offline/` registra os três formatos de relatório gerados a partir de uma fixture salva. A amostra tinha três mensagens examinadas e uma resposta HTTP 5xx.
- `cobertura-404-offline/` registra um relatório sintético em JSON, Markdown e HTML. A operação mantém o código de motivo `not_success` e informa o HTTP 404 observado pelo probe.
- `spec-inspect-inicial.json` é a saída da CLI para um OpenAPI sintético. Foram sinalizados um campo obrigatório ausente e um número abaixo do mínimo.
- `preparacao-cega.txt` registra a preparação offline da cópia da Clínica Piloto, com 34 exclusões e zero termos de gabarito detectados naquela árvore. O guia estava presente, e os planos do coordenador e gabaritos estavam ausentes.
- `spec-inspect-multipart.json` registra a operação de upload de demonstração com `multipart_offline: true`, sem copiar o corpo nem a boundary para a saída.
- `gates/` guarda as saídas dos gates por integração.

## 4. Qualidade e testes

| Gate | Resultado |
| --- | --- |
| Ruff | Sem erros |
| Formatação | 844 arquivos conferidos |
| mypy Windows e Linux | 701 arquivos sem erros em cada execução |
| import-linter | 372 arquivos, 2.261 dependências e 6 contratos preservados |
| Vulture | Sem código sem uso reportado pelo gate |
| Cobertura local | Ramos de domínio 98,6% (piso 95%) e de aplicação 96,9% (piso 85%). Linhas alteradas da V1.5 94% (piso 90%), comparadas com a base `origin/feat/v1-4` usada na candidata |
| pytest | 7723 passaram, 5 pulados e 67 desmarcados em 211.42s (0:03:31) |

O teste focado do QA integrado passou nos três casos. Os logs detalhados estão em C:\harness-dast-artefatos\v1.5\gates.

## 5. Problemas e decisões

A suíte da base `e0521d5` falhou nos três casos de detecção de vazamento da cópia cega. O briefing de coordenação estava sendo entregue na cópia. A exclusão de `docs/plans/` preservou a entrega do AGENTS.md e reduziu a exposição de material do coordenador. A V1.4 também retirou a referência literal do seu briefing, no commit `f30a077`.

O QA independente reproduziu dois defeitos na árvore integrada. A suíte com as duas primeiras regressões teve 7.586 aprovados e duas falhas esperadas antes das correções. Um terceiro teste local, acrescentado após a coleta, também reproduziu o defeito de exemplo nulo.

| Constatação | Correção |
| --- | --- |
| Um exemplo `null` pulava a conferência do enum quando o schema permitia o tipo nulo | A inspeção passou a verificar o tipo e a presença de `null` no enum independentemente, com teste direto e documentos OpenAPI locais. A geração anterior manteve a semântica. |
| Multipart na posição 21 desaparecia do resumo | A inspeção olha as chaves de mídia separadamente dos esquemas até seu limite. Acima do limite ou com chave que não cabe na análise, o aviso fica visível. A preferência da mídia usada no caminho normal é a mesma. |

## 6. Em linguagem simples

- **Erro interno.** Se entre as respostas já guardadas houver uma mensagem com um código de erro de banco, o relatório conta um possível sinal e informa quantas mensagens examinou.
- **HTTP 404.** Se uma operação respondeu que um recurso não foi encontrado e ficou sem varredura, o relatório mostra essa resposta e o motivo registrado para ter ficado de fora.
- **Exemplos do OpenAPI.** Se o contrato exige uma quantidade de pelo menos um e o exemplo declara zero, a inspeção indica a divergência sem repetir o valor.
- **Envio de arquivo.** A inspeção identifica uma operação que declara multipart e mostra o resultado de montar e ler um arquivo sintético pequeno em memória.
- **Cópia cega.** O agente recebe um guia de como operar o projeto. A cópia exclui os planos do coordenador e mantém o teste de vazamento.

## 7. Propostas avaliadas

A análise dos sinais no proxy e a coleta extra de respostas ficaram fora da entrega. A verificação usa as evidências redigidas disponíveis. Para multipart, manteve-se o limite de parse dos esquemas e separou-se a detecção das chaves de mídia na inspeção offline.

## 8. Limites da prova

A análise de erros tem a cobertura das evidências já coletadas. Zero sinais só descreve essa amostra, e a classificação heurística pode errar. A inspeção do OpenAPI verifica um subconjunto de regras e exemplos locais representados. A prova multipart é sobre o formato sintético em memória. A compatibilidade com um servidor de upload continua sem prova.

Os degraus de teste ativo e varredura completa previstos para a versão original não foram executados. O exercício cego offline usou briefing reduzido e outro modelo e ferramenta, sem pontuação comparável às rodadas de laboratório. Depois de preparar a .venv com o cache local em modo offline, o agente executou a inspeção de uma cópia do OpenAPI da Clínica Piloto e obteve saída 0, 40 operações, nenhuma omitida e 11 marcadas fora do escopo do perfil fictício. Os resultados estão em `exercicio-cego-offline/`. O ambiente inicial da cópia precisava ser preparado pelo coordenador.

## 9. Fechamento e modelos

Esta branch é uma candidata. A base traz `origin/feat/v1-4` (`d9d1780`), enquanto `origin/develop` estava em `03320af` na validação. A integração da V1.4 é pré-requisito do PR da V1.5. A publicação também precisa passar pelo CI e pelas revisões aplicáveis.

Programação e QA usaram GPT-6.1 Terra. Três programadores trabalharam em high e um em xhigh, para multipart. A portabilidade usou GPT-6.1 Terra high. A coordenação usou GPT-6.1 Sol e o exercício cego offline usou GPT-6.1 Terra high em sessão sem histórico. Ao todo, sete subagentes distintos (quatro de programação, um de documentação, um de QA e um de exercício cego).

## 10. Integração com a V1.4 (coordenador)

Depois de a V1.4 entrar na `develop` (PR #7), a `develop` foi juntada nesta branch. Houve conflitos só na versão, no lock, no `CHANGELOG.md`, no roadmap, no índice de ADRs e num import de `report_markdown.py` (as células de tabela passaram a usar `cell_code`, da V1.4). Gates sobre o resultado: ruff sem problemas, 853 arquivos formatados, mypy sem problemas em 708 arquivos nas duas plataformas, 6 contratos do import-linter, vulture limpo e pytest com 7875 aprovados e 4 pulados.

A V1.5 fica registrada no roadmap como **entregue em parte**. Ficaram fora, para uma próxima entrega:
- a cerca lendo as respostas em busca de sinais de erro interno;
- atacar as funções que deram "não encontrado" (`scan.include_outcomes` no `run`, vindo da carta);
- enviar ao alvo valores que o esquema proíbe;
- o `multipart` aplicado ao `probe` e ao `scan`.
