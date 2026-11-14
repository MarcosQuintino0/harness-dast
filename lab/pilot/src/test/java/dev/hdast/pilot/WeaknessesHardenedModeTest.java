package dev.hdast.pilot;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import java.util.Map;

import dev.hdast.pilot.convenio.ConvenioService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

/** Modo corrigido (PILOT_VULNERABLE=0): as mesmas requisições mínimas de cada item H1..H7 NÃO funcionam. */
@SpringBootTest(properties = "pilot.vulnerable=false")
class WeaknessesHardenedModeTest extends ApiTestBase {

    @MockitoBean ConvenioService convenios; // só para provocar uma falha interna sem depender do banco

    @Test
    void h1_filtroDeBuscaEParametrizado() throws Exception {
        Reply injection = search(login(ADMIN), "zzz' OR 1=1 --");
        assertThat(injection.status()).isEqualTo(200);
        assertThat(injection.body()).isEmpty();
        assertThat(search(login(ADMIN), "'").status()).isEqualTo(200);
        assertThat(search(login(ADMIN), "Exemplo").body()).hasSize(2);
    }

    @Test
    void h2_erroInternoNaoRevelaDetalhes() throws Exception {
        when(convenios.list()).thenThrow(new IllegalStateException("segredo SELECT interno"));
        Reply r = get(login(ADMIN), "/api/convenios");
        assertThat(r.status()).isEqualTo(500);
        assertThat(r.body().get("code").asText()).isEqualTo("ERRO_INTERNO");
        assertThat(r.body().has("trace")).isFalse();
        assertThat(r.body().has("detail")).isFalse();
        assertThat(r.raw().getResponse().getContentAsString()).doesNotContain("segredo").doesNotContain("dev.hdast");
    }

    @Test
    void h3_cabecalhosDeSegurancaPresentesESemCors() throws Exception {
        Reply r = send(MockMvcRequestBuilders.get("/api/saude").header("Origin", "http://origem-qualquer.example"));
        assertThat(r.header("X-Content-Type-Options")).isEqualTo("nosniff");
        assertThat(r.header("Content-Security-Policy")).contains("default-src 'none'");
        assertThat(r.header("X-Frame-Options")).isNotNull();
        assertThat(r.header("Referrer-Policy")).isEqualTo("no-referrer");
        assertThat(r.header("Access-Control-Allow-Origin")).isNull();
    }

    @Test
    void h4_downloadNaoSaiDoDiretorioDeDocumentos() throws Exception {
        String token = login(PACIENTE_A);
        Reply traversal = send(MockMvcRequestBuilders.get("/api/documentos/download").param("arquivo", "../build-info.txt")
                .header("Authorization", "Bearer " + token));
        assertThat(traversal.status()).isEqualTo(400);
        assertThat(traversal.raw().getResponse().getContentAsString()).doesNotContain(BUILD_INFO_MARKER);
        Reply ok = send(MockMvcRequestBuilders.get("/api/documentos/download").param("arquivo", "laudo.txt")
                .header("Authorization", "Bearer " + token));
        assertThat(ok.status()).isEqualTo(200);
    }

    @Test
    void h5_pacienteNaoLeConsultaDeOutroPaciente() throws Exception {
        String token = login(PACIENTE_A);
        assertThat(get(token, "/api/consultas/2").status()).isEqualTo(403);
        assertThat(get(token, "/api/consultas/1").status()).isEqualTo(200);
    }

    @Test
    void h6_atualizacaoDePerfilIgnoraPapel() throws Exception {
        String token = login(PACIENTE_A);
        Reply r = write("PUT", token, "/api/me", Map.of("nome", "Paciente Exemplo A", "role", "admin"));
        assertThat(r.status()).isEqualTo(200);
        assertThat(r.body().get("papel").asText()).isEqualTo("paciente");
        assertThat(post(token, "/api/convenios", convenioBody("90000040")).status()).isEqualTo(403);
    }

    @Test
    void h7_listagemNaoDevolveCamposInternos() throws Exception {
        Reply r = get(login(ADMIN), "/api/pacientes");
        assertThat(r.body().get("items").get(0).has("notasInternas")).isFalse();
        assertThat(r.body().get("items").get(0).has("senhaHash")).isFalse();
        assertThat(r.body().get("items").get(0).has("nome")).isTrue();
    }

    private Reply getRaw(String token, String rawPath) throws Exception {
        return send(MockMvcRequestBuilders.get(java.net.URI.create(rawPath)).header("Authorization", "Bearer " + token));
    }

    @Test
    void h8_codigoNoCaminhoEValidado() throws Exception {
        String token = login(ADMIN);
        assertThat(getRaw(token, "/api/convenios/codigo/00000001").status()).isEqualTo(200);
        long t0 = System.nanoTime();
        Reply r = getRaw(token, "/api/convenios/codigo/1'%20and%20sleep(2)%20--%20");
        assertThat(r.status()).isEqualTo(400);
        assertThat((System.nanoTime() - t0) / 1_000_000).isLessThan(1500);
    }

    @Test
    void h9_nomeDeArquivoNoCaminhoEValidadoEBarraCodificadaERecusada() throws Exception {
        String token = login(ADMIN);
        assertThat(getRaw(token, "/api/arquivos/laudo-0001.txt").status()).isEqualTo(200);
        Reply passwd = getRaw(token, "/api/arquivos/..%2f..%2fetc%2fpasswd");
        assertThat(passwd.raw().getResponse().getContentAsString()).doesNotContain("root:x:0:0:");
        assertThat(passwd.status()).isIn(400, 404);
    }

    @Test
    void h10_crmNoCaminhoEParametrizado() throws Exception {
        String token = login(ADMIN);
        assertThat(getRaw(token, "/api/medicos/crm/%27").status()).isEqualTo(400);
        assertThat(getRaw(token, "/api/medicos/crm/12345-SP").status()).isEqualTo(200);
    }

}
