# ADR 0066: concessão real e medição do proxy

Status: proposta para V1.7, sem prova em laboratório.

## Contexto e decisão

Reservar horários futuros não garante espaçamento entre saídas quando o escalonador atrasa
várias tarefas. O proxy serializa a concessão em seu laço de eventos, limita a fila, confere
trava e prazo após cada espera e marca o instante real da concessão. O atraso subsequente é
calculado a partir desse instante. Cancelamento libera a fila sem conceder o pedido.

Uma resposta remota 429 adia as concessões daquela instância, sem repetir pedidos. Aceita
`Retry-After` em segundos ou data HTTP entre zero exclusivo e 60 segundos inclusivo; valores
ausentes, inválidos ou fora desse intervalo provocam pausa de um segundo. Outro 429 pode
renovar o recuo. A trava e o prazo não são prorrogados, e a taxa não aumenta. Não há tentativas
automáticas, inclusive de mutações.

Enquanto o recuo estiver ativo, o proxy recusa imediatamente com HTTP 429,
`X-Hdast-Reason: rate_backoff` e `Retry-After` igual ao tempo restante arredondado para
cima. A recusa é auditada como `deny` e não chega ao destino. Pedidos já na fila são
despertados; parada e prazo continuam prioritários. Isso evita manter a conexão aberta
além do timeout do cliente sem encurtar o recuo remoto. Uma recusa é lacuna, não cobertura
executada; a aplicação deve propagar essa condição ao resultado e ao relatório.

O JSON de métricas recebe `timing` aditivo. `proxy_grant_wait_seconds` soma a espera real dos
pedidos liberados; `proxy_network_seconds` soma o tempo entre concessão e resposta ou erro no
proxy, incluindo DNS, conexão e processamento do servidor, não apenas latência de rede. Recusas
continuam separadas na contagem de tráfego. Soma de tempos concorrentes pode superar o tempo de
parede. Em auditorias antigas ou incompletas, valores não medidos ficam `null`, não zero.
`local_queue_seconds` soma, para cada trabalho, a espera desde o início do executor até começar
seu preparo, podendo sobrepor varreduras anteriores. `authentication_seconds` mede a ativação,
troca e renovação do Replacer e pode sobrepor a varredura. `zap_delay_seconds` só aparece quando
medido. CPU e memória referem-se ao processo CLI, não ao ZAP nem ao proxy; o pico de memória é
o pico residente histórico do processo, consultado no início e fim. `null` significa indisponível.

## Consequências

O formato aceita registros antigos. A mudança requer reconstruir a imagem do proxy e provar o
espaçamento real, cancelamento e bordas do prazo no laboratório. Não há alegação de ganho de
velocidade ou equivalência de cobertura até as provas previstas na V1.7.
