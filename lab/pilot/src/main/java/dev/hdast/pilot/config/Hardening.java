package dev.hdast.pilot.config;

import org.springframework.stereotype.Component;

/**
 * Chave única dos blocos endurecíveis do alvo. Cada ponto do código pergunta
 * {@code hardening.applies(Item.Hn)}: verdadeiro quando o alvo está no modo corrigido.
 */
@Component
public class Hardening {

    public enum Item { H1, H2, H3, H4, H5, H6, H7, H8, H9, H10 }

    private final boolean vulnerable;

    public Hardening(PilotProperties properties) {
        this.vulnerable = properties.vulnerable();
    }

    public boolean applies(Item item) {
        return !vulnerable;
    }

    public boolean isVulnerableMode() {
        return vulnerable;
    }
}
