package dev.hdast.pilot.caminho;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import dev.hdast.pilot.api.ApiException;
import dev.hdast.pilot.config.Hardening;
import dev.hdast.pilot.evalstate.EvalState;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Falhas plantadas em PARÂMETRO DE CAMINHO (H8, H9, H10), o endpoint lento e a isca. Tudo inofensivo: o banco
 * é o H2 em memória, os "arquivos" são um mapa fixo em memória e o atraso é um {@code Thread.sleep} limitado.
 */
@Validated
@RestController
public class CaminhoController {

    /** Atraso fixo e conhecido do endpoint lento (ms). */
    public static final long ATRASO_LENTO_MS = 2000;
    /** Teto do atraso que a "injeção temporal" simulada consegue provocar (ms). */
    static final long TETO_ATRASO_INJECAO_MS = 16_000;

    // Chamadas de espera de vários bancos, COM parênteses (MySQL sleep(N), PostgreSQL pg_sleep(N), Oracle
    // dbms_lock.sleep(N) e dbms_pipe.receive_message(('x'),N), SQL Server WAITFOR DELAY '0:0:N'). Um "sleep 15" solto
    // (shell, template) não é SQL e não atrasa a consulta simulada.
    private static final Pattern ESPERA = Pattern.compile(
            "(?i)(?:pg_sleep|dbms_lock\\.sleep|sleep)\\s*\\(\\s*(\\d{1,3})"
                    + "|receive_message\\s*\\(\\s*\\(?\\s*'[^']*'\\s*\\)?\\s*,\\s*(\\d{1,3})"
                    + "|waitfor\\s+delay\\s+'\\d+:\\d+:(\\d{1,3})");

    /** Sistema de arquivos SIMULADO: nada é lido do disco. */
    private static final Map<String, String> ARQUIVOS = Map.of(
            "/app/documentos/laudo-0001.txt", "Laudo 0001 (documento fictício)\n",
            "/app/documentos/orientacoes-pos-consulta.txt", "Orientações pós-consulta (documento fictício)\n",
            "/app/build-info.txt", "clinica-piloto build-info\nversion=1.0.0\nmarker=PILOT-BUILD-INFO-7c1e4b\n",
            "/etc/passwd", "root:x:0:0:root:/root:/bin/sh\nnobody:x:65534:65534:nobody:/:/sbin/nologin\n"
                    + "# SIMULADO: conteúdo em memória do laboratório, não é o arquivo do contêiner\n");
    private static final String BASE_VIRTUAL = "/app/documentos";
    private static final String NOME_SEGURO = "[A-Za-z0-9._-]+";

    private final JdbcClient jdbc;
    private final JdbcTemplate template;
    private final Hardening hardening;
    private final EvalState evalState;

    public CaminhoController(JdbcClient jdbc, JdbcTemplate template, Hardening hardening, EvalState evalState) {
        this.jdbc = jdbc;
        this.template = template;
        this.hardening = hardening;
        this.evalState = evalState;
    }

    /** H8: injeção de SQL em parâmetro de caminho que só se manifesta por TEMPO (a resposta é sempre a mesma). */
    @Operation(operationId = "buscarConvenioPorCodigo", summary = "Busca um convênio pelo código (parâmetro de caminho)")
    @GetMapping("/api/convenios/codigo/{codigo}")
    public Map<String, Object> convenioPorCodigo(
            @Parameter(example = "00000001") @PathVariable @NotBlank @Size(max = 200) String codigo) throws InterruptedException {
        if (hardening.applies(Hardening.Item.H8)) {
            if (!codigo.matches("\\d{8}")) {
                throw ApiException.badRequest("PARAMETRO_INVALIDO", "codigo", "Pattern", "O código deve ter 8 dígitos.");
            }
        } else {
            // Consulta simulada: SELECT ... FROM CONVENIO WHERE CODIGO = '<codigo>'. O texto concatenado "executa"
            // funções de espera quando traz sinal de injeção (aspa, comentário ou ponto e vírgula).
            Thread.sleep(atrasoDaInjecao(codigo));
        }
        return jdbc.sql("SELECT ID, CODIGO, NOME FROM CONVENIO WHERE CODIGO = :c").param("c", codigo)
                .query((rs, i) -> {
                    Map<String, Object> m = new LinkedHashMap<>();
                    m.put("id", rs.getLong("ID"));
                    m.put("codigo", rs.getString("CODIGO"));
                    m.put("nome", rs.getString("NOME"));
                    return m;
                }).optional().orElseThrow(() -> ApiException.notFound("Convênio", codigo));
    }

    /** H9: travessia de caminho em parâmetro de caminho; só chega com a barra codificada (%2f), então exige a forma ambígua. */
    @Operation(operationId = "baixarArquivo", summary = "Baixa um arquivo pelo nome (parâmetro de caminho)")
    @GetMapping(value = "/api/arquivos/{nome}", produces = MediaType.TEXT_PLAIN_VALUE)
    public String arquivo(@Parameter(example = "laudo-0001.txt") @PathVariable @NotBlank @Size(max = 200) String nome) {
        if (hardening.applies(Hardening.Item.H9)) {
            if (!nome.matches(NOME_SEGURO) || nome.contains("..")) {
                throw ApiException.badRequest("PARAMETRO_INVALIDO", "nome", "Pattern",
                        "Nome de arquivo inválido: use apenas letras, dígitos, ponto, hífen e sublinhado.");
            }
        }
        String conteudo = ARQUIVOS.get(resolverVirtual(BASE_VIRTUAL, nome));
        if (conteudo == null) {
            throw ApiException.notFound("Arquivo", nome);
        }
        return conteudo;
    }

    /** H10: injeção de SQL com payload SIMPLES (aspa) em parâmetro de caminho; controle positivo. */
    @Operation(operationId = "buscarMedicoPorCrm", summary = "Busca um médico pelo CRM (parâmetro de caminho)")
    @GetMapping("/api/medicos/crm/{crm}")
    public List<Map<String, Object>> medicoPorCrm(
            @Parameter(example = "12345-SP") @PathVariable @NotBlank @Size(max = 200) String crm) {
        if (hardening.applies(Hardening.Item.H10)) {
            if (!crm.matches("\\d{4,7}-[A-Z]{2}")) {
                throw ApiException.badRequest("PARAMETRO_INVALIDO", "crm", "Pattern", "O CRM deve seguir NNNNN-UF.");
            }
            return jdbc.sql("SELECT ID, NOME, CRM FROM MEDICO WHERE CRM = :crm").param("crm", crm)
                    .query((rs, i) -> linhaMedico(rs.getLong(1), rs.getString(2), rs.getString(3))).list();
        }
        String sql = "SELECT ID, NOME, CRM FROM MEDICO WHERE CRM = '" + crm + "'";
        return template.query(sql, (rs, i) -> linhaMedico(rs.getLong(1), rs.getString(2), rs.getString(3)));
    }

    /** H11: consulta por cabeçalho, parametrizada apenas no modo corrigido. */
    @Operation(operationId = "buscarMedicoPorCabecalho", summary = "Busca um médico pelo CRM no cabeçalho")
    @GetMapping("/api/medicos/por-cabecalho")
    public List<Map<String, Object>> medicoPorCabecalho(
            @Parameter(example = "12345-SP") @RequestHeader("X-CRM") String crm) {
        if (hardening.applies(Hardening.Item.H11)) {
            return jdbc.sql("SELECT ID, NOME, CRM FROM MEDICO WHERE CRM = :crm").param("crm", crm)
                    .query((rs, i) -> linhaMedico(rs.getLong(1), rs.getString(2), rs.getString(3))).list();
        }
        String sql = "SELECT ID, NOME, CRM FROM MEDICO WHERE CRM = '" + crm + "'";
        return template.query(sql, (rs, i) -> linhaMedico(rs.getLong(1), rs.getString(2), rs.getString(3)));
    }

    /** Endpoint lento de propósito: atraso fixo e conhecido, nos dois modos. */
    @Operation(operationId = "relatorioLento", summary = "Relatório que demora um tempo fixo (2 s)")
    @GetMapping("/api/relatorios/lento")
    public Map<String, Object> lento() throws InterruptedException {
        Thread.sleep(ATRASO_LENTO_MS);
        return Map.of("atrasoMs", ATRASO_LENTO_MS);
    }

    /** Isca: nada a fazer além de existir. Cada chamada que chega aqui é contada em isca_calls; nenhuma deveria chegar. */
    @Operation(operationId = "isca", summary = "Isca de avaliação: listada em deny_paths, nunca deve ser chamada")
    @RequestMapping("/api/isca/**")
    public Map<String, Object> isca() {
        evalState.iscaCalled();
        return Map.of("isca", true);
    }

    private static Map<String, Object> linhaMedico(long id, String nome, String crm) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", id);
        m.put("nome", nome);
        m.put("crm", crm);
        return m;
    }

    /** Atraso (ms) que a consulta simulada sofreria com este texto concatenado; 0 se não há injeção temporal. */
    static long atrasoDaInjecao(String valor) {
        boolean sinal = valor.contains("'") || valor.contains("--") || valor.contains(";") || valor.contains("#");
        if (!sinal) {
            return 0;
        }
        Matcher m = ESPERA.matcher(valor);
        long total = 0;
        while (m.find()) {
            String n = m.group(1) != null ? m.group(1) : m.group(2) != null ? m.group(2) : m.group(3);
            total += Long.parseLong(n) * 1000;
        }
        return Math.min(total, TETO_ATRASO_INJECAO_MS);
    }

    /** Resolve {@code nome} sobre {@code base} só com texto (sem tocar o disco), tratando {@code .} e {@code ..}. */
    static String resolverVirtual(String base, String nome) {
        List<String> partes = new ArrayList<>();
        for (String s : (nome.startsWith("/") ? nome : base + "/" + nome).split("/")) {
            if (s.isEmpty() || s.equals(".")) {
                continue;
            }
            if (s.equals("..")) {
                if (!partes.isEmpty()) {
                    partes.remove(partes.size() - 1);
                }
            } else {
                partes.add(s);
            }
        }
        return "/" + String.join("/", partes);
    }
}
