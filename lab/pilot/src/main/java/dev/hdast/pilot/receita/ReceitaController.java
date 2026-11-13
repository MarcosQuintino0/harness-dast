package dev.hdast.pilot.receita;

import java.util.List;

import dev.hdast.pilot.receita.ReceitaService.ReceitaRequest;
import dev.hdast.pilot.receita.ReceitaService.ReceitaResponse;
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
public class ReceitaController {

    private final ReceitaService service;

    public ReceitaController(ReceitaService service) {
        this.service = service;
    }

    @Operation(operationId = "criarReceita", summary = "Emite uma receita para uma consulta (médico ou admin)")
    @PreAuthorize("hasAnyRole('ADMIN','MEDICO')")
    @PostMapping("/api/receitas")
    @ResponseStatus(HttpStatus.CREATED)
    public ReceitaResponse criar(@Valid @RequestBody ReceitaRequest request) {
        return service.create(request);
    }

    @Operation(operationId = "buscarReceita", summary = "Busca uma receita pelo id")
    @GetMapping("/api/receitas/{id}")
    public ReceitaResponse buscar(@PathVariable long id) {
        return service.get(id);
    }

    @Operation(operationId = "listarReceitasDaConsulta", summary = "Lista as receitas de uma consulta")
    @GetMapping("/api/consultas/{id}/receitas")
    public List<ReceitaResponse> listarDaConsulta(@PathVariable long id) {
        return service.listByConsulta(id);
    }
}
