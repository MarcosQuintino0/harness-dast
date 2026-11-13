package dev.hdast.pilot.medico;

import java.util.List;

import dev.hdast.pilot.api.ApiException;
import dev.hdast.pilot.api.Persistence;
import dev.hdast.pilot.auth.CurrentUser;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

@Service
public class MedicoService {

    public enum Especialidade { CLINICA_GERAL, CARDIOLOGIA, PEDIATRIA, DERMATOLOGIA }

    public record MedicoRequest(
            @NotBlank @Size(min = 3, max = 100) String nome,
            @Schema(description = "CRM no formato NNNNN-UF, único")
            @NotBlank @Pattern(regexp = "\\d{4,7}-[A-Z]{2}", message = "deve seguir o formato NNNNN-UF (ex.: 12345-SP)")
            String crm,
            @NotNull Especialidade especialidade) {}

    public record MedicoResponse(Long id, String nome, String crm, Especialidade especialidade) {}

    private static final String SELECT = "SELECT ID, NOME, CRM, ESPECIALIDADE FROM MEDICO";

    private final JdbcClient jdbc;
    private final Persistence db;
    private final CurrentUser current;

    public MedicoService(JdbcClient jdbc, Persistence db, CurrentUser current) {
        this.jdbc = jdbc;
        this.db = db;
        this.current = current;
    }

    public MedicoResponse create(MedicoRequest r) {
        db.ensureUnique("MEDICO", "CRM", r.crm(), "crm", null);
        long id = db.nextId();
        jdbc.sql("INSERT INTO MEDICO (ID, NOME, CRM, ESPECIALIDADE, CREATED_BY, CREATED_AT) "
                        + "VALUES (:id, :nome, :crm, :esp, :by, :at)")
                .param("id", id).param("nome", r.nome()).param("crm", r.crm()).param("esp", r.especialidade().name())
                .param("by", current.username()).param("at", db.now()).update();
        return get(id);
    }

    public List<MedicoResponse> list() {
        return jdbc.sql(SELECT + " ORDER BY ID").query(MedicoService::map).list();
    }

    public MedicoResponse get(long id) {
        return jdbc.sql(SELECT + " WHERE ID = :id").param("id", id).query(MedicoService::map).optional()
                .orElseThrow(() -> ApiException.notFound("Médico", id));
    }

    private static MedicoResponse map(java.sql.ResultSet rs, int i) throws java.sql.SQLException {
        return new MedicoResponse(rs.getLong("ID"), rs.getString("NOME"), rs.getString("CRM"),
                Especialidade.valueOf(rs.getString("ESPECIALIDADE")));
    }
}
