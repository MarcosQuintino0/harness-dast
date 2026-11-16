# Pré-registro V1.7 — antes das medições

Nenhuma execução de laboratório foi feita neste ramo. A referência A desta rodada não substitui a referência cega V1.5.5, que não existe. As variantes usam cópias temporárias do perfil, `scan.pacing` `legacy` (A) ou `proxy` (B), sem alterar regras, força, limites, dados nem perfis reais. Tecnologia é apenas advisory e não autoriza excluir regras. Não alterar este protocolo depois de conhecer os resultados; publicar emenda datada e motivo separadamente.

## T3: seleção e estratos

A seleção foi feita pelo mecanismo e pelo contrato/perfil, não pelo gabarito: diversifica consulta, caminho, corpo JSON, leitura, escrita, conta, CSRF e encadeamento. O probe continua integral para estabelecer dependências. A disponibilidade depende de sucesso do probe e da cerca: seleção não é prova de cobertura.

| API | Operação | Conta prevista | Entrada / dependência | Estrato |
| --- | --- | --- | --- | --- |
| Clínica | buscarPacientesPorNome | default | query `nome` | leitura parametrizada |
| Clínica | baixarDocumento | default | query `arquivo` | arquivo/caminho |
| Clínica | buscarConvenioPorCodigo | default | path `codigo` | leitura por chave |
| Clínica | criarConvenio | admin_a | JSON | escrita/CSRF, produz ID |
| Clínica | buscarConvenio | default | path `id`, criarConvenio | dependência |
| Clínica | criarMedico | admin_a | JSON | escrita/CSRF, produz ID |
| Clínica | criarPaciente | medico_a | JSON, criarConvenio | escrita e encadeamento |
| Clínica | buscarPaciente | medico_a | path `id`, criarPaciente | identidade e dependência |
| Clínica | obterPerfil | paciente_a | sem parâmetro | identidade |
| Clínica | atualizarPerfil | paciente_a | JSON | identidade e escrita |
| VAmPI | api_views.users.get_all_users | user_a | sem parâmetro | lista/identidade |
| VAmPI | api_views.users.get_by_username | user_a | path `username` | leitura parametrizada |
| VAmPI | api_views.users.me | user_a | sem parâmetro | identidade |
| VAmPI | api_views.users.update_email | user_b | path e JSON | escrita/identidade |
| VAmPI | api_views.users.update_password | user_b | path e JSON | escrita/identidade |
| VAmPI | api_views.books.get_all_books | user_a | sem parâmetro | produtor de vínculo |
| VAmPI | api_views.books.add_new_book | user_a | JSON | escrita |
| VAmPI | api_views.books.get_by_title | user_a | path, get_all_books | dependência |

Contas previstas devem ser aferidas pelos registros do probe e auditoria; default é o definido no perfil. Os valores são os gerados pelo probe e data-rules, não fixados aqui: registrar tipos, parâmetros efetivamente injetados e classes de valores, sem valores sensíveis. Não há multipart, DELETE, login ou todas as combinações de papéis; nenhum resultado deste subconjunto os cobre. As classes SQL, caminho e autorização são hipóteses de mecanismo a aferir nos controles existentes e no gabarito depois da seleção. Controles de CORS, valores proibidos, upload e atribuição em massa não são provados simplesmente por incluir uma operação: exigem T2 próprio. Ausência de uma classe ou controle em A/B é lacuna e impede alegar equivalência da classe.

## Ordem e estimador

Por API, 3 pares, em sequência AB, BA, AB; reinício da pilha entre *todas* as execuções. Pare se não for possível reconstruir o proxy, manter os mesmos limites/força/regras ou obter artefatos verificáveis. Para cada par válido calcule `100*(wall_A-wall_B)/wall_A`, usando a duração da varredura (`finished_at - started_at`); a mediana dos 3 percentuais é o ganho T3 por API. Dados ausentes, zero, truncamento, regras puladas/interrompidas, divergência não explicada de trabalho executado ou cerca/identidade sem prova invalidam o par; não imputar zero. Se sinais divergirem ou amplitude superar 10 pontos percentuais, executar mais 2 pares mediante replanejamento de orçamento; se continuar inconclusivo, B não se torna padrão.

Previsão por regra: executar T4 A antes de T4 B. Para cada regra r, F_r é o tempo completo medido em A, e q_r é a mediana dos tempos T3 B dividida pela mediana dos tempos T3 A. Estimar `wall_B = wall_A * soma(F_r*q_r)/soma(F_r)`. Todos os F_r e medianas T3 precisam ser positivos, completos e presentes em todas as amostras exigidas; ausência, truncamento ou regra sem amostra invalida a previsão. O fator `wall_A/soma(F_r)` supõe que sobreposição e overhead não medidos variam proporcionalmente com o tempo por regra: é hipótese forte, não identidade. Se houver overhead medido sem sobreposição, reportá-lo como limitação sem alterar o estimador. Congelar a previsão antes da T4 B. A diferença absoluta entre ganho previsto e observado T4 maior que 10 pontos percentuais, ou dado necessário ausente, torna a alegação de ganho completo inconclusiva. Meta: pelo menos 15% na mediana T3 por API e demais critérios satisfeitos. Sem T4 A comparável, T4 B não confirma ganho relativo. Orçamento replanejado na emenda abaixo.

A parcela paralelizável usa limites inferior e superior conservadores de tempo de parede, sem soma ingênua de regras sobrepostas. Sem linha do tempo confiável, limite inferior 0 e superior 100% (ou limite menor comprovado por intervalos exclusivos medidos); esta faixa não decide a condição de 40%. Excluir integralmente intervalos com regras de tempo/cegas, mutação compartilhada, dependências ou classificação incerta; identificar fonte de cada classificação. Medir requisições reais, política, regras, contas, escopo, controles, recursos, truncamento e limites de taxa separadamente; alertas brutos não provam trabalho equivalente. T2 cobre controles vulnerável e seguro para ambas APIs quando houver prova; qualquer indisponibilidade fica explícita. T4 não reduz operações nem regras conforme gabarito.

## Emenda anterior à primeira prova: orçamento

Decisão do coordenador: teto global de 4 horas, incluindo T2, T3, T4, builds e reinícios. A revisão é necessária porque quatro T4 estimadas em 15–30 min, doze T3 e T2 mais os resets podem exceder 3h10. Antes de iniciar cada cenário, reservar no mínimo 10 min para T3 e 30 min para T4; esses valores não são promessa de conclusão. Após o primeiro par de cada API, projetar o restante a partir dos tempos observados, incluindo T2 e resets, antes de continuar. Se não couber, parar, registrar inconclusivo e manter A padrão. A parada e desmontagem da pilha após o prazo podem consumir tempo adicional inevitável de segurança. Os testes não medem CPU atualmente; ausência da medição é lacuna explícita.
