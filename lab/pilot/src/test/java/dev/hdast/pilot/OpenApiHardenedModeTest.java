package dev.hdast.pilot;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

/** O contrato não pode denunciar o modo: o modo corrigido publica exatamente o mesmo openapi.json. */
@SpringBootTest(properties = "pilot.vulnerable=false")
class OpenApiHardenedModeTest extends ApiTestBase {

    @Test
    void openapi_identicoAoVersionadoTambemNoModoCorrigido() throws Exception {
        String generated = mvc.perform(MockMvcRequestBuilders.get("/v3/api-docs")).andReturn().getResponse()
                .getContentAsString(StandardCharsets.UTF_8);
        assertThat(json.readTree(generated))
                .isEqualTo(json.readTree(Files.readString(Path.of("openapi.json"), StandardCharsets.UTF_8)));
    }
}
