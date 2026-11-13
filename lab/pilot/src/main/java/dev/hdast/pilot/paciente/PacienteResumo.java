package dev.hdast.pilot.paciente;

import java.util.Map;

import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonIgnore;
import io.swagger.v3.oas.annotations.media.Schema;

/** Item da listagem de pacientes. */
public class PacienteResumo {

    @Schema(description = "Identificador do paciente")
    private final Long id;
    private final String nome;
    private final String cpf;
    private final String email;
    private final Long convenioId;
    @JsonIgnore
    private final Map<String, Object> extras;

    public PacienteResumo(Long id, String nome, String cpf, String email, Long convenioId, Map<String, Object> extras) {
        this.id = id;
        this.nome = nome;
        this.cpf = cpf;
        this.email = email;
        this.convenioId = convenioId;
        this.extras = extras;
    }

    public Long getId() { return id; }

    public String getNome() { return nome; }

    public String getCpf() { return cpf; }

    public String getEmail() { return email; }

    public Long getConvenioId() { return convenioId; }

    @JsonAnyGetter
    @Schema(hidden = true)
    public Map<String, Object> extras() { return extras; }
}
