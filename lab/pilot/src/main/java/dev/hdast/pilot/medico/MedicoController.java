package dev.hdast.pilot.medico;

import java.util.List;

import dev.hdast.pilot.medico.MedicoService.MedicoRequest;
import dev.hdast.pilot.medico.MedicoService.MedicoResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MedicoController {

    private final MedicoService service;

    public MedicoController(MedicoService service) {
        this.service = service;
    }

    @Operation(operationId = "criarMedico", summary = "Cadastra um médico (admin)")
    @PreAuthorize("hasRole('ADMIN')")
    @PostMapping("/api/medicos")
    @ResponseStatus(HttpStatus.CREATED)
    public MedicoResponse criar(@Valid @RequestBody MedicoRequest request) {
        return service.create(request);
    }

    @Operation(operationId = "listarMedicos", summary = "Lista os médicos")
    @GetMapping("/api/medicos")
    public List<MedicoResponse> listar() {
        return service.list();
    }

    @Operation(operationId = "buscarMedico", summary = "Busca um médico pelo id")
    @GetMapping("/api/medicos/{id}")
    public MedicoResponse buscar(@PathVariable long id) {
        return service.get(id);
    }
}
