package dev.hdast.pilot;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

/** Comportamentos funcionais que valem nos dois modos (padrão e corrigido). As subclasses fixam o modo. */
abstract class FunctionalBehaviour extends ApiTestBase {

    private String adminToken() throws Exception { return login(ADMIN); }

    private long id(Reply r) { return r.body().get("id").asLong(); }

    private JsonNode firstError(Reply r) { return r.body().get("errors").get(0); }

    // ---------------------------------------------------------------- autenticação

    @Test
    void login_devolveJwtComValidadeConfiguradaQuandoCredenciaisValidas() throws Exception {
        Reply r = send(MockMvcRequestBuilders.post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("username", ADMIN, "password", PASSWORDS.get(ADMIN)))));
        assertThat(r.status()).isEqualTo(200);
        assertThat(r.body().get("access_token").asText()).isNotBlank();
        assertThat(r.body().get("token_type").asText()).isEqualTo("Bearer");
        assertThat(r.body().get("expires_in").asLong()).isEqualTo(300);
        assertThat(r.body().get("papel").asText()).isEqualTo("admin");
    }

    @Test
    void login_devolve401QuandoSenhaErrada() throws Exception {
        Reply r = send(MockMvcRequestBuilders.post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("username", ADMIN, "password", "errada"))));
        assertThat(r.status()).isEqualTo(401);
        assertThat(r.body().get("code").asText()).isEqualTo("CREDENCIAIS_INVALIDAS");
    }

    @Test
    void login_devolve400NomeandoOCampoQuandoSenhaEmBranco() throws Exception {
        Reply r = send(MockMvcRequestBuilders.post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"x\",\"password\":\"\"}"));
        assertThat(r.status()).isEqualTo(400);
        assertThat(firstError(r).get("field").asText()).isEqualTo("password");
        assertThat(firstError(r).get("rule").asText()).isEqualTo("NotBlank");
    }

    @Test
    void endpointProtegido_devolve401SemToken() throws Exception {
        Reply r = get(null, "/api/convenios");
        assertThat(r.status()).isEqualTo(401);
        assertThat(r.body().get("code").asText()).isEqualTo("NAO_AUTENTICADO");
    }

    @Test
    void endpointProtegido_devolve401ComTokenInvalido() throws Exception {
        Reply r = get("isto.nao.e-um-jwt", "/api/convenios");
        assertThat(r.status()).isEqualTo(401);
        assertThat(r.body().get("code").asText()).isEqualTo("TOKEN_INVALIDO");
    }

    @Test
    void papelPaciente_nao_criaConvenio() throws Exception {
        Reply r = post(login(PACIENTE_A), "/api/convenios", convenioBody("90000001"));
        assertThat(r.status()).isEqualTo(403);
        assertThat(r.body().get("code").asText()).isEqualTo("ACESSO_NEGADO");
    }

    // ---------------------------------------------------------------- XSRF

    @Test
    void get_csrf_defineCookieComOMesmoValorDoCorpo() throws Exception {
        var res = mvc.perform(MockMvcRequestBuilders.get("/api/csrf")).andReturn().getResponse();
        Cookie cookie = res.getCookie("XSRF-TOKEN");
        assertThat(cookie).isNotNull();
        JsonNode body = json.readTree(res.getContentAsString());
        assertThat(body.get("token").asText()).isEqualTo(cookie.getValue());
        assertThat(body.get("headerName").asText()).isEqualTo("X-XSRF-TOKEN");
        assertThat(cookie.isHttpOnly()).isFalse();
    }

    @Test
    void escrita_devolve403XsrfSemOCabecalho() throws Exception {
        String token = adminToken();
        Reply r = send(MockMvcRequestBuilders.post("/api/convenios").header("Authorization", "Bearer " + token)
                .contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(convenioBody("90000002"))));
        assertThat(r.status()).isEqualTo(403);
        assertThat(r.body().get("code").asText()).isEqualTo("XSRF_INVALIDO");
        assertThat(r.body().get("message").asText()).contains("X-XSRF-TOKEN");
    }

    @Test
    void escrita_devolve403XsrfQuandoCabecalhoDifereDoCookie() throws Exception {
        String token = adminToken();
        Reply r = send(MockMvcRequestBuilders.post("/api/convenios").header("Authorization", "Bearer " + token)
                .cookie(new Cookie("XSRF-TOKEN", xsrfToken())).header("X-XSRF-TOKEN", "outro-valor")
                .contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(convenioBody("90000003"))));
        assertThat(r.status()).isEqualTo(403);
        assertThat(r.body().get("code").asText()).isEqualTo("XSRF_INVALIDO");
    }

    @Test
    void escrita_passaComParXsrfValido() throws Exception {
        Reply r = post(adminToken(), "/api/convenios", convenioBody("90000004"));
        assertThat(r.status()).isEqualTo(201);
    }

    // ---------------------------------------------------------------- validação e unicidade

    @Test
    void convenio_codigoComTamanhoErrado_devolve400NomeandoCampoERegra() throws Exception {
        Reply r = post(adminToken(), "/api/convenios", convenioBody("1234567"));
        assertThat(r.status()).isEqualTo(400);
        assertThat(r.body().get("code").asText()).isEqualTo("VALIDACAO");
        assertThat(firstError(r).get("field").asText()).isEqualTo("codigo");
        assertThat(firstError(r).get("rule").asText()).isEqualTo("Pattern");
    }

    @Test
    void convenio_codigoNaoNumerico_devolve400() throws Exception {
        Reply r = post(adminToken(), "/api/convenios", convenioBody("ABCD1234"));
        assertThat(r.status()).isEqualTo(400);
        assertThat(firstError(r).get("field").asText()).isEqualTo("codigo");
    }

    @Test
    void convenio_codigoDuplicado_devolve409NomeandoCampo() throws Exception {
        String token = adminToken();
        assertThat(post(token, "/api/convenios", convenioBody("90000005")).status()).isEqualTo(201);
        Reply r = post(token, "/api/convenios", convenioBody("90000005"));
        assertThat(r.status()).isEqualTo(409);
        assertThat(r.body().get("code").asText()).isEqualTo("CONFLITO");
        assertThat(firstError(r).get("field").asText()).isEqualTo("codigo");
    }

    @Test
    void convenio_coparticipacaoForaDaFaixa_devolve400() throws Exception {
        Map<String, Object> body = Map.of("codigo", "90000006", "nome", "Plano X", "tipo", "PUBLICO",
                "coparticipacaoPercentual", 101);
        Reply r = post(adminToken(), "/api/convenios", body);
        assertThat(r.status()).isEqualTo(400);
        assertThat(firstError(r).get("field").asText()).isEqualTo("coparticipacaoPercentual");
        assertThat(firstError(r).get("rule").asText()).isEqualTo("Max");
    }

    @Test
    void convenio_tipoForaDoEnum_devolve400ListandoValoresAceitos() throws Exception {
        Reply r = post(adminToken(), "/api/convenios",
                Map.of("codigo", "90000007", "nome", "Plano X", "tipo", "VIP", "coparticipacaoPercentual", 5));
        assertThat(r.status()).isEqualTo(400);
        assertThat(r.body().get("code").asText()).isEqualTo("CORPO_INVALIDO");
        assertThat(r.body().get("message").asText()).contains("tipo").contains("INDIVIDUAL");
    }

    @Test
    void medico_crmDuplicado_devolve409() throws Exception {
        Map<String, Object> body = Map.of("nome", "Dr. Teste", "crm", "99999-MG", "especialidade", "PEDIATRIA");
        String token = adminToken();
        assertThat(post(token, "/api/medicos", body).status()).isEqualTo(201);
        Reply r = post(token, "/api/medicos", body);
        assertThat(r.status()).isEqualTo(409);
        assertThat(firstError(r).get("field").asText()).isEqualTo("crm");
    }

    @Test
    void paciente_cpfComDigitoVerificadorInvalido_devolve400() throws Exception {
        Reply r = post(adminToken(), "/api/pacientes", pacienteBody("12345678900", "a@example.test", 1));
        assertThat(r.status()).isEqualTo(400);
        assertThat(firstError(r).get("field").asText()).isEqualTo("cpf");
        assertThat(firstError(r).get("rule").asText()).isEqualTo("Cpf");
    }

    @Test
    void paciente_cpfMalformado_devolve400ComRegraPattern() throws Exception {
        Reply r = post(adminToken(), "/api/pacientes", pacienteBody("123", "b@example.test", 1));
        assertThat(r.status()).isEqualTo(400);
        assertThat(firstError(r).get("rule").asText()).isEqualTo("Pattern");
    }

    @Test
    void paciente_cpfEEmailDuplicados_devolvem409NomeandoOCampo() throws Exception {
        String token = adminToken();
        assertThat(post(token, "/api/pacientes", pacienteBody("39053344705", "c@example.test", 1)).status()).isEqualTo(201);
        Reply cpf = post(token, "/api/pacientes", pacienteBody("39053344705", "d@example.test", 1));
        assertThat(cpf.status()).isEqualTo(409);
        assertThat(firstError(cpf).get("field").asText()).isEqualTo("cpf");
        Reply email = post(token, "/api/pacientes", pacienteBody("12345678909", "c@example.test", 1));
        assertThat(email.status()).isEqualTo(409);
        assertThat(firstError(email).get("field").asText()).isEqualTo("email");
    }

    @Test
    void paciente_nascimentoNoFuturo_devolve400() throws Exception {
        Map<String, Object> body = new java.util.HashMap<>(pacienteBody("39053344705", "e@example.test", 1));
        body.put("dataNascimento", "2999-01-01");
        Reply r = post(adminToken(), "/api/pacientes", body);
        assertThat(r.status()).isEqualTo(400);
        assertThat(firstError(r).get("field").asText()).isEqualTo("dataNascimento");
        assertThat(firstError(r).get("rule").asText()).isEqualTo("Past");
    }

    @Test
    void paciente_sexoForaDoEnum_devolve400() throws Exception {
        Map<String, Object> body = new java.util.HashMap<>(pacienteBody("39053344705", "f@example.test", 1));
        body.put("sexo", "X");
        Reply r = post(adminToken(), "/api/pacientes", body);
        assertThat(r.status()).isEqualTo(400);
        assertThat(r.body().get("message").asText()).contains("sexo");
    }

    @Test
    void consulta_dataNoPassado_devolve400ComRegraFuture() throws Exception {
        Map<String, Object> body = new java.util.HashMap<>(consultaBody(1, 1));
        body.put("dataHora", "2001-01-01T10:00:00");
        Reply r = post(login(MEDICO), "/api/consultas", body);
        assertThat(r.status()).isEqualTo(400);
        assertThat(firstError(r).get("field").asText()).isEqualTo("dataHora");
        assertThat(firstError(r).get("rule").asText()).isEqualTo("Future");
    }

    @Test
    void consulta_valorAcimaDoMaximo_devolve400() throws Exception {
        Map<String, Object> body = new java.util.HashMap<>(consultaBody(1, 1));
        body.put("valor", 5000.01);
        Reply r = post(login(MEDICO), "/api/consultas", body);
        assertThat(r.status()).isEqualTo(400);
        assertThat(firstError(r).get("field").asText()).isEqualTo("valor");
    }

    @Test
    void receita_duracaoForaDaFaixa_devolve400() throws Exception {
        Reply r = post(login(MEDICO), "/api/receitas",
                Map.of("consultaId", 1, "medicamento", "Dipirona", "posologia", "1 por dia", "duracaoDias", 400));
        assertThat(r.status()).isEqualTo(400);
        assertThat(firstError(r).get("field").asText()).isEqualTo("duracaoDias");
        assertThat(firstError(r).get("rule").asText()).isEqualTo("Max");
    }

    @Test
    void paginacao_tamanhoAcimaDoMaximo_devolve400NomeandoOParametro() throws Exception {
        Reply r = get(adminToken(), "/api/pacientes?size=1000");
        assertThat(r.status()).isEqualTo(400);
        assertThat(firstError(r).get("field").asText()).isEqualTo("size");
    }

    @Test
    void idNaoNumerico_devolve400() throws Exception {
        Reply r = get(adminToken(), "/api/convenios/abc");
        assertThat(r.status()).isEqualTo(400);
        assertThat(r.body().get("code").asText()).isEqualTo("PARAMETRO_INVALIDO");
    }

    // ---------------------------------------------------------------- encadeamento e propriedade

    @Test
    void fluxoCompleto_convenioPacienteConsultaReceita() throws Exception {
        String admin = adminToken();
        long convenio = id(post(admin, "/api/convenios", convenioBody("90000010")));
        long paciente = id(post(admin, "/api/pacientes", pacienteBody("39053344705", "fluxo@example.test", convenio)));
        long consulta = id(post(login(MEDICO), "/api/consultas", consultaBody(paciente, 1)));
        Reply receita = post(login(MEDICO), "/api/receitas",
                Map.of("consultaId", consulta, "medicamento", "Dipirona", "posologia", "1 comprimido", "duracaoDias", 5));
        assertThat(receita.status()).isEqualTo(201);
        assertThat(receita.body().get("consultaId").asLong()).isEqualTo(consulta);
        assertThat(get(admin, "/api/consultas/" + consulta + "/receitas").body()).hasSize(1);
    }

    @Test
    void paciente_comConvenioInexistente_devolve422() throws Exception {
        Reply r = post(adminToken(), "/api/pacientes", pacienteBody("39053344705", "g@example.test", 987654));
        assertThat(r.status()).isEqualTo(422);
        assertThat(r.body().get("code").asText()).isEqualTo("REFERENCIA_INEXISTENTE");
        assertThat(firstError(r).get("field").asText()).isEqualTo("convenioId");
    }

    @Test
    void consulta_comPacienteOuMedicoInexistente_devolve422() throws Exception {
        String medico = login(MEDICO);
        assertThat(post(medico, "/api/consultas", consultaBody(987654, 1)).status()).isEqualTo(422);
        assertThat(post(medico, "/api/consultas", consultaBody(1, 987654)).status()).isEqualTo(422);
    }

    @Test
    void receita_comConsultaInexistente_devolve422() throws Exception {
        Reply r = post(login(MEDICO), "/api/receitas",
                Map.of("consultaId", 987654, "medicamento", "Dipirona", "posologia", "1", "duracaoDias", 5));
        assertThat(r.status()).isEqualTo(422);
    }

    @Test
    void buscaPorIdInexistente_devolve404() throws Exception {
        assertThat(get(adminToken(), "/api/pacientes/987654").status()).isEqualTo(404);
        assertThat(get(adminToken(), "/api/consultas/987654").status()).isEqualTo(404);
    }

    @Test
    void paciente_nao_vePacienteDeOutro() throws Exception {
        Reply r = get(login(PACIENTE_A), "/api/pacientes/2");
        assertThat(r.status()).isEqualTo(403);
        assertThat(get(login(PACIENTE_A), "/api/pacientes/1").status()).isEqualTo(200);
    }

    @Test
    void paciente_listaSomenteOProprioCadastro() throws Exception {
        Reply r = get(login(PACIENTE_A), "/api/pacientes");
        assertThat(r.body().get("total").asLong()).isEqualTo(1);
        assertThat(r.body().get("items").get(0).get("id").asLong()).isEqualTo(1);
    }

    @Test
    void paciente_agendaParaSiMasNaoParaOutro() throws Exception {
        String a = login(PACIENTE_A);
        assertThat(post(a, "/api/consultas", consultaBody(1, 1)).status()).isEqualTo(201);
        assertThat(post(a, "/api/consultas", consultaBody(2, 1)).status()).isEqualTo(403);
    }

    @Test
    void consulta_statusSoMudaUmaVezEPacienteSoCancela() throws Exception {
        String a = login(PACIENTE_A);
        assertThat(write("PATCH", a, "/api/consultas/1/status", Map.of("status", "REALIZADA")).status()).isEqualTo(403);
        assertThat(write("PATCH", a, "/api/consultas/1/status", Map.of("status", "CANCELADA")).status()).isEqualTo(200);
        Reply again = write("PATCH", a, "/api/consultas/1/status", Map.of("status", "CANCELADA"));
        assertThat(again.status()).isEqualTo(409);
        assertThat(again.body().get("code").asText()).isEqualTo("TRANSICAO_INVALIDA");
        Reply receita = post(login(MEDICO), "/api/receitas",
                Map.of("consultaId", 1, "medicamento", "Dipirona", "posologia", "1", "duracaoDias", 5));
        assertThat(receita.body().get("code").asText()).isEqualTo("CONSULTA_CANCELADA");
    }

    @Test
    void convenioEmUso_naoPodeSerRemovido() throws Exception {
        Reply r = write("DELETE", adminToken(), "/api/convenios/1", null);
        assertThat(r.status()).isEqualTo(409);
        assertThat(r.body().get("code").asText()).isEqualTo("EM_USO");
    }

    // ---------------------------------------------------------------- notificações e estado de avaliação

    @Test
    void notificacao_incrementaOContadorENadaMais() throws Exception {
        Reply r = post(login(MEDICO), "/api/notificacoes/enviar",
                Map.of("destinatario", "paciente@example.test", "canal", "EMAIL", "mensagem", "Lembrete"));
        assertThat(r.status()).isEqualTo(202);
        assertThat(r.body().get("totalEnviadas").asLong()).isEqualTo(1);
        assertThat(evalState().get("notifications_sent").asLong()).isEqualTo(1);
    }

    @Test
    void estadoDeAvaliacao_contaRequisicoesPorTemplateELinhasCriadas() throws Exception {
        String admin = adminToken();
        post(admin, "/api/convenios", convenioBody("90000020"));
        get(admin, "/api/convenios/1");
        get(admin, "/api/convenios/2");
        JsonNode state = evalState();
        assertThat(state.get("requests_by_endpoint").get("GET /api/convenios/{id}").asLong()).isEqualTo(2);
        assertThat(state.get("requests_by_endpoint").get("POST /api/convenios").asLong()).isEqualTo(1);
        assertThat(state.get("rows_created_since_startup").get("convenio").asLong()).isEqualTo(1);
        assertThat(state.get("rows").get("convenio").asLong()).isEqualTo(2);
        assertThat(state.get("rows_created_total").asLong()).isEqualTo(1);
    }

    @Test
    void reset_restauraOEstadoDeSemente() throws Exception {
        String admin = adminToken();
        post(admin, "/api/convenios", convenioBody("90000021"));
        post(login(MEDICO), "/api/notificacoes/enviar",
                Map.of("destinatario", "x@example.test", "canal", "SMS", "mensagem", "Oi"));
        JsonNode after = json.readTree(mvc.perform(MockMvcRequestBuilders.post("/internal/eval/reset")
                .with(onManagementPort())).andReturn().getResponse().getContentAsString());
        assertThat(after.get("rows_created_total").asLong()).isZero();
        assertThat(after.get("notifications_sent").asLong()).isZero();
        assertThat(after.get("rows").get("convenio").asLong()).isEqualTo(1);
    }

    @Test
    void estadoDeAvaliacao_soExisteNaPortaDeGestao() throws Exception {
        assertThat(mvc.perform(MockMvcRequestBuilders.get("/internal/eval/state")).andReturn().getResponse().getStatus())
                .isEqualTo(404);
        assertThat(mvc.perform(MockMvcRequestBuilders.get("/api/saude").with(onManagementPort()))
                .andReturn().getResponse().getStatus()).isEqualTo(404);
        assertThat(mvc.perform(MockMvcRequestBuilders.get("/internal/eval/state").with(onManagementPort()))
                .andReturn().getResponse().getStatus()).isEqualTo(200);
    }

    @Test
    void openapi_ePublicoENaoMencionaOEstadoDeAvaliacao() throws Exception {
        String doc = mvc.perform(MockMvcRequestBuilders.get("/v3/api-docs")).andReturn().getResponse()
                .getContentAsString();
        assertThat(doc).contains("/api/notificacoes/enviar").doesNotContain("/internal");
    }

    private JsonNode evalState() throws Exception {
        return json.readTree(mvc.perform(MockMvcRequestBuilders.get("/internal/eval/state").with(onManagementPort()))
                .andReturn().getResponse().getContentAsString());
    }

    protected static org.springframework.test.web.servlet.request.RequestPostProcessor onManagementPort() {
        return request -> {
            request.setLocalPort(9091);
            return request;
        };
    }
}
