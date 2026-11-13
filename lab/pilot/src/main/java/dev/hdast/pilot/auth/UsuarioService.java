package dev.hdast.pilot.auth;

import java.sql.Timestamp;
import java.sql.Types;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Optional;

import dev.hdast.pilot.config.Hardening;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

@Service
public class UsuarioService {

    public record Credentials(AuthenticatedUser user, String passwordHash) {}

    public record Perfil(String nome, String telefone) {}

    private final JdbcClient jdbc;
    private final Hardening hardening;
    private final Clock clock;

    public UsuarioService(JdbcClient jdbc, Hardening hardening, Clock clock) {
        this.jdbc = jdbc;
        this.hardening = hardening;
        this.clock = clock;
    }

    public Optional<Credentials> findCredentials(String username) {
        return jdbc.sql("SELECT ID, USERNAME, PASSWORD_HASH, PAPEL, PACIENTE_ID, MEDICO_ID FROM USUARIO WHERE USERNAME = :u")
                .param("u", username)
                .query((rs, i) -> new Credentials(new AuthenticatedUser(rs.getLong("ID"), rs.getString("USERNAME"),
                        Papel.from(rs.getString("PAPEL")), nullableLong(rs.getObject("PACIENTE_ID")),
                        nullableLong(rs.getObject("MEDICO_ID"))), rs.getString("PASSWORD_HASH")))
                .optional();
    }

    public Perfil perfil(long id) {
        return jdbc.sql("SELECT NOME_EXIBICAO, TELEFONE FROM USUARIO WHERE ID = :id").param("id", id)
                .query((rs, i) -> new Perfil(rs.getString(1), rs.getString(2))).single();
    }

    public void updatePerfil(long id, String nome, String telefone, Papel requestedRole) {
        jdbc.sql("UPDATE USUARIO SET NOME_EXIBICAO = COALESCE(:nome, NOME_EXIBICAO), "
                        + "TELEFONE = COALESCE(:tel, TELEFONE) WHERE ID = :id")
                .param("nome", nome, Types.VARCHAR).param("tel", telefone, Types.VARCHAR).param("id", id).update();
        if (requestedRole != null && !hardening.applies(Hardening.Item.H6)) {
            jdbc.sql("UPDATE USUARIO SET PAPEL = :papel WHERE ID = :id").param("papel", requestedRole.value())
                    .param("id", id).update();
        }
    }

    public void insert(long id, String username, String hash, Papel papel, String nome, Long pacienteId,
                       Long medicoId, String createdBy) {
        jdbc.sql("INSERT INTO USUARIO (ID, USERNAME, PASSWORD_HASH, PAPEL, NOME_EXIBICAO, PACIENTE_ID, MEDICO_ID, "
                        + "CREATED_BY, CREATED_AT) VALUES (:id, :u, :h, :p, :n, :pac, :med, :by, :at)")
                .param("id", id).param("u", username).param("h", hash).param("p", papel.value()).param("n", nome, Types.VARCHAR)
                .param("pac", pacienteId, Types.NUMERIC).param("med", medicoId, Types.NUMERIC).param("by", createdBy)
                .param("at", Timestamp.valueOf(LocalDateTime.ofInstant(clock.instant(), ZoneOffset.UTC))).update();
    }

    private static Long nullableLong(Object o) {
        return o == null ? null : ((Number) o).longValue();
    }
}
