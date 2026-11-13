package dev.hdast.pilot;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

@SpringBootTest(properties = {"pilot.login-max-per-minute=3", "pilot.vulnerable=true"})
class LoginRateLimitTest extends ApiTestBase {

    private Reply attempt(String password) throws Exception {
        return send(MockMvcRequestBuilders.post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("username", ADMIN, "password", password))));
    }

    @Test
    void login_devolve429ComRetryAfterDepoisDoLimiteMesmoComSenhaCerta() throws Exception {
        assertThat(attempt("errada-1").status()).isEqualTo(401);
        assertThat(attempt("errada-2").status()).isEqualTo(401);
        assertThat(attempt(PASSWORDS.get(ADMIN)).status()).isEqualTo(200);
        Reply blocked = attempt(PASSWORDS.get(ADMIN));
        assertThat(blocked.status()).isEqualTo(429);
        assertThat(blocked.body().get("code").asText()).isEqualTo("LIMITE_EXCEDIDO");
        assertThat(Long.parseLong(blocked.header("Retry-After"))).isBetween(1L, 61L);
    }

    @Test
    void reset_liberaOLogin() throws Exception {
        for (int i = 0; i < 4; i++) {
            attempt("errada");
        }
        assertThat(attempt(PASSWORDS.get(ADMIN)).status()).isEqualTo(429);
        seed.reset();
        assertThat(attempt(PASSWORDS.get(ADMIN)).status()).isEqualTo(200);
    }
}
