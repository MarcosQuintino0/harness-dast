package dev.hdast.pilot.auth;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

/** Papéis do sistema; o valor na API e no banco é minúsculo. */
public enum Papel {
    PACIENTE("paciente"), MEDICO("medico"), ADMIN("admin");

    private final String value;

    Papel(String value) { this.value = value; }

    @JsonValue
    public String value() { return value; }

    @JsonCreator
    public static Papel from(String value) {
        for (Papel p : values()) {
            if (p.value.equals(value)) {
                return p;
            }
        }
        throw new IllegalArgumentException("papel desconhecido");
    }

    public String authority() { return "ROLE_" + name(); }
}
