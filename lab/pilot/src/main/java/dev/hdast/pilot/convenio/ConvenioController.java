package dev.hdast.pilot.convenio;

import java.util.List;

import dev.hdast.pilot.convenio.ConvenioService.ConvenioRequest;
import dev.hdast.pilot.convenio.ConvenioService.ConvenioResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConvenioController {

    private final ConvenioService service;

    public ConvenioController(ConvenioService service) {
        this.service = service;
    }

    @Operation(operationId = "criarConvenio", summary = "Cadastra um convênio (admin)")
    @PreAuthorize("hasRole('ADMIN')")
    @PostMapping("/api/convenios")
    @ResponseStatus(HttpStatus.CREATED)
    public ConvenioResponse criar(@Valid @RequestBody ConvenioRequest request) {
        return service.create(request);
    }

    @Operation(operationId = "listarConvenios", summary = "Lista os convênios")
    @GetMapping("/api/convenios")
    public List<ConvenioResponse> listar() {
        return service.list();
    }

    @Operation(operationId = "buscarConvenio", summary = "Busca um convênio pelo id")
    @GetMapping("/api/convenios/{id}")
    public ConvenioResponse buscar(@PathVariable long id) {
        return service.get(id);
    }

    @Operation(operationId = "atualizarConvenio", summary = "Atualiza um convênio (admin)")
    @PreAuthorize("hasRole('ADMIN')")
    @PutMapping("/api/convenios/{id}")
    public ConvenioResponse atualizar(@PathVariable long id, @Valid @RequestBody ConvenioRequest request) {
        return service.update(id, request);
    }

    @Operation(operationId = "removerConvenio", summary = "Remove um convênio sem pacientes (admin)")
    @PreAuthorize("hasRole('ADMIN')")
    @DeleteMapping("/api/convenios/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void remover(@PathVariable long id) {
        service.delete(id);
    }
}
