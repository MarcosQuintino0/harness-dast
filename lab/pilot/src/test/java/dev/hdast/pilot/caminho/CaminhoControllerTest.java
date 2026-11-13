package dev.hdast.pilot.caminho;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/** Testes de unidade dos pedaços puros do CaminhoController (sem Spring). */
class CaminhoControllerTest {

    @Test
    void atrasoDaInjecao_somaAsEsperasEOLimiteSeAplica() {
        assertThat(CaminhoController.atrasoDaInjecao("1' and sleep(5) -- ")).isEqualTo(5000);
        assertThat(CaminhoController.atrasoDaInjecao("x'; select pg_sleep(3) --")).isEqualTo(3000);
        assertThat(CaminhoController.atrasoDaInjecao("00000001")).isZero();
        assertThat(CaminhoController.atrasoDaInjecao("sleep(5)")).isZero(); // sem sinal de injeção
        assertThat(CaminhoController.atrasoDaInjecao("' or sleep(999) #")).isEqualTo(16000);
    }

    @Test
    void resolverVirtual_resolvePontosPontosSemSairDaRaiz() {
        assertThat(CaminhoController.resolverVirtual("/app/documentos", "laudo-0001.txt"))
                .isEqualTo("/app/documentos/laudo-0001.txt");
        assertThat(CaminhoController.resolverVirtual("/app/documentos", "../../etc/passwd")).isEqualTo("/etc/passwd");
        assertThat(CaminhoController.resolverVirtual("/app/documentos", "../../../../../etc/passwd"))
                .isEqualTo("/etc/passwd");
        assertThat(CaminhoController.resolverVirtual("/app/documentos", "/etc/passwd")).isEqualTo("/etc/passwd");
    }

    private static CaminhoController controller(boolean vulnerable) {
        var props = new dev.hdast.pilot.config.PilotProperties(vulnerable, 300, 5, true, 9091, "documentos", false, null);
        return new CaminhoController(null, null, new dev.hdast.pilot.config.Hardening(props));
    }

    @Test
    void arquivo_modoVulneravelLeOPasswdSimuladoComBarraDecodificada() {
        String conteudo = controller(true).arquivo("../../etc/passwd");
        assertThat(conteudo).contains("root:x:0:0:").contains("SIMULADO");
        assertThat(controller(true).arquivo("../build-info.txt")).contains("PILOT-BUILD-INFO");
    }

    @Test
    void arquivo_modoCorrigidoRecusaTravessia() {
        var ex = org.junit.jupiter.api.Assertions.assertThrows(dev.hdast.pilot.api.ApiException.class,
                () -> controller(false).arquivo("../../etc/passwd"));
        assertThat(ex.status().value()).isEqualTo(400);
        assertThat(controller(false).arquivo("laudo-0001.txt")).contains("Laudo");
    }
}
