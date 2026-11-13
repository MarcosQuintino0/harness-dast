package dev.hdast.pilot.convenio;

import java.util.List;

import dev.hdast.pilot.api.ApiException;
import dev.hdast.pilot.api.Persistence;
import dev.hdast.pilot.auth.CurrentUser;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

@Service
public class ConvenioService {

    public enum TipoConvenio { INDIVIDUAL, EMPRESARIAL, PUBLICO }

    public record ConvenioRequest(
            @Schema(description = "Código do convênio: exatamente 8 dígitos, único")
            @NotBlank @Pattern(regexp = "\\d{8}", message = "deve ter exatamente 8 dígitos numéricos") String codigo,
            @NotBlank @Size(min = 3, max = 80) String nome,
            @NotNull TipoConvenio tipo,
            @Schema(description = "Percentual de coparticipação") @NotNull @Min(0) @Max(100)
            Integer coparticipacaoPercentual) {}

    public record ConvenioResponse(Long id, String codigo, String nome, TipoConvenio tipo,
                                   Integer coparticipacaoPercentual, boolean ativo) {}

    private static final String SELECT =
            "SELECT ID, CODIGO, NOME, TIPO, COPARTICIPACAO_PERCENTUAL, ATIVO FROM CONVENIO";

    private final JdbcClient jdbc;
    private final Persistence db;
    private final CurrentUser current;

    public ConvenioService(JdbcClient jdbc, Persistence db, CurrentUser current) {
        this.jdbc = jdbc;
        this.db = db;
        this.current = current;
    }

    public ConvenioResponse create(ConvenioRequest r) {
        db.ensureUnique("CONVENIO", "CODIGO", r.codigo(), "codigo", null);
        long id = db.nextId();
        jdbc.sql("INSERT INTO CONVENIO (ID, CODIGO, NOME, TIPO, COPARTICIPACAO_PERCENTUAL, ATIVO, CREATED_BY, CREATED_AT) "
                        + "VALUES (:id, :codigo, :nome, :tipo, :copart, 1, :by, :at)")
                .param("id", id).param("codigo", r.codigo()).param("nome", r.nome()).param("tipo", r.tipo().name())
                .param("copart", r.coparticipacaoPercentual()).param("by", current.username()).param("at", db.now())
                .update();
        return get(id);
    }

    public List<ConvenioResponse> list() {
        return jdbc.sql(SELECT + " ORDER BY ID").query(ConvenioService::map).list();
    }

    public ConvenioResponse get(long id) {
        return jdbc.sql(SELECT + " WHERE ID = :id").param("id", id).query(ConvenioService::map).optional()
                .orElseThrow(() -> ApiException.notFound("Convênio", id));
    }

    public ConvenioResponse update(long id, ConvenioRequest r) {
        get(id);
        db.ensureUnique("CONVENIO", "CODIGO", r.codigo(), "codigo", id);
        jdbc.sql("UPDATE CONVENIO SET CODIGO = :codigo, NOME = :nome, TIPO = :tipo, "
                        + "COPARTICIPACAO_PERCENTUAL = :copart WHERE ID = :id")
                .param("codigo", r.codigo()).param("nome", r.nome()).param("tipo", r.tipo().name())
                .param("copart", r.coparticipacaoPercentual()).param("id", id).update();
        return get(id);
    }

    public void delete(long id) {
        get(id);
        jdbc.sql("DELETE FROM CONVENIO WHERE ID = :id").param("id", id).update();
    }

    private static ConvenioResponse map(java.sql.ResultSet rs, int i) throws java.sql.SQLException {
        return new ConvenioResponse(rs.getLong("ID"), rs.getString("CODIGO"), rs.getString("NOME"),
                TipoConvenio.valueOf(rs.getString("TIPO")), rs.getInt("COPARTICIPACAO_PERCENTUAL"),
                rs.getInt("ATIVO") == 1);
    }
}
