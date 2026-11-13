package dev.hdast.pilot.config;

import java.io.IOException;

import dev.hdast.pilot.evalstate.EvalState;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.apache.catalina.connector.Connector;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

/**
 * Borda do servidor: (1) /internal/** só existe na porta de gestão e o resto da API só na porta
 * principal; (2) conta as requisições por rota para o estado de avaliação.
 */
@Configuration
public class EdgeFilter {

    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory> managementConnector(PilotProperties props) {
        return factory -> {
            Connector connector = new Connector("org.apache.coyote.http11.Http11NioProtocol");
            connector.setPort(props.managementPort());
            factory.addAdditionalTomcatConnectors(connector);
        };
    }

    /**
     * Modo vulnerável (H9): o Tomcat deixa o {@code %2f} passar sem decodificar, para o Spring tratá-lo como parte do
     * segmento do caminho. No modo corrigido vale o padrão do Tomcat (400 para {@code %2f}).
     */
    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory> encodedSlashPassthrough(PilotProperties props) {
        return factory -> factory.addConnectorCustomizers(connector -> {
            if (props.vulnerable()) {
                connector.setEncodedSolidusHandling("passthrough");
            }
        });
    }

    /** Verdadeiro se o caminho cru, antes ou depois de decodificar o percentual, traz o segmento da isca. */
    static boolean mencionaIsca(String rawUri) {
        String lower = rawUri.toLowerCase(java.util.Locale.ROOT);
        String decoded;
        try {
            decoded = java.net.URLDecoder.decode(lower.replace("+", "%2b"), java.nio.charset.StandardCharsets.UTF_8);
        } catch (IllegalArgumentException e) {
            decoded = lower;
        }
        return lower.contains("/api/isca") || decoded.contains("/api/isca") || lower.contains("%2fapi%2fisca");
    }

    @Bean
    FilterRegistrationBean<OncePerRequestFilter> edge(PilotProperties props, EvalState state) {
        OncePerRequestFilter filter = new OncePerRequestFilter() {
            @Override
            protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain)
                    throws ServletException, IOException {
                boolean internalPath = req.getRequestURI().startsWith("/internal/");
                boolean managementPort = req.getLocalPort() == props.managementPort();
                if (internalPath != managementPort) {
                    res.setStatus(404);
                    res.setContentType("application/json");
                    res.getWriter().write("{\"code\":\"NAO_ENCONTRADO\",\"message\":\"Recurso não encontrado.\",\"errors\":[]}");
                    return;
                }
                if (!internalPath && mencionaIsca(req.getRequestURI())) {
                    state.iscaCalled();
                }
                chain.doFilter(req, res);
                if (!internalPath) {
                    state.countRequest(req.getMethod(),
                            (String) req.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE),
                            req.getRequestURI());
                }
            }
        };
        FilterRegistrationBean<OncePerRequestFilter> bean = new FilterRegistrationBean<>(filter);
        bean.setOrder(-200); // antes da cadeia do Spring Security
        return bean;
    }
}
