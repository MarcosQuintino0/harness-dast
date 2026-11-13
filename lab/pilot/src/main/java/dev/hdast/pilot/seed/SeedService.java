package dev.hdast.pilot.seed;

import java.sql.Date;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

import dev.hdast.pilot.api.Persistence;
import dev.hdast.pilot.auth.LoginRateLimiter;
import dev.hdast.pilot.auth.Papel;
import dev.hdast.pilot.auth.UsuarioService;
import dev.hdast.pilot.config.PilotProperties;
import dev.hdast.pilot.evalstate.EvalState;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Estado inicial: um convênio, dois médicos, dois pacientes (com conta), uma consulta e uma receita cada. */
@Service
public class SeedService implements ApplicationRunner {

    public static final String SEED = "seed";
    private static final List<String> DELETE_ORDER =
            List.of("RECEITA", "CONSULTA", "USUARIO", "PACIENTE", "MEDICO", "CONVENIO");

    private final JdbcClient jdbc;
    private final Persistence db;
    private final UsuarioService usuarios;
    private final PasswordEncoder encoder;
    private final PilotProperties props;
    private final EvalState state;
    private final LoginRateLimiter limiter;

    public SeedService(JdbcClient jdbc, Persistence db, UsuarioService usuarios, PasswordEncoder encoder,
                       PilotProperties props, EvalState state, LoginRateLimiter limiter) {
        this.jdbc = jdbc;
        this.db = db;
        this.usuarios = usuarios;
        this.encoder = encoder;
        this.props = props;
        this.state = state;
        this.limiter = limiter;
    }

    @Override
    public void run(ApplicationArguments args) {
        reset(); // com banco persistente (Oracle) a subida também volta ao estado de semente
    }

    /** Apaga tudo e semeia de novo. Os ids de seed são fixos (< 1000). */
    @Transactional
    public void reset() {
        DELETE_ORDER.forEach(table -> jdbc.sql("DELETE FROM " + table).update()); // nomes fixos acima
        seed();
        limiter.reset();
        state.resetCounters();
    }

    @Transactional
    public void seed() {
        Timestamp at = db.now();
        jdbc.sql("INSERT INTO CONVENIO (ID, CODIGO, NOME, TIPO, COPARTICIPACAO_PERCENTUAL, ATIVO, CREATED_BY, CREATED_AT) "
                + "VALUES (1, '00000001', 'Plano Exemplo Saúde', 'EMPRESARIAL', 20, 1, :by, :at)")
                .param("by", SEED).param("at", at).update();
        medico(1, "Dra. Helena Exemplo", "12345-SP", "CLINICA_GERAL", at);
        medico(2, "Dr. Rui Exemplo", "23456-RJ", "CARDIOLOGIA", at);
        paciente(1, "Paciente Exemplo A", "52998224725", "paciente.a@example.test", LocalDate.of(1985, 3, 14), at);
        paciente(2, "Paciente Exemplo B", "11144477735", "paciente.b@example.test", LocalDate.of(1992, 11, 2), at);
        consulta(1, 1, 1, "Check-up anual", at);
        consulta(2, 2, 2, "Avaliação cardiológica", at);
        receita(1, 1, "Vitamina D 2000 UI", at);
        receita(2, 2, "Losartana 50 mg", at);

        PilotProperties.Accounts a = props.accounts();
        usuarios.insert(1, a.admin().username(), encoder.encode(a.admin().password()), Papel.ADMIN,
                "Administrador Exemplo", null, null, SEED);
        usuarios.insert(2, a.medico().username(), encoder.encode(a.medico().password()), Papel.MEDICO,
                "Dra. Helena Exemplo", null, 1L, SEED);
        usuarios.insert(3, a.pacienteA().username(), encoder.encode(a.pacienteA().password()), Papel.PACIENTE,
                "Paciente Exemplo A", 1L, null, SEED);
        usuarios.insert(4, a.pacienteB().username(), encoder.encode(a.pacienteB().password()), Papel.PACIENTE,
                "Paciente Exemplo B", 2L, null, SEED);
    }

    private void medico(long id, String nome, String crm, String especialidade, Timestamp at) {
        jdbc.sql("INSERT INTO MEDICO (ID, NOME, CRM, ESPECIALIDADE, CREATED_BY, CREATED_AT) "
                + "VALUES (:id, :nome, :crm, :esp, :by, :at)")
                .param("id", id).param("nome", nome).param("crm", crm).param("esp", especialidade)
                .param("by", SEED).param("at", at).update();
    }

    private void paciente(long id, String nome, String cpf, String email, LocalDate nascimento, Timestamp at) {
        jdbc.sql("INSERT INTO PACIENTE (ID, NOME, CPF, EMAIL, DATA_NASCIMENTO, SEXO, TELEFONE, CONVENIO_ID, "
                + "NOTAS_INTERNAS, CREATED_BY, CREATED_AT) VALUES (:id, :nome, :cpf, :email, :nasc, 'NAO_INFORMADO', "
                + "'11999990000', 1, 'Nota interna: prefere contato por e-mail.', :by, :at)")
                .param("id", id).param("nome", nome).param("cpf", cpf).param("email", email)
                .param("nasc", Date.valueOf(nascimento)).param("by", SEED).param("at", at).update();
    }

    private void consulta(long id, long pacienteId, long medicoId, String motivo, Timestamp at) {
        jdbc.sql("INSERT INTO CONSULTA (ID, PACIENTE_ID, MEDICO_ID, DATA_HORA, MOTIVO, VALOR, STATUS, CREATED_BY, CREATED_AT) "
                + "VALUES (:id, :pac, :med, :dh, :motivo, 250.00, 'AGENDADA', :by, :at)")
                .param("id", id).param("pac", pacienteId).param("med", medicoId)
                .param("dh", Timestamp.valueOf(LocalDateTime.of(2030, 1, 15, 9, 0))).param("motivo", motivo)
                .param("by", SEED).param("at", at).update();
    }

    private void receita(long id, long consultaId, String medicamento, Timestamp at) {
        jdbc.sql("INSERT INTO RECEITA (ID, CONSULTA_ID, MEDICAMENTO, POSOLOGIA, DURACAO_DIAS, CREATED_BY, CREATED_AT) "
                + "VALUES (:id, :cons, :med, '1 comprimido ao dia', 30, :by, :at)")
                .param("id", id).param("cons", consultaId).param("med", medicamento)
                .param("by", SEED).param("at", at).update();
    }
}
