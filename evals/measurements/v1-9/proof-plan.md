# Pré-registro de prova da V1.9

Registrado antes da primeira execução desta versão. A base é `aec8cf8`, com
V1.7/V1.8 integradas. Não há rodada cega nem estudo de reutilização nesta entrega.

## Passo zero

Executar, nesta ordem, A Clínica, A VAmPI, B Clínica, B VAmPI, cada célula em pilha
nova. A significa `legacy`; B significa `proxy`. Reduzir somente a política da
cópia descartável, mantendo uma regra do inventário histórico: 90035 na operação
`atualizarPaciente`, 40008 em `api_views.books.get_by_title`. Força, taxa, threads,
escopo, dados e prazo são os dos perfis existentes. O probe integral estabelece
as dependências; não há outra T4 no passo zero. Todas as tentativas são retidas.

Metadados permitidos: método, classes fechadas dos segmentos/valores, nomes dos
campos, comprimento dos corpos, status, estado/contagem/alertas da regra e
identidade pública do add-on. Não exportar headers, URLs concretas, corpos,
cookies, tokens, credenciais, IDs ou valores de recurso. Fontes consultadas antes
da execução: `SstiScanRule` e `ParameterTamperScanRule` no commit público
`06c3ade40fcc51a85d1227734c64451b95794ba2` (`ascanrules-v84`); o teste registra
hashes e confere a versão observada. Divergência de versão impede atribuir causa.

Na 40008, a resposta do pedido base condiciona a entrada no laço de seis vetores.
Na 90035 LOW, a heurística de similaridade com referência aleatória condiciona a
busca matemática. Essas são hipóteses derivadas do código, não causas comprovadas
dos resultados históricos. A prova isolada pode demonstrar mecanismo, mas não
reconstruir respostas históricas ausentes. Sem relação demonstrada com ambas as
diferenças históricas, conservar `legacy` e explicitar a lacuna.

## Fechamento

T1: contratos legados, conhecimento, invalidação, diário antes do envio, entrada
inválida/ausente/malformada, par 201/200 e canal de exportação. Comparação de plano
item a item, sem usar hash como prova de cobertura.

T2: controles dirigidos existentes de estratégia nas duas APIs e nos dois modos,
mais prova nova de authz e conhecimento. T4: exatamente uma completa por API no
modo vulnerável, com política e ritmo `legacy`, salvo promoção comprovada no passo
zero. Não medir A/B de velocidade se não houver promoção. Comparar com matrizes
V1.8: operações, regras/estados, lacunas, técnicas/achados, conta e estado.

Reserva fechada de laboratório: 2h30 para T2, T4, diagnóstico, preparo, resets e
reprodução selecionada do validador. O T5 dispensado libera sua reserva nominal
para o passo zero e os novos controles. Se faltar tempo, registrar prova parcial;
não diminuir força/regras da T4 ou ampliar limites. Cada bloco exige trava
exclusiva `C:\harness-dast-artefatos\lab.lock`, desmontagem e Compose vazio.

O estudo real em dois contextos e os testes cegos ficam com Claude Code após o
merge, como determina o briefing. Ensaio de exportação seco não recebe esse nome.

## Emenda anterior à primeira T4: fatos observados

Após a crítica preliminar independente, a captura deve consumir recibos reais do
probe (`knowledge capture --run`). A T4 usa os comandos públicos em sequência:
preflight, um único probe, captura e ativação explícita, scan integral, authz,
negative e report. A ordem dos pedidos ao alvo e os mesmos arquivos/política da
referência são preservados; a captura consulta somente metadados locais/controle
ZAP. Não se roda um segundo probe antes da completa, para evitar alterar suas
pré-condições. A métrica de parede continua sendo a do scan; não há alegação de
velocidade. Recibos de efeito são provados e reutilizados nos controles T2, sem
inventar uma observação quando a resposta não permite comprová-la.

## Retomada após interrupção da plataforma

Em 2026-11-16, durante `knowledge-final`, a plataforma interrompeu a sessão.
O coordenador geral desmontou `hdast` e `hdast-pilotrun` e removeu a trava desta
versão. O arquivo de saída ficou vazio e a tentativa interrompida não conta como
prova aprovada. Seus diretórios são retidos.

Antes da próxima prova, a coordenação conferiu Compose vazio, branch `4758f8a`
publicada, worktrees e alterações não commitadas do autor. A retomada preserva o
teto de **150 minutos efetivos de laboratório**, incluindo builds, resets e
reprodução independente. As quatro suítes concluídas somam 44,55 minutos
(410,56 + 512,78 + 1.227,59 + 521,61 segundos). Reservam-se conservadoramente
dez minutos para a tentativa interrompida, sem alegar seu tempo exato.

O bloco restante fica limitado a **75 minutos efetivos**, com encerramento até
2026-11-16T16:15:00Z; o total reservado permanece abaixo de 150 minutos. O novo
prazo de parede acomoda a interrupção externa e as correções independentes, sem
aumentar carga, força, regras, escopo, permissões ou duração dos perfis.
Não iniciar cenário sem reserva conservadora para finalização e desmontagem.
