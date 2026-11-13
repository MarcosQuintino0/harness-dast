package dev.hdast.pilot;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {"pilot.jwt-ttl-seconds=1", "pilot.vulnerable=true"})
class TokenExpiryTest extends ApiTestBase {

    @Test
    void token_expiradoDevolve401ComCodigoProprio() throws Exception {
        String token = login(ADMIN);
        assertThat(get(token, "/api/me").status()).isEqualTo(200);
        Thread.sleep(2200);
        Reply r = get(token, "/api/me");
        assertThat(r.status()).isEqualTo(401);
        assertThat(r.body().get("code").asText()).isEqualTo("TOKEN_EXPIRADO");
    }
}
