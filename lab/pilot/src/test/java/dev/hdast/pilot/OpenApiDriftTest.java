package dev.hdast.pilot;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

/**
 * Falha se o openapi.json versionado divergir do que a aplicação gera. Para regenerar o arquivo:
 * ver "Regenerar o openapi.json" em lab/pilot/README.md (variável PILOT_OPENAPI_OUT).
 */
@SpringBootTest(properties = "pilot.vulnerable=true")
class OpenApiDriftTest extends ApiTestBase {

    @Test
    void openapiVersionado_igualAoGeradoPelaAplicacao() throws Exception {
        String generated = mvc.perform(MockMvcRequestBuilders.get("/v3/api-docs")).andReturn().getResponse()
                .getContentAsString(StandardCharsets.UTF_8);
        String out = System.getenv("PILOT_OPENAPI_OUT");
        if (out != null && !out.isBlank()) {
            Files.writeString(Path.of(out), generated, StandardCharsets.UTF_8);
            return;
        }
        JsonNode versioned = json.readTree(Files.readString(Path.of("openapi.json"), StandardCharsets.UTF_8));
        assertThat(json.readTree(generated))
                .as("openapi.json divergiu do /v3/api-docs gerado. Regenere (README, seção OpenAPI) e revise o diff.")
                .isEqualTo(versioned);
    }
}
