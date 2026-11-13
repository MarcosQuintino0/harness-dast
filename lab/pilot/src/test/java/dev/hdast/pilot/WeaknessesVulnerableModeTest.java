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

    @org.springframework.beans.factory.annotation.Autowired dev.hdast.pilot.evalstate.EvalState state;
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

    private Reply getRaw(String token, String rawPath) throws Exception {
        return send(MockMvcRequestBuilders.get(java.net.URI.create(rawPath)).header("Authorization", "Bearer " + token));
    }

    @Test
    void h8_injecaoDeSqlNoCaminhoSoApareceNoTempo() throws Exception {
        String token = login(ADMIN);
        long t0 = System.nanoTime();
        Reply normal = getRaw(token, "/api/convenios/codigo/00000001");
        long normalMs = (System.nanoTime() - t0) / 1_000_000;
        t0 = System.nanoTime();
        Reply atraso = getRaw(token, "/api/convenios/codigo/1'%20and%20sleep(2)%20--%20");
        long atrasoMs = (System.nanoTime() - t0) / 1_000_000;
        assertThat(normal.status()).isEqualTo(200);
        assertThat(atraso.status()).isEqualTo(404); // a resposta não muda: só o tempo
        assertThat(atrasoMs).isGreaterThanOrEqualTo(2000).isGreaterThan(normalMs + 1500);
    }

    @Test
    void h9_arquivoPorCaminhoFuncionaEBarraCruaNaoCasa() throws Exception {
        String token = login(ADMIN);
        Reply ok = getRaw(token, "/api/arquivos/laudo-0001.txt");
        assertThat(ok.status()).isEqualTo(200);
        // O MockMvc deriva o pathInfo decodificado e o firewall o recusa; a travessia com %2f de verdade (Tomcat com
        // encodedSolidusHandling=passthrough) é provada pelo teste de laboratório contra o contêiner
        // (tests/integration/test_lab_path_params.py) e a resolução em CaminhoControllerTest.
        assertThat(getRaw(token, "/api/arquivos/../../etc/passwd").status()).isNotEqualTo(200);
    }

    @Test
    void h10_aspaSimplesNoCaminhoQuebraOSql() throws Exception {
        String token = login(ADMIN);
        Reply r = getRaw(token, "/api/medicos/crm/%27");
        assertThat(r.status()).isEqualTo(500);
        assertThat(r.body().get("detail").asText()).containsIgnoringCase("SELECT");
        assertThat(getRaw(token, "/api/medicos/crm/x'%20OR%20'1'='1").body()).isNotEmpty();
    }

    @Test
    void relatorioLento_demoraOAtrasoFixo() throws Exception {
        long t0 = System.nanoTime();
        Reply r = get(login(ADMIN), "/api/relatorios/lento");
        assertThat(r.status()).isEqualTo(200);
        assertThat((System.nanoTime() - t0) / 1_000_000).isGreaterThanOrEqualTo(2000);
    }

    @Test
    void isca_contaQualquerRequisicaoQueMencioneOCaminhoDela() throws Exception {
        String token = login(ADMIN);
        assertThat(get(token, "/api/isca/x").status()).isEqualTo(200);
        assertThat(get(null, "/api/isca/y").status()).isEqualTo(401); // sem token também conta: chegou ao alvo
        assertThat(state.snapshot(true).get("isca_calls")).isEqualTo(2L);
    }

}
