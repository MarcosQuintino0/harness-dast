package dev.hdast.pilot;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

import dev.hdast.pilot.convenio.ConvenioService;

import static org.mockito.Mockito.when;

/** Modo padrão do laboratório (PILOT_VULNERABLE=1): cada item H1..H7 é explorável com uma requisição mínima. */
@SpringBootTest(properties = "pilot.vulnerable=true")
class WeaknessesVulnerableModeTest extends ApiTestBase {

    @MockitoBean ConvenioService convenios; // só para provocar uma falha interna sem depender do banco (H2)

    @Test
    void h1_filtroDeBuscaAceitaSqlEDevolveTodasAsLinhas() throws Exception {
        Reply r = search(login(ADMIN), "zzz' OR 1=1 --");
        assertThat(r.status()).isEqualTo(200);
        assertThat(r.body()).hasSize(2);
    }

    @Test
    void h2_erroInternoRevelaDetalhesEPilha() throws Exception {
        Reply r = search(login(ADMIN), "'");
        assertThat(r.status()).isEqualTo(500);
        assertThat(r.body().get("trace").asText()).contains("dev.hdast.pilot");
        assertThat(r.body().get("detail").asText()).containsIgnoringCase("SELECT");
        when(convenios.list()).thenThrow(new IllegalStateException("falha interna simulada"));
        Reply mocked = get(login(ADMIN), "/api/convenios");
        assertThat(mocked.status()).isEqualTo(500);
        assertThat(mocked.body().has("trace")).isTrue();
    }

    @Test
    void h3_semCabecalhosDeSegurancaECorsPermissivo() throws Exception {
        Reply r = send(MockMvcRequestBuilders.get("/api/saude").header("Origin", "http://origem-qualquer.example"));
        assertThat(r.header("X-Content-Type-Options")).isNull();
        assertThat(r.header("Content-Security-Policy")).isNull();
        assertThat(r.header("Access-Control-Allow-Origin")).isEqualTo("http://origem-qualquer.example");
        assertThat(r.header("Access-Control-Allow-Credentials")).isEqualTo("true");
    }

    @Test
    void h4_downloadLeArquivoForaDoDiretorioDeDocumentos() throws Exception {
        Reply r = send(MockMvcRequestBuilders.get("/api/documentos/download").param("arquivo", "../build-info.txt")
                .header("Authorization", "Bearer " + login(PACIENTE_A)));
        assertThat(r.status()).isEqualTo(200);
        assertThat(r.raw().getResponse().getContentAsString()).contains(BUILD_INFO_MARKER);
    }

    @Test
    void h5_pacienteLeConsultaDeOutroPaciente() throws Exception {
        Reply r = get(login(PACIENTE_A), "/api/consultas/2");
        assertThat(r.status()).isEqualTo(200);
        assertThat(r.body().get("pacienteId").asLong()).isEqualTo(2);
    }

    @Test
    void h6_atualizacaoDePerfilAceitaPapel() throws Exception {
        String token = login(PACIENTE_A);
        Reply r = write("PUT", token, "/api/me", Map.of("nome", "Paciente Exemplo A", "role", "admin"));
        assertThat(r.status()).isEqualTo(200);
        assertThat(r.body().get("papel").asText()).isEqualTo("admin");
        assertThat(get(token, "/api/convenios").status()).isEqualTo(200);
        assertThat(post(token, "/api/convenios", convenioBody("90000040")).status()).isEqualTo(201);
    }

    @Test
    void h7_listagemDevolveCamposQueNaoDeveria() throws Exception {
        Reply r = get(login(ADMIN), "/api/pacientes");
        assertThat(r.body().get("items").get(0).has("notasInternas")).isTrue();
        assertThat(r.body().get("items").get(0).get("senhaHash").asText()).startsWith("$2");
    }

}
