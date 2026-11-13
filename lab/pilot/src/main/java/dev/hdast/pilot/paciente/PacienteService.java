package dev.hdast.pilot.paciente;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import dev.hdast.pilot.api.ApiException;
import dev.hdast.pilot.api.Persistence;
import dev.hdast.pilot.auth.AuthenticatedUser;
import dev.hdast.pilot.auth.CurrentUser;
import dev.hdast.pilot.config.Hardening;
import dev.hdast.pilot.validation.Cpf;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

@Service
public class PacienteService {

    public enum Sexo { FEMININO, MASCULINO, OUTRO, NAO_INFORMADO }

    public record PacienteRequest(
            @NotBlank @Size(min = 3, max = 100) String nome,
            @Schema(description = "CPF só com dígitos, com dígitos verificadores válidos; único")
            @NotBlank @Pattern(regexp = "\\d{11}", message = "deve ter 11 dígitos numéricos") @Cpf String cpf,
            @Schema(description = "E-mail único") @NotBlank @Email @Size(max = 120) String email,
            @Schema(description = "Data de nascimento (deve estar no passado)") @NotNull @Past LocalDate dataNascimento,
            @NotNull Sexo sexo,
            @Schema(description = "Telefone com DDD, só dígitos") @Pattern(regexp = "\\d{10,11}") String telefone,
            @Schema(description = "Id de um convênio existente") @NotNull @Positive Long convenioId) {}

    public record PacienteResponse(Long id, String nome, String cpf, String email, LocalDate dataNascimento,
                                   Sexo sexo, String telefone, Long convenioId) {}

    public record Pagina(List<PacienteResumo> items, int page, int size, long total) {}

    private static final String COLUMNS =
            "ID, NOME, CPF, EMAIL, DATA_NASCIMENTO, SEXO, TELEFONE, CONVENIO_ID";

    private final JdbcClient jdbc;
    private final JdbcTemplate template;
    private final Persistence db;
    private final CurrentUser current;
    private final Hardening hardening;

    public PacienteService(JdbcClient jdbc, JdbcTemplate template, Persistence db, CurrentUser current,
                           Hardening hardening) {
        this.jdbc = jdbc;
        this.template = template;
        this.db = db;
        this.current = current;
        this.hardening = hardening;
    }

    public PacienteResponse create(PacienteRequest r) {
        db.requireReference("CONVENIO", r.convenioId(), "convenioId", "Convênio");
        db.ensureUnique("PACIENTE", "CPF", r.cpf(), "cpf", null);
        db.ensureUnique("PACIENTE", "EMAIL", r.email(), "email", null);
        long id = db.nextId();
        jdbc.sql("INSERT INTO PACIENTE (ID, NOME, CPF, EMAIL, DATA_NASCIMENTO, SEXO, TELEFONE, CONVENIO_ID, "
                        + "NOTAS_INTERNAS, CREATED_BY, CREATED_AT) VALUES (:id, :nome, :cpf, :email, :nasc, :sexo, "
                        + ":tel, :conv, :notas, :by, :at)")
                .param("id", id).param("nome", r.nome()).param("cpf", r.cpf()).param("email", r.email())
                .param("nasc", java.sql.Date.valueOf(r.dataNascimento())).param("sexo", r.sexo().name())
                .param("tel", r.telefone(), java.sql.Types.VARCHAR).param("conv", r.convenioId())
                .param("notas", "Nota interna: cadastro realizado pela API.").param("by", current.username())
                .param("at", db.now()).update();
        return get(id);
    }

    public PacienteResponse get(long id) {
        return jdbc.sql("SELECT " + COLUMNS + " FROM PACIENTE WHERE ID = :id").param("id", id)
                .query(PacienteService::map).optional().orElseThrow(() -> ApiException.notFound("Paciente", id));
    }

    public PacienteResponse getAuthorized(long id) {
        PacienteResponse p = get(id);
        current.requireOwnerOrStaff(id);
        return p;
    }

    public PacienteResponse update(long id, PacienteRequest r) {
        get(id);
        current.requireOwnerOrStaff(id);
        db.requireReference("CONVENIO", r.convenioId(), "convenioId", "Convênio");
        db.ensureUnique("PACIENTE", "CPF", r.cpf(), "cpf", id);
        db.ensureUnique("PACIENTE", "EMAIL", r.email(), "email", id);
        jdbc.sql("UPDATE PACIENTE SET NOME = :nome, CPF = :cpf, EMAIL = :email, DATA_NASCIMENTO = :nasc, "
                        + "SEXO = :sexo, TELEFONE = :tel, CONVENIO_ID = :conv WHERE ID = :id")
                .param("nome", r.nome()).param("cpf", r.cpf()).param("email", r.email())
                .param("nasc", java.sql.Date.valueOf(r.dataNascimento())).param("sexo", r.sexo().name())
                .param("tel", r.telefone(), java.sql.Types.VARCHAR).param("conv", r.convenioId()).param("id", id).update();
        return get(id);
    }

    public void delete(long id) {
        get(id);
        jdbc.sql("DELETE FROM PACIENTE WHERE ID = :id").param("id", id).update();
    }

    public Pagina list(int page, int size) {
        AuthenticatedUser user = current.get();
        String where = user.isStaff() ? "" : " WHERE p.ID = " + (user.pacienteId() == null ? -1 : user.pacienteId());
        long total = jdbc.sql("SELECT COUNT(*) FROM PACIENTE p" + where).query(Long.class).single();
        boolean expose = !hardening.applies(Hardening.Item.H7);
        List<PacienteResumo> items = jdbc.sql("SELECT p.ID, p.NOME, p.CPF, p.EMAIL, p.CONVENIO_ID, p.NOTAS_INTERNAS, "
                        + "(SELECT MAX(u.PASSWORD_HASH) FROM USUARIO u WHERE u.PACIENTE_ID = p.ID) AS HASH "
                        + "FROM PACIENTE p" + where + " ORDER BY p.ID OFFSET :off ROWS FETCH NEXT :size ROWS ONLY")
                .param("off", (long) page * size).param("size", size)
                .query((rs, i) -> resumo(rs, expose)).list();
        return new Pagina(items, page, size, total);
    }

    public List<PacienteResponse> search(String nome) {
        if (hardening.applies(Hardening.Item.H1)) {
            return jdbc.sql("SELECT " + COLUMNS + " FROM PACIENTE WHERE UPPER(NOME) LIKE UPPER(:pattern) ORDER BY NOME")
                    .param("pattern", "%" + nome + "%").query(PacienteService::map).list();
        }
        String sql = "SELECT " + COLUMNS + " FROM PACIENTE WHERE UPPER(NOME) LIKE '%" + nome.toUpperCase() + "%' ORDER BY NOME";
        return template.query(sql, PacienteService::map);
    }

    private static PacienteResumo resumo(ResultSet rs, boolean expose) throws SQLException {
        Map<String, Object> extras = new LinkedHashMap<>();
        if (expose) {
            extras.put("notasInternas", rs.getString("NOTAS_INTERNAS"));
            extras.put("senhaHash", rs.getString("HASH"));
        }
        return new PacienteResumo(rs.getLong("ID"), rs.getString("NOME"), rs.getString("CPF"), rs.getString("EMAIL"),
                rs.getLong("CONVENIO_ID"), extras);
    }

    private static PacienteResponse map(ResultSet rs, int i) throws SQLException {
        return new PacienteResponse(rs.getLong(1), rs.getString(2), rs.getString(3), rs.getString(4),
                rs.getDate(5).toLocalDate(), Sexo.valueOf(rs.getString(6)), rs.getString(7), rs.getLong(8));
    }
}
