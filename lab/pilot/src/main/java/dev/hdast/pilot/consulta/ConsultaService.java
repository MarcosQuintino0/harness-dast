package dev.hdast.pilot.consulta;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDateTime;
import java.util.List;

import dev.hdast.pilot.api.ApiException;
import dev.hdast.pilot.api.Persistence;
import dev.hdast.pilot.auth.AuthenticatedUser;
import dev.hdast.pilot.auth.CurrentUser;
import dev.hdast.pilot.config.Hardening;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

@Service
public class ConsultaService {

    public enum StatusConsulta { AGENDADA, REALIZADA, CANCELADA }

    public record ConsultaRequest(
            @Schema(description = "Id de um paciente existente") @NotNull @Positive Long pacienteId,
            @Schema(description = "Id de um médico existente") @NotNull @Positive Long medicoId,
            @Schema(description = "Data e hora da consulta (deve estar no futuro)") @NotNull @Future LocalDateTime dataHora,
            @NotBlank @Size(min = 5, max = 200) String motivo,
            @Schema(description = "Valor em reais, de 0 a 5000")
            @NotNull @DecimalMin("0.00") @DecimalMax("5000.00") @Digits(integer = 4, fraction = 2) BigDecimal valor) {}

    public record StatusRequest(@NotNull StatusConsulta status) {}

    public record ConsultaResponse(Long id, Long pacienteId, Long medicoId, LocalDateTime dataHora, String motivo,
                                   BigDecimal valor, StatusConsulta status) {}

    private static final String SELECT =
            "SELECT ID, PACIENTE_ID, MEDICO_ID, DATA_HORA, MOTIVO, VALOR, STATUS FROM CONSULTA";

    private final JdbcClient jdbc;
    private final Persistence db;
    private final CurrentUser current;
    private final Hardening hardening;

    public ConsultaService(JdbcClient jdbc, Persistence db, CurrentUser current, Hardening hardening) {
        this.jdbc = jdbc;
        this.db = db;
        this.current = current;
        this.hardening = hardening;
    }

    public ConsultaResponse create(ConsultaRequest r) {
        db.requireReference("PACIENTE", r.pacienteId(), "pacienteId", "Paciente");
        db.requireReference("MEDICO", r.medicoId(), "medicoId", "Médico");
        current.requireOwnerOrStaff(r.pacienteId());
        long id = db.nextId();
        jdbc.sql("INSERT INTO CONSULTA (ID, PACIENTE_ID, MEDICO_ID, DATA_HORA, MOTIVO, VALOR, STATUS, CREATED_BY, CREATED_AT) "
                        + "VALUES (:id, :pac, :med, :dh, :motivo, :valor, 'AGENDADA', :by, :at)")
                .param("id", id).param("pac", r.pacienteId()).param("med", r.medicoId())
                .param("dh", java.sql.Timestamp.valueOf(r.dataHora())).param("motivo", r.motivo())
                .param("valor", r.valor()).param("by", current.username()).param("at", db.now()).update();
        return find(id);
    }

    public List<ConsultaResponse> list() {
        AuthenticatedUser user = current.get();
        if (user.isStaff()) {
            return jdbc.sql(SELECT + " ORDER BY ID").query(ConsultaService::map).list();
        }
        return jdbc.sql(SELECT + " WHERE PACIENTE_ID = :pac ORDER BY ID")
                .param("pac", user.pacienteId() == null ? -1L : user.pacienteId()).query(ConsultaService::map).list();
    }

    public ConsultaResponse get(long id) {
        ConsultaResponse c = find(id);
        if (hardening.applies(Hardening.Item.H5)) {
            current.requireOwnerOrStaff(c.pacienteId());
        }
        return c;
    }

    /** Busca sem checar dono: para uso interno dos outros serviços, que checam por conta própria. */
    public ConsultaResponse find(long id) {
        return jdbc.sql(SELECT + " WHERE ID = :id").param("id", id).query(ConsultaService::map).optional()
                .orElseThrow(() -> ApiException.notFound("Consulta", id));
    }

    public ConsultaResponse updateStatus(long id, StatusConsulta novo) {
        ConsultaResponse c = find(id);
        current.requireOwnerOrStaff(c.pacienteId());
        if (c.status() != StatusConsulta.AGENDADA) {
            throw ApiException.conflictWithCode("TRANSICAO_INVALIDA",
                    "Consulta " + c.status() + " não pode mudar de status; só AGENDADA pode virar REALIZADA ou CANCELADA.");
        }
        if (novo == StatusConsulta.AGENDADA) {
            throw ApiException.conflictWithCode("TRANSICAO_INVALIDA", "Escolha REALIZADA ou CANCELADA.");
        }
        AuthenticatedUser user = current.get();
        if (!user.isStaff() && novo != StatusConsulta.CANCELADA) {
            throw ApiException.forbidden("Paciente só pode cancelar a própria consulta.");
        }
        jdbc.sql("UPDATE CONSULTA SET STATUS = :s WHERE ID = :id").param("s", novo.name()).param("id", id).update();
        return find(id);
    }

    private static ConsultaResponse map(ResultSet rs, int i) throws SQLException {
        return new ConsultaResponse(rs.getLong("ID"), rs.getLong("PACIENTE_ID"), rs.getLong("MEDICO_ID"),
                rs.getTimestamp("DATA_HORA").toLocalDateTime(), rs.getString("MOTIVO"), rs.getBigDecimal("VALOR"),
                StatusConsulta.valueOf(rs.getString("STATUS")));
    }
}
