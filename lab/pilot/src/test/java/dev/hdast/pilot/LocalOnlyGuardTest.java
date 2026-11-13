package dev.hdast.pilot;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.InetAddress;
import java.util.List;

import dev.hdast.pilot.config.LocalOnlyGuard;
import org.junit.jupiter.api.Test;

class LocalOnlyGuardTest {

    private static InetAddress ip(String literal) throws Exception {
        return InetAddress.getByName(literal);
    }

    @Test
    void aceita_loopbackPrivadoLinkLocalCgnatEUla() throws Exception {
        List<InetAddress> locais = List.of(ip("127.0.0.1"), ip("172.19.0.2"), ip("10.1.2.3"), ip("192.168.0.9"),
                ip("169.254.1.1"), ip("100.64.0.5"), ip("fd00::1"), ip("::1"));
        assertThat(LocalOnlyGuard.publicAddresses(locais)).isEmpty();
    }

    @Test
    void recusa_enderecoPublicoV4eV6() throws Exception {
        List<InetAddress> publicos = LocalOnlyGuard.publicAddresses(
                List.of(ip("127.0.0.1"), ip("8.8.8.8"), ip("2001:4860:4860::8888")));
        assertThat(publicos).hasSize(2);
    }
}
