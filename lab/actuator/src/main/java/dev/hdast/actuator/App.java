package dev.hdast.actuator;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** Alvo de laboratório mínimo da prova do Nuclei: uma rota de API e o Actuator exposto de propósito. */
@SpringBootApplication
@RestController
public class App {

  public static void main(String[] args) {
    SpringApplication.run(App.class, args);
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
