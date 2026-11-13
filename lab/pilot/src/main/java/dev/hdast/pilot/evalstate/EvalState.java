package dev.hdast.pilot.evalstate;

import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

/** Contadores para a avaliação: notificações, requisições por rota e linhas por tabela. */
@Component
public class EvalState {

    static final java.util.List<String> TABLES = java.util.List.of("CONVENIO", "MEDICO", "PACIENTE", "USUARIO", "CONSULTA", "RECEITA");
    private static final int MAX_UNROUTED = 200;

    private final JdbcClient jdbc;
    private final Clock clock;
    private final AtomicLong notificationsSent = new AtomicLong();
    private final Map<String, AtomicLong> requests = new ConcurrentHashMap<>();
    private volatile Instant since;

    public EvalState(JdbcClient jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
        this.since = clock.instant();
    }

    public long notificationSent() {
        return notificationsSent.incrementAndGet();
    }

    /** Conta a requisição pelo padrão de rota; sem rota (404/401/403), pelo caminho cru, com teto. */
    public void countRequest(String method, String routePattern, String rawPath) {
        String key = routePattern != null ? method + " " + routePattern : method + " (sem rota) " + rawPath;
        if (routePattern == null && requests.size() >= MAX_UNROUTED && !requests.containsKey(key)) {
            key = method + " (sem rota) <outros>";
        }
        requests.computeIfAbsent(key, k -> new AtomicLong()).incrementAndGet();
    }

    public Map<String, Object> snapshot(boolean vulnerableMode) {
        Map<String, Long> rows = new LinkedHashMap<>();
        Map<String, Long> created = new LinkedHashMap<>();
        for (String table : TABLES) { // nomes fixos da lista acima, nunca entrada externa
            rows.put(table.toLowerCase(), jdbc.sql("SELECT COUNT(*) FROM " + table).query(Long.class).single());
            created.put(table.toLowerCase(), jdbc.sql("SELECT COUNT(*) FROM " + table
                    + " WHERE CREATED_BY <> 'seed'").query(Long.class).single());
        }
        Map<String, Long> byEndpoint = new java.util.TreeMap<>();
        requests.forEach((k, v) -> byEndpoint.put(k, v.get()));
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("since", since.toString());
        out.put("hardening_applied", !vulnerableMode);
        out.put("notifications_sent", notificationsSent.get());
        out.put("requests_total", byEndpoint.values().stream().mapToLong(Long::longValue).sum());
        out.put("requests_by_endpoint", byEndpoint);
        out.put("rows", rows);
        out.put("rows_created_since_startup", created);
        out.put("rows_created_total", created.values().stream().mapToLong(Long::longValue).sum());
        return out;
    }

    public void resetCounters() {
        notificationsSent.set(0);
        requests.clear();
        since = clock.instant();
    }
}
