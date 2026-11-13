package dev.hdast.pilot.paciente;

import java.util.List;

import dev.hdast.pilot.paciente.PacienteService.Pagina;
import dev.hdast.pilot.paciente.PacienteService.PacienteRequest;
import dev.hdast.pilot.paciente.PacienteService.PacienteResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PacienteController {

    private final PacienteService service;

    public PacienteController(PacienteService service) {
        this.service = service;
    }

    @Operation(operationId = "criarPaciente", summary = "Cadastra um paciente (médico ou admin)")
    @PreAuthorize("hasAnyRole('ADMIN','MEDICO')")
    @PostMapping("/api/pacientes")
    @ResponseStatus(HttpStatus.CREATED)
    public PacienteResponse criar(@Valid @RequestBody PacienteRequest request) {
        return service.create(request);
    }

    @Operation(operationId = "listarPacientes", summary = "Lista pacientes (paciente vê só o próprio)")
    @GetMapping("/api/pacientes")
    public Pagina listar(@RequestParam(defaultValue = "0") @Min(0) int page,
                         @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        return service.list(page, size);
    }

    @Operation(operationId = "buscarPacientesPorNome", summary = "Busca pacientes pelo nome (médico ou admin)")
    @PreAuthorize("hasAnyRole('ADMIN','MEDICO')")
    @GetMapping("/api/pacientes/busca")
    public List<PacienteResponse> buscarPorNome(@RequestParam @NotBlank @Size(max = 100) String nome) {
        return service.search(nome);
    }

    @Operation(operationId = "buscarPaciente", summary = "Busca um paciente pelo id")
    @GetMapping("/api/pacientes/{id}")
    public PacienteResponse buscar(@PathVariable long id) {
        return service.getAuthorized(id);
    }

    @Operation(operationId = "atualizarPaciente", summary = "Atualiza um paciente")
    @PutMapping("/api/pacientes/{id}")
    public PacienteResponse atualizar(@PathVariable long id, @Valid @RequestBody PacienteRequest request) {
        return service.update(id, request);
    }

    @Operation(operationId = "removerPaciente", summary = "Remove um paciente sem consultas (admin)")
    @PreAuthorize("hasRole('ADMIN')")
    @DeleteMapping("/api/pacientes/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void remover(@PathVariable long id) {
        service.delete(id);
    }
}
