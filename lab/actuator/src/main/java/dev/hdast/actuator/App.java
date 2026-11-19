package dev.hdast.actuator;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** Alvo de pilha mínimo do spike do Nuclei: uma rota de API e o Actuator exposto de propósito. */
@SpringBootApplication
@RestController
public class App {

  public static void main(String[] args) {
    SpringApplication.run(App.class, args);
  }

  /** Redireciona para um caminho do mesmo host que o escopo não cobre (teste da cerca). */
  @GetMapping("/api/r1")
  public ResponseEntity<Void> redirectToPathOutOfScope() {
    return ResponseEntity.status(302)
        .header("Location", "http://alvo-pilha:8080/zzz-fora-do-escopo")
        .build();
  }

  /** Redireciona para um host fora do escopo (teste da cerca). */
  @GetMapping("/api/r2")
  public ResponseEntity<Void> redirectToHostOutOfScope() {
    return ResponseEntity.status(302).header("Location", "http://fora.invalid/x").build();
  }

  /** Página inicial com uma chave de exemplo da documentação da AWS (valor público e sintético). */
  @GetMapping("/")
  public String home() {
    return "alvo-actuator chave_de_exemplo=AKIAIOSFODNN7EXAMPLE";
  }

  @GetMapping("/api/ping")
  public Map<String, String> ping() {
    return Map.of("status", "ok");
  }
}
