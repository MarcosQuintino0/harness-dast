package dev.hdast.pilot.receita;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;

import dev.hdast.pilot.api.ApiException;
import dev.hdast.pilot.api.Persistence;
import dev.hdast.pilot.auth.CurrentUser;
import dev.hdast.pilot.consulta.ConsultaService;
import dev.hdast.pilot.consulta.ConsultaService.ConsultaResponse;
import dev.hdast.pilot.consulta.ConsultaService.StatusConsulta;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

@Service
public class ReceitaService {

    public record ReceitaRequest(
            @Schema(description = "Id de uma consulta existente e não cancelada") @NotNull @Positive Long consultaId,
            @NotBlank @Size(min = 2, max = 100) String medicamento,
            @NotBlank @Size(max = 200) String posologia,
            @Schema(description = "Duração do tratamento em dias, de 1 a 365") @NotNull @Min(1) @Max(365)
            Integer duracaoDias) {}

    public record ReceitaResponse(Long id, Long consultaId, String medicamento, String posologia, Integer duracaoDias) {}

    private static final String SELECT = "SELECT ID, CONSULTA_ID, MEDICAMENTO, POSOLOGIA, DURACAO_DIAS FROM RECEITA";

    private final JdbcClient jdbc;
    private final Persistence db;
    private final CurrentUser current;
    private final ConsultaService consultas;

    public ReceitaService(JdbcClient jdbc, Persistence db, CurrentUser current, ConsultaService consultas) {
        this.jdbc = jdbc;
        this.db = db;
        this.current = current;
        this.consultas = consultas;
    }

    public ReceitaResponse create(ReceitaRequest r) {
        db.requireReference("CONSULTA", r.consultaId(), "consultaId", "Consulta");
        if (consultas.find(r.consultaId()).status() == StatusConsulta.CANCELADA) {
            throw ApiException.conflictWithCode("CONSULTA_CANCELADA", "Não é possível prescrever em consulta cancelada.");
        }
        long id = db.nextId();
        jdbc.sql("INSERT INTO RECEITA (ID, CONSULTA_ID, MEDICAMENTO, POSOLOGIA, DURACAO_DIAS, CREATED_BY, CREATED_AT) "
                        + "VALUES (:id, :cons, :med, :pos, :dias, :by, :at)")
                .param("id", id).param("cons", r.consultaId()).param("med", r.medicamento())
                .param("pos", r.posologia()).param("dias", r.duracaoDias()).param("by", current.username())
                .param("at", db.now()).update();
        return jdbc.sql(SELECT + " WHERE ID = :id").param("id", id).query(ReceitaService::map).single();
    }

    public ReceitaResponse get(long id) {
        ReceitaResponse r = jdbc.sql(SELECT + " WHERE ID = :id").param("id", id).query(ReceitaService::map)
                .optional().orElseThrow(() -> ApiException.notFound("Receita", id));
        current.requireOwnerOrStaff(consultas.find(r.consultaId()).pacienteId());
        return r;
    }

    public List<ReceitaResponse> listByConsulta(long consultaId) {
        ConsultaResponse c = consultas.find(consultaId);
        current.requireOwnerOrStaff(c.pacienteId());
        return jdbc.sql(SELECT + " WHERE CONSULTA_ID = :c ORDER BY ID").param("c", consultaId)
                .query(ReceitaService::map).list();
    }

    private static ReceitaResponse map(ResultSet rs, int i) throws SQLException {
        return new ReceitaResponse(rs.getLong("ID"), rs.getLong("CONSULTA_ID"), rs.getString("MEDICAMENTO"),
                rs.getString("POSOLOGIA"), rs.getInt("DURACAO_DIAS"));
    }
}
