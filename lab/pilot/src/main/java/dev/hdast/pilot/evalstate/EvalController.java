package dev.hdast.pilot.evalstate;

import java.util.Map;

import dev.hdast.pilot.config.Hardening;
import dev.hdast.pilot.seed.SeedService;
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

/** Estado da avaliação. Fora do OpenAPI e servido só na porta de gestão (ver EdgeFilter). */
@Hidden
@RestController
public class EvalController {

    private final EvalState state;
    private final SeedService seed;
    private final Hardening hardening;

    public EvalController(EvalState state, SeedService seed, Hardening hardening) {
        this.state = state;
        this.seed = seed;
        this.hardening = hardening;
    }

    @GetMapping("/internal/eval/state")
    public Map<String, Object> state() {
        return state.snapshot(hardening.isVulnerableMode());
    }

    @PostMapping("/internal/eval/reset")
    public Map<String, Object> reset() {
        seed.reset();
        return state.snapshot(hardening.isVulnerableMode());
    }
}
