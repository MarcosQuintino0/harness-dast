package dev.hdast.pilot.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Configuração do alvo. Tudo vem de variáveis de ambiente (ver application.yml e .env.example).
 *
 * @param vulnerable            modo do alvo: true = padrão do laboratório, false = versão corrigida
 * @param jwtTtlSeconds         vida do token de acesso
 * @param loginMaxPerMinute     tentativas de login por minuto e por origem antes do 429
 * @param xsrfEnforced          exige o par cookie/cabeçalho XSRF nas escritas
 * @param managementPort        porta separada do estado de avaliação
 * @param documentsDir          diretório de documentos fictícios
 * @param localOnlyCheck        recusa subir se alguma interface tiver endereço público
 * @param accounts              contas de teste semeadas na subida
 */
@ConfigurationProperties("pilot")
public record PilotProperties(
        boolean vulnerable,
        long jwtTtlSeconds,
        int loginMaxPerMinute,
        boolean xsrfEnforced,
        int managementPort,
        String documentsDir,
        boolean localOnlyCheck,
        Accounts accounts) {

    public record Accounts(Account admin, Account medico, Account medicoB, Account pacienteA, Account pacienteB) {}

    public record Account(String username, String password) {}
}
