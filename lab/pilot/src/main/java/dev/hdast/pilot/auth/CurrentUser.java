package dev.hdast.pilot.auth;

import dev.hdast.pilot.api.ApiException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class CurrentUser {

    public AuthenticatedUser get() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        return (AuthenticatedUser) auth.getPrincipal();
    }

    public String username() {
        return get().username();
    }

    /** Equipe (médico/admin) vê tudo; paciente só o próprio cadastro. Sempre aplicado. */
    public void requireOwnerOrStaff(long pacienteId) {
        AuthenticatedUser u = get();
        if (!u.isStaff() && (u.pacienteId() == null || u.pacienteId() != pacienteId)) {
            throw ApiException.forbidden("Você só pode acessar os seus próprios registros.");
        }
    }
}
