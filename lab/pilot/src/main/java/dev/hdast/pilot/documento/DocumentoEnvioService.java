package dev.hdast.pilot.documento;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Locale;
import java.util.Set;

import dev.hdast.pilot.api.ApiException;
import org.springframework.stereotype.Service;

/**
 * Envio de arquivo do laboratório. Existe só para provar o alcance do multipart no harness-dast: sem falha plantada,
 * idêntico nos dois modos. Guarda os últimos envios SÓ EM MEMÓRIA (nada vai para o disco, nem para a pasta de
 * documentos) e saneia o nome antes de guardar.
 */
@Service
public class DocumentoEnvioService {

    /** Tipos aceitos (os quatro arquivos sintéticos do harness-dast). */
    static final Set<String> TIPOS_ACEITOS = Set.of("text/plain", "text/csv", "application/json", "image/png");
    static final int TAMANHO_MAXIMO = 64 * 1024;
    private static final int MAX_GUARDADOS = 20;
    private static final int MAX_NOME = 100;

    private final Deque<Guardado> guardados = new ArrayDeque<>();

    private record Guardado(String nome, String tipo, byte[] bytes) {
    }

    /** Valida, guarda em memória e devolve o resumo. Levanta 400 (vazio, grande, descrição longa) ou 415 (tipo). */
    public DocumentoEnviado guardar(String nomeOriginal, String tipoDeclarado, byte[] bytes, String descricao) {
        if (descricao != null && descricao.length() > 200) {
            throw ApiException.badRequest("VALIDACAO", "descricao", "Size", "descricao: no máximo 200 caracteres");
        }
        if (bytes.length == 0) {
            throw ApiException.badRequest("VALIDACAO", "arquivo", "NotEmpty", "arquivo: não pode ser vazio");
        }
        if (bytes.length > TAMANHO_MAXIMO) {
            throw ApiException.badRequest("VALIDACAO", "arquivo", "Size",
                    "arquivo: no máximo " + TAMANHO_MAXIMO + " bytes");
        }
        String tipo = tipoBase(tipoDeclarado);
        if (!TIPOS_ACEITOS.contains(tipo)) {
            throw ApiException.unsupportedMediaType("TIPO_ARQUIVO_NAO_SUPORTADO",
                    "Tipo de arquivo não aceito. Aceitos: text/plain, text/csv, application/json, image/png.");
        }
        String nome = sanear(nomeOriginal);
        synchronized (guardados) {
            if (guardados.size() >= MAX_GUARDADOS) {
                guardados.removeFirst();
            }
            guardados.addLast(new Guardado(nome, tipo, bytes.clone()));
        }
        return new DocumentoEnviado(nome, bytes.length, tipo);
    }

    /** Tipo sem parâmetros e em minúsculas ({@code Text/Plain; charset=x} vira {@code text/plain}). */
    static String tipoBase(String declarado) {
        if (declarado == null) {
            return "";
        }
        int ponto = declarado.indexOf(';');
        return (ponto < 0 ? declarado : declarado.substring(0, ponto)).trim().toLowerCase(Locale.ROOT);
    }

    /** Fica só o último trecho do nome e só caracteres seguros; nunca vira caminho. */
    static String sanear(String original) {
        String base = original == null ? "" : original;
        int corte = Math.max(base.lastIndexOf('/'), base.lastIndexOf('\\'));
        base = corte < 0 ? base : base.substring(corte + 1);
        base = base.replaceAll("[^A-Za-z0-9._-]", "_");
        if (base.length() > MAX_NOME) {
            base = base.substring(0, MAX_NOME);
        }
        return base.isBlank() || base.chars().allMatch(c -> c == '.') ? "arquivo" : base;
    }
}
