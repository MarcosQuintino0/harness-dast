package dev.hdast.pilot.documento;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

import dev.hdast.pilot.api.ApiException;
import dev.hdast.pilot.config.Hardening;
import dev.hdast.pilot.config.PilotProperties;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class DocumentoController {

    private final Path base;
    private final Hardening hardening;
    private final DocumentoEnvioService envio;

    public DocumentoController(PilotProperties props, Hardening hardening, DocumentoEnvioService envio) {
        this.base = Path.of(props.documentsDir()).toAbsolutePath().normalize();
        this.hardening = hardening;
        this.envio = envio;
    }

    @Operation(operationId = "enviarDocumento",
            summary = "Envia um arquivo pequeno (texto, CSV, JSON ou PNG, até 64 KiB); guardado só em memória")
    @io.swagger.v3.oas.annotations.parameters.RequestBody(content = @io.swagger.v3.oas.annotations.media.Content(
            mediaType = "multipart/form-data",
            encoding = @io.swagger.v3.oas.annotations.media.Encoding(name = "arquivo",
                    contentType = "text/plain, text/csv, application/json, image/png")))
    @PostMapping(value = "/api/documentos/enviar", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public DocumentoEnviado enviar(@RequestPart("arquivo") MultipartFile arquivo,
                                   @RequestPart(value = "descricao", required = false) String descricao)
            throws IOException {
        return envio.guardar(arquivo.getOriginalFilename(), arquivo.getContentType(), arquivo.getBytes(), descricao);
    }

    @Operation(operationId = "listarDocumentos", summary = "Lista os documentos disponíveis para download")
    @GetMapping("/api/documentos")
    public List<String> listar() throws IOException {
        try (Stream<Path> files = Files.list(base)) {
            return files.filter(Files::isRegularFile).map(p -> p.getFileName().toString()).sorted().toList();
        }
    }

    @Operation(operationId = "baixarDocumento", summary = "Baixa um documento pelo nome do arquivo")
    @GetMapping(value = "/api/documentos/download", produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public byte[] baixar(@RequestParam @NotBlank @Size(max = 200) String arquivo) throws IOException {
        Path alvo = base.resolve(arquivo);
        if (hardening.applies(Hardening.Item.H4)) {
            alvo = alvo.normalize();
            if (!alvo.startsWith(base) || !arquivo.matches("[A-Za-z0-9._-]+")) {
                throw ApiException.badRequest("PARAMETRO_INVALIDO", "arquivo", "Pattern",
                        "Nome de arquivo inválido: use apenas letras, dígitos, ponto, hífen e sublinhado.");
            }
        }
        try {
            return Files.readAllBytes(alvo);
        } catch (NoSuchFileException e) {
            throw ApiException.notFound("Documento", arquivo);
        }
    }
}
