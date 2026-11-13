package dev.hdast.pilot.api;

import java.sql.Timestamp;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

/**
 * Utilidades de persistência comuns: ids, relógio e checagem de unicidade. Os nomes de
 * tabela e coluna recebidos são sempre constantes do código, nunca entrada do cliente.
 */
@Component
public class Persistence {

    private final JdbcClient jdbc;
    private final Clock clock;

    public Persistence(JdbcClient jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
    }

    public long nextId() {
        return jdbc.sql("SELECT SEQ_CLINICA.NEXTVAL FROM DUAL").query(Long.class).single();
    }

    /** Instante atual em UTC, no tipo que o banco guarda em CREATED_AT. */
    public Timestamp now() {
        return Timestamp.valueOf(LocalDateTime.ofInstant(clock.instant(), ZoneOffset.UTC));
    }

    public LocalDateTime nowLocal() {
        return LocalDateTime.ofInstant(clock.instant(), ZoneOffset.UTC);
    }

    /** 409 nomeando o campo se já existe outra linha com o valor. {@code ignoreId} permite atualizar a si mesmo. */
    public void ensureUnique(String table, String column, Object value, String field, Long ignoreId) {
        Long count = jdbc.sql("SELECT COUNT(*) FROM " + table + " WHERE " + column + " = :v AND ID <> :id")
                .param("v", value).param("id", ignoreId == null ? -1L : ignoreId).query(Long.class).single();
        if (count > 0) {
            throw ApiException.conflict(field, "Já existe um registro com este valor de '" + field + "'.");
        }
    }

    public boolean exists(String table, long id) {
        return jdbc.sql("SELECT COUNT(*) FROM " + table + " WHERE ID = :id").param("id", id)
                .query(Long.class).single() > 0;
    }

    /** 422 quando o corpo aponta para um registro inexistente. */
    public void requireReference(String table, Long id, String field, String label) {
        if (id == null || !exists(table, id)) {
            throw ApiException.unknownReference(field, label + " " + id + " não existe. Crie-o antes (ou use um id válido).");
        }
    }
}
