package dev.hdast.pilot.notificacao;

import dev.hdast.pilot.auth.CurrentUser;
import dev.hdast.pilot.evalstate.EvalState;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** Simula o envio de SMS/e-mail: só incrementa um contador e registra no log. Nada sai da máquina. */
@RestController
public class NotificacaoController {

    private static final Logger LOG = LoggerFactory.getLogger(NotificacaoController.class);

    public enum Canal { SMS, EMAIL }

    public record NotificacaoRequest(
            @Schema(description = "Telefone ou e-mail do destinatário") @NotBlank @Size(max = 120) String destinatario,
            @NotNull Canal canal,
            @NotBlank @Size(max = 300) String mensagem) {}

    public record NotificacaoResponse(String status, long totalEnviadas) {}

    private final EvalState state;
    private final CurrentUser current;

    public NotificacaoController(EvalState state, CurrentUser current) {
        this.state = state;
        this.current = current;
    }

    @Operation(operationId = "enviarNotificacao", summary = "Envia uma notificação ao paciente (SMS ou e-mail)")
    @PostMapping("/api/notificacoes/enviar")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public NotificacaoResponse enviar(@Valid @RequestBody NotificacaoRequest request) {
        long total = state.notificationSent();
        LOG.warn("NOTIFICACAO SIMULADA #{} canal={} por={} (nada foi enviado)", total, request.canal(), current.username());
        return new NotificacaoResponse("ENVIADA", total);
    }
}
