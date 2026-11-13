package dev.hdast.pilot.config;

import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/**
 * Recusa subir fora de um ambiente local e imprime o aviso de software de treino.
 * "Local" = todas as interfaces ativas têm endereço de loopback, privado, link-local ou CGNAT.
 */
@Component
public class LocalOnlyGuard {

    private static final Logger LOG = LoggerFactory.getLogger(LocalOnlyGuard.class);

    private final PilotProperties properties;

    public LocalOnlyGuard(PilotProperties properties) {
        this.properties = properties;
        if (properties.localOnlyCheck()) {
            List<InetAddress> publicas = publicAddresses(interfaceAddresses());
            if (!publicas.isEmpty()) {
                throw new IllegalStateException("Recusando subir: a interface tem endereço público " + publicas
                        + ". Esta aplicação é software de treino e só roda em rede local/Docker, "
                        + "sem endereço público (não use --network host em máquina com IP público).");
            }
        }
    }

    @EventListener(ApplicationReadyEvent.class)
    void announce() {
        String modo = properties.vulnerable() ? "MODO PADRAO DO LABORATORIO (PILOT_VULNERABLE=1)"
                : "MODO CORRIGIDO (PILOT_VULNERABLE=0)";
        String barra = "=".repeat(78);
        LOG.warn("\n{}\n  CLINICA PILOTO: SOFTWARE DE TREINO INTENCIONALMENTE VULNERAVEL.\n"
                + "  Nao e um produto. Dados ficticios. Rode SOMENTE em localhost/Docker local.\n"
                + "  Nunca exponha esta porta fora da maquina. {}\n{}", barra, modo, barra);
    }

    static List<InetAddress> interfaceAddresses() {
        List<InetAddress> out = new ArrayList<>();
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (ni.isUp()) {
                    out.addAll(Collections.list(ni.getInetAddresses()));
                }
            }
        } catch (java.net.SocketException e) {
            throw new IllegalStateException("Não foi possível listar as interfaces de rede", e);
        }
        return out;
    }

    /** Endereços que NÃO são locais. Pública para ser testada sem rede. */
    public static List<InetAddress> publicAddresses(List<InetAddress> addresses) {
        return addresses.stream().filter(a -> !isLocal(a)).toList();
    }

    private static boolean isLocal(InetAddress a) {
        if (a.isLoopbackAddress() || a.isLinkLocalAddress() || a.isSiteLocalAddress() || a.isAnyLocalAddress()) {
            return true;
        }
        byte[] b = a.getAddress();
        if (a instanceof Inet6Address) {
            return (b[0] & 0xFE) == 0xFC; // fc00::/7, endereço local único
        }
        return (b[0] & 0xFF) == 100 && (b[1] & 0xC0) == 64; // 100.64.0.0/10, CGNAT
    }
}
