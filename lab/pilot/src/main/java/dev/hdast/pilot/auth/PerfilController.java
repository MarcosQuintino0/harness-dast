package dev.hdast.pilot.auth;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PerfilController {

    public record PerfilRequest(
            @Schema(description = "Nome de exibição") @Size(min = 2, max = 100) String nome,
            @Schema(description = "Telefone com DDD, só dígitos") @Pattern(regexp = "\\d{10,11}") String telefone,
            @Schema(description = "Papel do usuário") Papel role) {}

    public record PerfilResponse(String username, Papel papel, String nome, String telefone, Long pacienteId,
                                 Long medicoId) {}

    private final CurrentUser current;
    private final UsuarioService usuarios;

    public PerfilController(CurrentUser current, UsuarioService usuarios) {
        this.current = current;
        this.usuarios = usuarios;
    }

    @Operation(operationId = "obterPerfil", summary = "Dados do usuário autenticado")
    @GetMapping("/api/me")
    public PerfilResponse obter() {
        return response(current.get());
    }

    @Operation(operationId = "atualizarPerfil", summary = "Atualiza o perfil do usuário autenticado")
    @PutMapping("/api/me")
    public PerfilResponse atualizar(@Valid @RequestBody PerfilRequest request) {
        AuthenticatedUser user = current.get();
        usuarios.updatePerfil(user.id(), request.nome(), request.telefone(), request.role());
        return response(usuarios.findCredentials(user.username()).orElseThrow().user());
    }

    private PerfilResponse response(AuthenticatedUser u) {
        UsuarioService.Perfil p = usuarios.perfil(u.id());
        return new PerfilResponse(u.username(), u.papel(), p.nome(), p.telefone(), u.pacienteId(), u.medicoId());
    }
}
