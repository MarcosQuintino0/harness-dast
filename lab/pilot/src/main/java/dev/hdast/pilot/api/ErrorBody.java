package dev.hdast.pilot.api;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonIgnore;
import io.swagger.v3.oas.annotations.media.Schema;

/** Corpo único de erro da API. */
@Schema(description = "Corpo de erro padrão")
public class ErrorBody {

    @Schema(description = "Código estável do erro")
    private final String code;
    @Schema(description = "Mensagem para humanos")
    private final String message;
    @Schema(description = "Problemas por campo (vazio quando não se aplica)")
    private final List<FieldIssue> errors;
    @JsonIgnore
    private final Map<String, Object> extras;

    public ErrorBody(String code, String message, List<FieldIssue> errors, Map<String, Object> extras) {
        this.code = code;
        this.message = message;
        this.errors = errors;
        this.extras = extras;
    }

    public static ErrorBody of(String code, String message) {
        return new ErrorBody(code, message, List.of(), Map.of());
    }

    public String getCode() { return code; }

    public String getMessage() { return message; }

    public List<FieldIssue> getErrors() { return errors; }

    @JsonAnyGetter
    @Schema(hidden = true)
    public Map<String, Object> extras() { return extras; }

    @Schema(description = "Problema em um campo")
    public record FieldIssue(
            @Schema(description = "Nome do campo") String field,
            @Schema(description = "Regra violada") String rule,
            @Schema(description = "Explicação") String message) {}
}
