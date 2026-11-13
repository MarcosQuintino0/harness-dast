package dev.hdast.pilot.config;

import java.util.List;
import java.util.Set;

import dev.hdast.pilot.api.ErrorBody;
import io.swagger.v3.core.converter.ModelConverters;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.responses.ApiResponses;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.utils.SpringDocUtils;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    static {
        // Parametro injetado pelo Spring Security: nao faz parte do contrato HTTP.
        SpringDocUtils.getConfig().addRequestWrapperToIgnore(org.springframework.security.web.csrf.CsrfToken.class);
    }

    private static final Set<String> PUBLIC_PATHS = Set.of("/api/csrf", "/api/saude", "/api/auth/login");

    @Bean
    OpenAPI baseOpenApi() {
        return new OpenAPI()
                .info(new Info().title("Clínica Piloto API").version("1.0.0")
                        .description("API REST fictícia de uma clínica: convênios, médicos, pacientes, consultas e receitas. "
                                + "Dados sintéticos. Autenticação por JWT (POST /api/auth/login); escritas exigem também "
                                + "o par cookie/cabeçalho XSRF (GET /api/csrf)."))
                .servers(List.of(new Server().url("http://localhost:8080").description("Ambiente local")));
    }

    @Bean
    OpenApiCustomizer securityAndErrors() {
        return openApi -> {
            openApi.getComponents().addSecuritySchemes("bearerAuth",
                    new SecurityScheme().type(SecurityScheme.Type.HTTP).scheme("bearer").bearerFormat("JWT"));
            openApi.getComponents().addSecuritySchemes("xsrfToken",
                    new SecurityScheme().type(SecurityScheme.Type.APIKEY).in(SecurityScheme.In.HEADER)
                            .name("X-XSRF-TOKEN").description("Valor do cookie XSRF-TOKEN (obtido em GET /api/csrf); "
                                    + "o cookie também deve ser enviado."));
            ModelConverters.getInstance().readAll(ErrorBody.class)
                    .forEach((name, schema) -> openApi.getComponents().addSchemas(name, schema));
            Content errorContent = new Content().addMediaType("application/json",
                    new MediaType().schema(new Schema<>().$ref("#/components/schemas/ErrorBody")));
            openApi.getPaths().forEach((path, item) -> item.readOperationsMap().forEach((method, op) -> {
                op.getResponses().addApiResponse("default", new ApiResponse()
                        .description("Erro (corpo padrão com code, message e errors)").content(errorContent));
                applySecurity(path, method, op);
            }));
        };
    }

    private static void applySecurity(String path, PathItem.HttpMethod method, Operation op) {
        if (PUBLIC_PATHS.contains(path)) {
            op.setSecurity(List.of());
            return;
        }
        boolean writes = method != PathItem.HttpMethod.GET;
        SecurityRequirement requirement = new SecurityRequirement().addList("bearerAuth");
        if (writes) {
            requirement.addList("xsrfToken");
        }
        op.setSecurity(List.of(requirement));
    }
}
