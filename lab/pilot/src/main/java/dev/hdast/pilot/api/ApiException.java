package dev.hdast.pilot.api;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;

/** Erro de negócio com status HTTP, código estável e problemas por campo. */
public class ApiException extends RuntimeException {

    private final HttpStatus status;
    private final String code;
    private final List<ErrorBody.FieldIssue> errors;
    private final Map<String, String> headers;

    private ApiException(HttpStatus status, String code, String message,
                         List<ErrorBody.FieldIssue> errors, Map<String, String> headers) {
        super(message);
        this.status = status;
        this.code = code;
        this.errors = errors;
        this.headers = headers;
    }

    public static ApiException notFound(String entity, Object id) {
        return new ApiException(HttpStatus.NOT_FOUND, "NAO_ENCONTRADO", entity + " " + id + " não encontrado(a).",
                List.of(), Map.of());
    }

    public static ApiException conflict(String field, String message) {
        return new ApiException(HttpStatus.CONFLICT, "CONFLITO", message,
                List.of(new ErrorBody.FieldIssue(field, "unique", message)), Map.of());
    }

    public static ApiException conflictWithCode(String code, String message) {
        return new ApiException(HttpStatus.CONFLICT, code, message, List.of(), Map.of());
    }

    /** 422: o corpo é válido, mas aponta para um registro que não existe. */
    public static ApiException unknownReference(String field, String message) {
        return new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "REFERENCIA_INEXISTENTE", message,
                List.of(new ErrorBody.FieldIssue(field, "exists", message)), Map.of());
    }

    public static ApiException forbidden(String message) {
        return new ApiException(HttpStatus.FORBIDDEN, "ACESSO_NEGADO", message, List.of(), Map.of());
    }

    public static ApiException badRequest(String code, String field, String rule, String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, code, message,
                List.of(new ErrorBody.FieldIssue(field, rule, message)), Map.of());
    }

    public static ApiException unauthorized(String code, String message) {
        return new ApiException(HttpStatus.UNAUTHORIZED, code, message, List.of(), Map.of());
    }

    public static ApiException tooManyRequests(long retryAfterSeconds) {
        return new ApiException(HttpStatus.TOO_MANY_REQUESTS, "LIMITE_EXCEDIDO",
                "Muitas tentativas de login. Aguarde " + retryAfterSeconds + " segundo(s) e tente de novo.",
                List.of(), Map.of("Retry-After", Long.toString(retryAfterSeconds)));
    }

    public HttpStatus status() { return status; }

    public String code() { return code; }

    public List<ErrorBody.FieldIssue> errors() { return errors; }

    public Map<String, String> headers() { return headers; }
}
