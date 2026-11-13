package dev.hdast.pilot.api;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.exc.InvalidFormatException;
import dev.hdast.pilot.config.Hardening;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/** Converte toda falha no corpo de erro único {code, message, errors}. */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger LOG = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    private final Hardening hardening;

    public GlobalExceptionHandler(Hardening hardening) {
        this.hardening = hardening;
    }

    @ExceptionHandler(ApiException.class)
    ResponseEntity<ErrorBody> handleApi(ApiException e) {
        HttpHeaders headers = new HttpHeaders();
        e.headers().forEach(headers::add);
        return ResponseEntity.status(e.status()).headers(headers)
                .body(new ErrorBody(e.code(), e.getMessage(), e.errors(), Map.of()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ErrorBody> handleBody(MethodArgumentNotValidException e) {
        List<ErrorBody.FieldIssue> issues = e.getBindingResult().getFieldErrors().stream()
                .map(f -> new ErrorBody.FieldIssue(f.getField(), f.getCode(), f.getDefaultMessage()))
                .toList();
        return validation(issues);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<ErrorBody> handleParams(HandlerMethodValidationException e) {
        List<ErrorBody.FieldIssue> issues = new ArrayList<>();
        e.getParameterValidationResults().forEach(r -> r.getResolvableErrors().forEach(err -> {
            String[] codes = err.getCodes();
            String rule = codes == null || codes.length == 0 ? "invalid" : lastSegment(codes[codes.length - 1]);
            issues.add(new ErrorBody.FieldIssue(r.getMethodParameter().getParameterName(), rule,
                    err.getDefaultMessage()));
        }));
        return validation(issues);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ErrorBody> handleUnreadable(HttpMessageNotReadableException e) {
        List<ErrorBody.FieldIssue> issues = List.of();
        String message = "Corpo da requisição ausente ou malformado (JSON inválido).";
        if (e.getCause() instanceof InvalidFormatException ife) {
            String field = ife.getPath().stream().map(JsonMappingException.Reference::getFieldName)
                    .filter(Objects::nonNull).reduce((a, b) -> a + "." + b).orElse("corpo");
            String allowed = ife.getTargetType().isEnum()
                    ? " Valores aceitos: " + Arrays.toString(ife.getTargetType().getEnumConstants()) : "";
            message = "Valor inválido para o campo '" + field + "'." + allowed;
            issues = List.of(new ErrorBody.FieldIssue(field, "format", message));
        }
        return ResponseEntity.badRequest().body(new ErrorBody("CORPO_INVALIDO", message, issues, Map.of()));
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<ErrorBody> handleMismatch(MethodArgumentTypeMismatchException e) {
        String msg = "Parâmetro '" + e.getName() + "' com valor inválido.";
        return ResponseEntity.badRequest().body(new ErrorBody("PARAMETRO_INVALIDO", msg,
                List.of(new ErrorBody.FieldIssue(e.getName(), "type", msg)), Map.of()));
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    ResponseEntity<ErrorBody> handleMissing(MissingServletRequestParameterException e) {
        String msg = "Parâmetro '" + e.getParameterName() + "' é obrigatório.";
        return ResponseEntity.badRequest().body(new ErrorBody("PARAMETRO_INVALIDO", msg,
                List.of(new ErrorBody.FieldIssue(e.getParameterName(), "NotNull", msg)), Map.of()));
    }

    @ExceptionHandler(NoResourceFoundException.class)
    ResponseEntity<ErrorBody> handleNoResource(NoResourceFoundException e) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(ErrorBody.of("NAO_ENCONTRADO", "Recurso não encontrado."));
    }

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    ResponseEntity<ErrorBody> handleMethod(HttpRequestMethodNotSupportedException e) {
        return ResponseEntity.status(HttpStatus.METHOD_NOT_ALLOWED).body(ErrorBody.of("METODO_NAO_PERMITIDO",
                "Método " + e.getMethod() + " não é aceito neste caminho."));
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    ResponseEntity<ErrorBody> handleMedia(HttpMediaTypeNotSupportedException e) {
        return ResponseEntity.status(HttpStatus.UNSUPPORTED_MEDIA_TYPE)
                .body(ErrorBody.of("TIPO_NAO_SUPORTADO", "Use Content-Type: application/json."));
    }

    @ExceptionHandler(AccessDeniedException.class)
    ResponseEntity<ErrorBody> handleDenied(AccessDeniedException e) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(ErrorBody.of("ACESSO_NEGADO", "Seu papel não tem permissão para esta operação."));
    }

    @ExceptionHandler(DuplicateKeyException.class)
    ResponseEntity<ErrorBody> handleDuplicate(DuplicateKeyException e) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(ErrorBody.of("CONFLITO", "Já existe um registro com o mesmo valor único."));
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    ResponseEntity<ErrorBody> handleIntegrity(DataIntegrityViolationException e) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(ErrorBody.of("EM_USO",
                "O registro é referenciado por outros e não pode ser alterado/removido."));
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ErrorBody> handleUnexpected(Exception e) {
        LOG.error("Erro inesperado", e);
        Map<String, Object> extras = new LinkedHashMap<>();
        if (!hardening.applies(Hardening.Item.H2)) {
            StringWriter trace = new StringWriter();
            e.printStackTrace(new PrintWriter(trace));
            extras.put("exception", e.getClass().getName());
            extras.put("detail", String.valueOf(e.getMessage()));
            extras.put("trace", trace.toString());
        }
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ErrorBody("ERRO_INTERNO", "Erro interno do servidor.", List.of(), extras));
    }

    private static ResponseEntity<ErrorBody> validation(List<ErrorBody.FieldIssue> issues) {
        String resumo = issues.stream().map(i -> i.field() + ": " + i.message()).reduce((a, b) -> a + "; " + b)
                .orElse("dados inválidos");
        return ResponseEntity.badRequest()
                .body(new ErrorBody("VALIDACAO", "Requisição inválida. " + resumo, issues, Map.of()));
    }

    private static String lastSegment(String code) {
        int dot = code.indexOf('.');
        return dot < 0 ? code : code.substring(0, dot);
    }
}
