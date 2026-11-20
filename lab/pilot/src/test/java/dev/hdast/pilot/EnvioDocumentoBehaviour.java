package dev.hdast.pilot;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.request.MockMultipartHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

/** Envio de arquivo (enviarDocumento): igual nos dois modos, sem falha plantada. */
abstract class EnvioDocumentoBehaviour extends ApiTestBase {

    private Reply enviar(MockMultipartFile arquivo, String descricao, boolean comToken) throws Exception {
        String xsrf = xsrfToken();
        MockMultipartHttpServletRequestBuilder b = MockMvcRequestBuilders.multipart("/api/documentos/enviar");
        if (arquivo != null) {
            b.file(arquivo);
        }
        if (descricao != null) {
            b.param("descricao", descricao);
        }
        b.cookie(new Cookie("XSRF-TOKEN", xsrf)).header("X-XSRF-TOKEN", xsrf);
        if (comToken) {
            b.header("Authorization", "Bearer " + login(MEDICO));
        }
        return send(b);
    }

    private static MockMultipartFile arquivo(String nome, String tipo, byte[] bytes) {
        return new MockMultipartFile("arquivo", nome, tipo, bytes);
    }

    @Test
    void enviar_devolve201ComNomeTamanhoETipoQuandoArquivoValido() throws Exception {
        byte[] bytes = "synthetic file\n".getBytes(StandardCharsets.UTF_8);
        Reply r = enviar(arquivo("synthetic.txt", "text/plain", bytes), "teste", true);
        assertThat(r.status()).isEqualTo(201);
        assertThat(r.body().get("nome").asText()).isEqualTo("synthetic.txt");
        assertThat(r.body().get("tamanho").asLong()).isEqualTo(bytes.length);
        assertThat(r.body().get("tipo").asText()).isEqualTo("text/plain");
    }

    @Test
    void enviar_saneiaONomeQuandoVemComCaminho() throws Exception {
        Reply r = enviar(arquivo("../../etc/passwd", "text/plain", new byte[] {65}), null, true);
        assertThat(r.status()).isEqualTo(201);
        assertThat(r.body().get("nome").asText()).isEqualTo("passwd");
    }

    @Test
    void enviar_devolve415QuandoTipoNaoAceito() throws Exception {
        Reply r = enviar(arquivo("a.bin", "application/octet-stream", new byte[] {1, 2}), null, true);
        assertThat(r.status()).isEqualTo(415);
        assertThat(r.body().get("code").asText()).isEqualTo("TIPO_ARQUIVO_NAO_SUPORTADO");
    }

    @Test
    void enviar_devolve400QuandoArquivoGrandeDemais() throws Exception {
        Reply r = enviar(arquivo("g.txt", "text/plain", new byte[64 * 1024 + 1]), null, true);
        assertThat(r.status()).isEqualTo(400);
        assertThat(r.body().get("code").asText()).isEqualTo("VALIDACAO");
    }

    @Test
    void enviar_devolve400QuandoArquivoAusente() throws Exception {
        Reply r = enviar(null, "so descricao", true);
        assertThat(r.status()).isEqualTo(400);
        assertThat(r.body().get("code").asText()).isEqualTo("VALIDACAO");
        assertThat(r.body().get("errors").get(0).get("field").asText()).isEqualTo("arquivo");
    }

    @Test
    void enviar_devolve401QuandoSemToken() throws Exception {
        Reply r = enviar(arquivo("a.txt", "text/plain", new byte[] {65}), null, false);
        assertThat(r.status()).isEqualTo(401);
    }
}
