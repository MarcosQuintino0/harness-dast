package dev.hdast.pilot;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.hdast.pilot.seed.SeedService;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

/**
 * Base dos testes de integração: sobe o app inteiro (H2 em modo Oracle) com MockMvc. Senhas de teste são
 * sorteadas a cada execução: nada de segredo fixo no repositório. O modo (padrão/corrigido) é escolhido
 * pela subclasse com {@code @SpringBootTest(properties = "pilot.vulnerable=...")}.
 */
@SpringBootTest
@AutoConfigureMockMvc
public abstract class ApiTestBase {

    protected static final String ADMIN = "t_admin";
    protected static final String MEDICO = "t_medico";
    protected static final String PACIENTE_A = "t_paciente_a";
    protected static final String PACIENTE_B = "t_paciente_b";
    protected static final Map<String, String> PASSWORDS = Map.of(
            ADMIN, UUID.randomUUID().toString(), MEDICO, UUID.randomUUID().toString(),
            PACIENTE_A, UUID.randomUUID().toString(), PACIENTE_B, UUID.randomUUID().toString());
    protected static final Path RUN_DIR = Path.of("target", "test-run");
    protected static final String BUILD_INFO_MARKER = "TEST-BUILD-INFO-MARKER";

    @Autowired protected MockMvc mvc;
    @Autowired protected ObjectMapper json;
    @Autowired protected SeedService seed;

    @DynamicPropertySource
    static void baseProperties(DynamicPropertyRegistry r) throws IOException {
        Files.createDirectories(RUN_DIR.resolve("documentos"));
        Files.writeString(RUN_DIR.resolve("documentos").resolve("laudo.txt"), "laudo fictício", StandardCharsets.UTF_8);
        Files.writeString(RUN_DIR.resolve("build-info.txt"), BUILD_INFO_MARKER, StandardCharsets.UTF_8);
        r.add("pilot.documents-dir", () -> RUN_DIR.resolve("documentos").toString());
        r.add("spring.datasource.url", () -> "jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=Oracle;DATABASE_TO_LOWER=FALSE;DB_CLOSE_DELAY=-1");
        r.add("pilot.accounts.admin.username", () -> ADMIN);
        r.add("pilot.accounts.admin.password", () -> PASSWORDS.get(ADMIN));
        r.add("pilot.accounts.medico.username", () -> MEDICO);
        r.add("pilot.accounts.medico.password", () -> PASSWORDS.get(MEDICO));
        r.add("pilot.accounts.paciente-a.username", () -> PACIENTE_A);
        r.add("pilot.accounts.paciente-a.password", () -> PASSWORDS.get(PACIENTE_A));
        r.add("pilot.accounts.paciente-b.username", () -> PACIENTE_B);
        r.add("pilot.accounts.paciente-b.password", () -> PASSWORDS.get(PACIENTE_B));
    }

    @BeforeEach
    void resetToSeed() {
        seed.reset();
    }

    /** Resposta já lida: status, corpo JSON e cabeçalhos. */
    protected record Reply(int status, JsonNode body, MvcResult raw) {
        String header(String name) { return raw.getResponse().getHeader(name); }
    }

    protected String login(String username) throws Exception {
        Reply r = send(MockMvcRequestBuilders.post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("username", username, "password", PASSWORDS.get(username)))));
        if (r.status() != 200) {
            throw new IllegalStateException("login falhou: " + r.status() + " " + r.body());
        }
        return r.body().get("access_token").asText();
    }

    protected String xsrfToken() throws Exception {
        MvcResult res = mvc.perform(MockMvcRequestBuilders.get("/api/csrf")).andReturn();
        Cookie cookie = res.getResponse().getCookie("XSRF-TOKEN");
        if (cookie == null) {
            throw new IllegalStateException("GET /api/csrf não definiu o cookie XSRF-TOKEN");
        }
        return cookie.getValue();
    }

    protected Reply send(MockHttpServletRequestBuilder request) throws Exception {
        MvcResult res = mvc.perform(request).andReturn();
        String text = res.getResponse().getContentAsString(StandardCharsets.UTF_8);
        JsonNode body = text.isBlank() || !text.trim().startsWith("{") && !text.trim().startsWith("[")
                ? json.nullNode() : json.readTree(text);
        return new Reply(res.getResponse().getStatus(), body, res);
    }

    /** Busca por nome com o valor cru no parâmetro (o MockMvc codifica; não pré-codifique). */
    protected Reply search(String token, String nome) throws Exception {
        return send(MockMvcRequestBuilders.get("/api/pacientes/busca").param("nome", nome)
                .header("Authorization", "Bearer " + token));
    }

    protected Reply get(String token, String path) throws Exception {
        MockHttpServletRequestBuilder b = MockMvcRequestBuilders.get(path);
        if (token != null) {
            b.header("Authorization", "Bearer " + token);
        }
        return send(b);
    }

    /** Escrita completa: Bearer + par XSRF (cookie e cabeçalho). */
    protected Reply write(String method, String token, String path, Object body) throws Exception {
        String xsrf = xsrfToken();
        MockHttpServletRequestBuilder b = MockMvcRequestBuilders.request(org.springframework.http.HttpMethod.valueOf(method), path)
                .cookie(new Cookie("XSRF-TOKEN", xsrf)).header("X-XSRF-TOKEN", xsrf)
                .contentType(MediaType.APPLICATION_JSON);
        if (token != null) {
            b.header("Authorization", "Bearer " + token);
        }
        if (body != null) {
            b.content(body instanceof String s ? s : json.writeValueAsString(body));
        }
        return send(b);
    }

    protected Reply post(String token, String path, Object body) throws Exception {
        return write("POST", token, path, body);
    }

    // ---- massas de dados válidas ------------------------------------------------------------------

    protected static Map<String, Object> convenioBody(String codigo) {
        return Map.of("codigo", codigo, "nome", "Plano de Teste", "tipo", "INDIVIDUAL", "coparticipacaoPercentual", 10);
    }

    protected static Map<String, Object> pacienteBody(String cpf, String email, long convenioId) {
        return Map.of("nome", "Paciente de Teste", "cpf", cpf, "email", email, "dataNascimento", "1990-05-20",
                "sexo", "FEMININO", "telefone", "11988887777", "convenioId", convenioId);
    }

    protected static Map<String, Object> consultaBody(long pacienteId, long medicoId) {
        return Map.of("pacienteId", pacienteId, "medicoId", medicoId, "dataHora", "2031-06-01T10:30:00",
                "motivo", "Consulta de rotina", "valor", 300.50);
    }
}
