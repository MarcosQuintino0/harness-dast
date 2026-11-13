package dev.hdast.pilot.config;

import java.io.IOException;
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.hdast.pilot.api.ErrorBody;
import dev.hdast.pilot.auth.JwtAuthenticationFilter;
import dev.hdast.pilot.auth.JwtService;
import dev.hdast.pilot.auth.UsuarioService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.HeadersConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfException;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    private final ObjectMapper mapper;

    public SecurityConfig(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(8);
    }

    /**
     * Modo vulnerável (H9): o firewall aceita {@code %2f} e {@code ;} no caminho (o padrão do Spring Security os recusa
     * com 400). No modo corrigido vale o padrão.
     */
    @Bean
    org.springframework.security.web.firewall.HttpFirewall httpFirewall(PilotProperties props) {
        org.springframework.security.web.firewall.StrictHttpFirewall firewall =
                new org.springframework.security.web.firewall.StrictHttpFirewall();
        if (props.vulnerable()) {
            firewall.setAllowUrlEncodedSlash(true);
            firewall.setAllowSemicolon(true);
        }
        return firewall;
    }

    /** Porta de gestão: sem autenticação, mas só alcançável pela porta separada (ver EdgeFilter). */
    @Bean
    @Order(1)
    SecurityFilterChain internalChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/internal/**")
                .csrf(csrf -> csrf.disable())
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(a -> a.anyRequest().permitAll());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiChain(HttpSecurity http, PilotProperties props, Hardening hardening,
                                 JwtService jwt, UsuarioService usuarios) throws Exception {
        CsrfTokenRequestAttributeHandler plain = new CsrfTokenRequestAttributeHandler();
        plain.setCsrfRequestAttributeName(null); // carrega o token em toda requisição: o cookie sai em qualquer GET
        CookieCsrfTokenRepository csrfRepository = CookieCsrfTokenRepository.withHttpOnlyFalse();
        csrfRepository.setCookiePath("/");
        csrfRepository.setCookieCustomizer(c -> c.sameSite("Strict"));

        http.sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(csrf -> {
                    csrf.csrfTokenRepository(csrfRepository).csrfTokenRequestHandler(plain)
                            .ignoringRequestMatchers(new AntPathRequestMatcher("/api/auth/login", "POST"));
                    if (!props.xsrfEnforced()) {
                        csrf.requireCsrfProtectionMatcher(r -> false);
                    }
                })
                .authorizeHttpRequests(a -> a
                        .requestMatchers("/api/csrf", "/api/saude", "/v3/api-docs", "/v3/api-docs/**").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/auth/login").permitAll()
                        .anyRequest().authenticated())
                .exceptionHandling(e -> e.authenticationEntryPoint(entryPoint()).accessDeniedHandler(deniedHandler()))
                .addFilterBefore(new JwtAuthenticationFilter(jwt, usuarios), UsernamePasswordAuthenticationFilter.class);

        applyHeadersAndCors(http, hardening);
        return http.build();
    }

    private void applyHeadersAndCors(HttpSecurity http, Hardening hardening) throws Exception {
        if (hardening.applies(Hardening.Item.H3)) {
            http.headers(h -> h
                    .contentSecurityPolicy(csp -> csp.policyDirectives("default-src 'none'; frame-ancestors 'none'"))
                    .referrerPolicy(r -> r.policy(
                            org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER))
                    .permissionsPolicyHeader(p -> p.policy("geolocation=(), camera=(), microphone=()"))
                    .crossOriginOpenerPolicy(c -> c.policy(
                            org.springframework.security.web.header.writers.CrossOriginOpenerPolicyHeaderWriter.CrossOriginOpenerPolicy.SAME_ORIGIN))
                    .crossOriginResourcePolicy(c -> c.policy(
                            org.springframework.security.web.header.writers.CrossOriginResourcePolicyHeaderWriter.CrossOriginResourcePolicy.SAME_ORIGIN)));
        } else {
            http.headers(h -> h.disable());
            http.cors(c -> c.configurationSource(permissiveCors()));
        }
    }

    private CorsConfigurationSource permissiveCors() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOriginPatterns(List.of("*"));
        cors.setAllowedMethods(List.of("*"));
        cors.setAllowedHeaders(List.of("*"));
        cors.setExposedHeaders(List.of("*"));
        cors.setAllowCredentials(true);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }

    private AuthenticationEntryPoint entryPoint() {
        return (request, response, ex) -> {
            Object reason = request.getAttribute(JwtAuthenticationFilter.ERROR_ATTRIBUTE);
            ErrorBody body = reason == JwtService.Failure.EXPIRED
                    ? ErrorBody.of("TOKEN_EXPIRADO", "O token expirou. Faça login de novo em POST /api/auth/login.")
                    : reason == JwtService.Failure.INVALID
                    ? ErrorBody.of("TOKEN_INVALIDO", "Token inválido. Faça login em POST /api/auth/login.")
                    : ErrorBody.of("NAO_AUTENTICADO", "Autenticação necessária: envie Authorization: Bearer <token>.");
            write(response, 401, body);
        };
    }

    private AccessDeniedHandler deniedHandler() {
        return (HttpServletRequest request, HttpServletResponse response, org.springframework.security.access.AccessDeniedException ex) -> {
            ErrorBody body = ex instanceof CsrfException
                    ? ErrorBody.of("XSRF_INVALIDO", "Token XSRF ausente ou diferente do cookie. Faça GET /api/csrf e "
                            + "envie o valor no cabeçalho X-XSRF-TOKEN junto com o cookie XSRF-TOKEN.")
                    : ErrorBody.of("ACESSO_NEGADO", "Seu papel não tem permissão para esta operação.");
            write(response, 403, body);
        };
    }

    private void write(HttpServletResponse response, int status, ErrorBody body) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding("UTF-8");
        mapper.writeValue(response.getWriter(), body);
    }
}
