package dev.hdast.pilot.auth;

import java.io.IOException;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/** Autentica por "Authorization: Bearer". Token ruim não barra aqui: o ponto de entrada responde 401. */
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    public static final String ERROR_ATTRIBUTE = "pilot.auth.error";

    private final JwtService jwt;
    private final UsuarioService usuarios;

    public JwtAuthenticationFilter(JwtService jwt, UsuarioService usuarios) {
        this.jwt = jwt;
        this.usuarios = usuarios;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        if (header != null && header.regionMatches(true, 0, "Bearer ", 0, 7)) {
            JwtService.Parsed parsed = jwt.parse(header.substring(7).trim());
            if (parsed.failure() != null) {
                request.setAttribute(ERROR_ATTRIBUTE, parsed.failure());
            } else {
                usuarios.findCredentials(parsed.username()).ifPresentOrElse(c -> {
                    var auth = new UsernamePasswordAuthenticationToken(c.user(), null,
                            List.of(new SimpleGrantedAuthority(c.user().papel().authority())));
                    SecurityContextHolder.getContext().setAuthentication(auth);
                }, () -> request.setAttribute(ERROR_ATTRIBUTE, JwtService.Failure.INVALID));
            }
        }
        chain.doFilter(request, response);
    }
}
