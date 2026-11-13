package dev.hdast.pilot.auth;

import com.fasterxml.jackson.annotation.JsonProperty;
import dev.hdast.pilot.api.ApiException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthController {

    public record LoginRequest(
            @Schema(description = "Nome de usuário") @NotBlank @Size(max = 60) String username,
            @Schema(description = "Senha") @NotBlank @Size(max = 100) String password) {}

    public record LoginResponse(
            @JsonProperty("access_token") @Schema(description = "JWT para o cabeçalho Authorization: Bearer")
            String accessToken,
            @JsonProperty("token_type") String tokenType,
            @JsonProperty("expires_in") @Schema(description = "Segundos de validade do token") long expiresIn,
            Papel papel) {}

    public record CsrfResponse(
            @Schema(description = "Valor do token XSRF") String token,
            @Schema(description = "Cabeçalho em que o token deve voltar") String headerName,
            @Schema(description = "Cookie que o servidor define com o mesmo valor") String cookieName) {}

    private final UsuarioService usuarios;
    private final PasswordEncoder encoder;
    private final JwtService jwt;
    private final LoginRateLimiter limiter;

    public AuthController(UsuarioService usuarios, PasswordEncoder encoder, JwtService jwt, LoginRateLimiter limiter) {
        this.usuarios = usuarios;
        this.encoder = encoder;
        this.jwt = jwt;
        this.limiter = limiter;
    }

    @Operation(operationId = "obterCsrf", summary = "Obtém o token XSRF",
            description = "Define o cookie XSRF-TOKEN e devolve o mesmo valor no corpo. Nas escritas (POST, PUT, "
                    + "PATCH, DELETE) envie o valor no cabeçalho X-XSRF-TOKEN e devolva o cookie.")
    @GetMapping("/api/csrf")
    public CsrfResponse csrf(CsrfToken token) {
        return new CsrfResponse(token.getToken(), token.getHeaderName(), "XSRF-TOKEN");
    }

    @Operation(operationId = "login", summary = "Autentica e devolve um JWT")
    @PostMapping("/api/auth/login")
    public LoginResponse login(@Valid @RequestBody LoginRequest request, HttpServletRequest http) {
        limiter.register(http.getRemoteAddr());
        UsuarioService.Credentials c = usuarios.findCredentials(request.username()).orElse(null);
        if (c == null || !encoder.matches(request.password(), c.passwordHash())) {
            throw ApiException.unauthorized("CREDENCIAIS_INVALIDAS", "Usuário ou senha inválidos.");
        }
        return new LoginResponse(jwt.issue(c.user().username()), "Bearer", jwt.ttlSeconds(), c.user().papel());
    }
}
