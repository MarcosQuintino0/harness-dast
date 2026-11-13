package dev.hdast.pilot.auth;

/** Usuário da requisição atual (carregado do banco a cada chamada). */
public record AuthenticatedUser(long id, String username, Papel papel, Long pacienteId, Long medicoId) {

    public boolean isStaff() {
        return papel != Papel.PACIENTE;
    }
}
