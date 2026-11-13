package dev.hdast.pilot;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Roda o cleanup/cleanup.sql de verdade (H2 em modo Oracle) e confere que só o criado pelas contas de teste some. */
@SpringBootTest(properties = "pilot.vulnerable=true")
class CleanupScriptTest extends ApiTestBase {

    @Autowired NamedParameterJdbcTemplate named;
    @Autowired JdbcClient jdbc;

    @Test
    void cleanup_apagaSoLinhasDasContasDeTesteNaOrdemDasDependencias() throws Exception {
        String admin = login(ADMIN);
        long convenio = post(admin, "/api/convenios", convenioBody("90000030")).body().get("id").asLong();
        long paciente = post(admin, "/api/pacientes", pacienteBody("39053344705", "cl@example.test", convenio))
                .body().get("id").asLong();
        long consulta = post(login(MEDICO), "/api/consultas", consultaBody(paciente, 1)).body().get("id").asLong();
        post(login(MEDICO), "/api/receitas",
                Map.of("consultaId", consulta, "medicamento", "Dipirona", "posologia", "1", "duracaoDias", 5));
        // linha de outra conta (não é de teste): precisa sobreviver
        jdbc.sql("INSERT INTO CONVENIO VALUES (777, '77777777', 'Outro time', 'PUBLICO', 0, 1, 'outra.pessoa', :at)")
                .param("at", Timestamp.valueOf(LocalDateTime.now())).update();

        Map<String, Object> binds = Map.of("run_start", Timestamp.valueOf(LocalDateTime.now(java.time.ZoneOffset.UTC).minusMinutes(5)),
                "account_1", ADMIN, "account_2", MEDICO, "account_3", PACIENTE_A, "account_4", PACIENTE_B);
        for (String statement : Files.readString(Path.of("cleanup", "cleanup.sql")).split(";")) {
            String sql = statement.replaceAll("(?m)^\\s*--.*$", "").trim();
            if (!sql.isEmpty()) {
                named.update(sql, binds);
            }
        }

        assertThat(count("RECEITA", "CREATED_BY <> 'seed'")).isZero();
        assertThat(count("CONSULTA", "CREATED_BY <> 'seed'")).isZero();
        assertThat(count("PACIENTE", "ID = " + paciente)).isZero();
        assertThat(count("CONVENIO", "ID = " + convenio)).isZero();
        assertThat(count("CONVENIO", "CREATED_BY = 'outra.pessoa'")).isEqualTo(1);
        assertThat(count("PACIENTE", "CREATED_BY = 'seed'")).isEqualTo(2);
        assertThat(count("USUARIO", "1 = 1")).isEqualTo(4);
    }

    private long count(String table, String where) {
        return jdbc.sql("SELECT COUNT(*) FROM " + table + " WHERE " + where).query(Long.class).single();
    }
}
