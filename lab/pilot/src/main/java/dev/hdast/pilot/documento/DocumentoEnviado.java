package dev.hdast.pilot.documento;

/** Resposta do envio: o que o alvo guardou (nome já saneado, tamanho em bytes e tipo declarado). */
public record DocumentoEnviado(String nome, long tamanho, String tipo) {
}
