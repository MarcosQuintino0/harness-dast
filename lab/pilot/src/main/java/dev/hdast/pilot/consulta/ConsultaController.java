package dev.hdast.pilot.consulta;

import java.util.List;

import dev.hdast.pilot.consulta.ConsultaService.ConsultaRequest;
import dev.hdast.pilot.consulta.ConsultaService.ConsultaResponse;
import dev.hdast.pilot.consulta.ConsultaService.StatusRequest;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConsultaController {

    private final ConsultaService service;

    public ConsultaController(ConsultaService service) {
        this.service = service;
    }

    @Operation(operationId = "criarConsulta", summary = "Agenda uma consulta (paciente só para si)")
    @PostMapping("/api/consultas")
    @ResponseStatus(HttpStatus.CREATED)
    public ConsultaResponse criar(@Valid @RequestBody ConsultaRequest request) {
        return service.create(request);
    }

    @Operation(operationId = "listarConsultas", summary = "Lista consultas (paciente vê só as próprias)")
    @GetMapping("/api/consultas")
    public List<ConsultaResponse> listar() {
        return service.list();
    }

    @Operation(operationId = "buscarConsulta", summary = "Busca uma consulta pelo id")
    @GetMapping("/api/consultas/{id}")
    public ConsultaResponse buscar(@PathVariable long id) {
        return service.get(id);
    }

    @Operation(operationId = "atualizarStatusConsulta", summary = "Marca a consulta como REALIZADA ou CANCELADA")
    @PatchMapping("/api/consultas/{id}/status")
    public ConsultaResponse atualizarStatus(@PathVariable long id, @Valid @RequestBody StatusRequest request) {
        return service.updateStatus(id, request.status());
    }
}
