"""Confere o mapa com os marcadores coletados pelo pytest, sem executar a integração."""

import subprocess
import sys
from pathlib import PurePosixPath
from typing import Literal

import pytest

from tests.integration.lab_round import INTEGRATION, MAP, ROOT, load_map, render_area_table

pytestmark = pytest.mark.contract

# Exceções já coletadas na T4b. Cada parâmetro tem identificação exata.
UNLEVELED_CASES = (
    (
        "test_cleanup_oracle.py",
        "Prova isolada de limpeza contra o Oracle real.",
        (
            "test_dry_run_then_a_person_typing_the_product_removes_only_the_junk_and_keeps_the_seed",
            "test_a_failing_statement_in_the_middle_leaves_the_database_unchanged",
            "test_row_ceiling_exceeded_rolls_back_the_real_transaction",
            "test_forbidden_statement_is_refused_before_any_connection_is_opened",
            "test_wrong_database_password_is_a_cleanup_error_without_leaking_it",
        ),
    ),
    (
        "test_crapi_cli_cycle.py",
        "Ciclo completo da CLI contra crAPI, com medições da V1.12.",
        ("test_v112_crapi_cli_cycle",),
    ),
    (
        "test_crapi_focus_dryrun.py",
        "Ensaio manualmente selecionado do fluxo focado da V1.12.",
        ("test_crapi_foco_ensaio_sem_agente",),
    ),
    (
        "test_guard_benchmark.py",
        "Benchmark da cerca com registro separado de desempenho.",
        ("test_guard_benchmark",),
    ),
    (
        "test_lab_crapi.py",
        "Linha de base de preflight e probe do crAPI.",
        ("test_crapi_preflight_e_probe_pela_cli",),
    ),
    (
        "test_lab_finding_verification.py",
        "Verificação aditiva depois de varredura completa, em três perfis.",
        (
            "test_verificacao_aditiva_apos_varredura_completa[clinica-piloto-vulnerable]",
            "test_verificacao_aditiva_apos_varredura_completa[clinica-piloto-secure]",
            "test_verificacao_aditiva_apos_varredura_completa[vampi-vulnerable]",
        ),
    ),
    (
        "test_lab_jwt_authz.py",
        "Provas específicas de JWT no crAPI e na Clínica Piloto.",
        (
            "test_crapi_jwt_e_achado_pelo_authz",
            "test_clinica_piloto_no_modo_seguro_nao_tem_achado_de_jwt",
        ),
    ),
    (
        "test_lab_mutation_pending.py",
        "Prova específica de retomada com mutação pendente no crAPI.",
        ("test_lab_mutation_pending_nao_reenvia_e_varre_demais",),
    ),
    (
        "test_lab_pilot.py",
        "Casos do ciclo abrangente da Clínica Piloto e verificações de sessão e janela.",
        (
            "test_preflight_is_ready_for_every_account[vulnerable]",
            "test_the_whole_chain_is_created_by_the_mapped_accounts[vulnerable-first]",
            "test_the_whole_chain_is_created_by_the_mapped_accounts[vulnerable-second]",
            "test_each_run_created_exactly_one_row_per_chain_table[vulnerable]",
            "test_unique_values_avoid_409_on_a_second_consecutive_run_without_reset[vulnerable]",
            "test_the_forbidden_notification_endpoint_is_never_called[vulnerable]",
            "test_every_write_in_the_zap_history_carried_the_xsrf_pair[vulnerable]",
            "test_login_traffic_never_enters_the_zap_history[vulnerable]",
            "test_logins_in_one_command_never_exceed_the_declared_rate[vulnerable]",
            "test_cli_and_proxy_audits_agree_and_nothing_left_the_scope[vulnerable]",
            "test_preflight_is_ready_for_every_account[secure]",
            "test_the_whole_chain_is_created_by_the_mapped_accounts[secure-first]",
            "test_the_whole_chain_is_created_by_the_mapped_accounts[secure-second]",
            "test_each_run_created_exactly_one_row_per_chain_table[secure]",
            "test_unique_values_avoid_409_on_a_second_consecutive_run_without_reset[secure]",
            "test_the_forbidden_notification_endpoint_is_never_called[secure]",
            "test_every_write_in_the_zap_history_carried_the_xsrf_pair[secure]",
            "test_login_traffic_never_enters_the_zap_history[secure]",
            "test_logins_in_one_command_never_exceed_the_declared_rate[secure]",
            "test_cli_and_proxy_audits_agree_and_nothing_left_the_scope[secure]",
            "test_a_token_that_expires_mid_run_is_renewed_once_per_request",
            "test_a_closed_window_exits_3_and_nothing_is_sent",
        ),
    ),
    (
        "test_lab_rate_and_inventory.py",
        "Provas específicas de limite de consumo e inventário.",
        (
            "test_crapi_limite_de_consumo_e_inventario_com_e_sem_as_chaves",
            "test_clinica_piloto_no_modo_seguro_com_as_duas_chaves",
        ),
    ),
    (
        "test_lab_stack_lock.py",
        "Prova de contenção da trava de comandos da pilha.",
        ("test_second_command_is_refused_while_the_first_runs_and_works_after_it_ends",),
    ),
    (
        "test_lab_vampi.py",
        "Linha de base da integração com VAmPI, ZAP e proxy reais.",
        (
            "test_preflight_is_ready_with_the_real_zap_and_proxy",
            "test_probe_reaches_all_fourteen_operations_like_the_handcrafted_baseline",
            "test_each_operation_used_the_account_the_profile_maps",
            "test_every_zap_route_request_is_in_the_zap_history_inside_the_run_context",
            "test_login_traffic_goes_through_the_auth_route_and_stays_out_of_the_zap_history",
            "test_proxy_audit_and_cli_audit_agree_and_nothing_left_the_scope",
            "test_a_second_probe_in_the_same_stack_also_completes",
            "test_stop_makes_subsequent_requests_fail_fast_and_is_audited",
        ),
    ),
    (
        "test_proxy_scan_performance.py",
        "Medições dirigidas do desempenho do proxy na V1.8.",
        (
            "test_v18_t4_proxy[clinica-piloto]",
            "test_v18_t4_proxy[vampi]",
        ),
    ),
    (
        "test_scan_performance_matrix.py",
        "Casos de medição da V1.7 fora do recorte já marcado como prova.",
        (
            "test_v17_t3[1-A-clinica-piloto]",
            "test_v17_t3[1-A-vampi]",
            "test_v17_t3[1-B-clinica-piloto]",
            "test_v17_t3[1-B-vampi]",
            "test_v17_t3[2-B-clinica-piloto]",
            "test_v17_t3[2-B-vampi]",
            "test_v17_t3[2-A-clinica-piloto]",
            "test_v17_t3[2-A-vampi]",
            "test_v17_t3[3-A-clinica-piloto]",
            "test_v17_t3[3-A-vampi]",
            "test_v17_t3[3-B-clinica-piloto]",
            "test_v17_t3[3-B-vampi]",
            "test_v17_t3_extra[4-B-clinica-piloto]",
            "test_v17_t3_extra[4-B-vampi]",
            "test_v17_t3_extra[4-A-clinica-piloto]",
            "test_v17_t3_extra[4-A-vampi]",
            "test_v17_t3_extra[5-A-clinica-piloto]",
            "test_v17_t3_extra[5-A-vampi]",
            "test_v17_t3_extra[5-B-clinica-piloto]",
            "test_v17_t3_extra[5-B-vampi]",
            "test_v17_t4[A-clinica-piloto]",
            "test_v17_t4[A-vampi]",
            "test_v17_t4[B-clinica-piloto]",
            "test_v17_t4[B-vampi]",
        ),
    ),
    (
        "test_scan_performance_origins.py",
        "Medições dirigidas de desempenho e origens na V1.8.",
        (
            "test_v18_t4_round3[A-clinica-piloto]",
            "test_v18_t4_round3[A-vampi]",
            "test_v18_t4_round3[B-clinica-piloto]",
            "test_v18_t4_round3[B-vampi]",
        ),
    ),
    (
        "test_scope_revocation.py",
        "Prova específica da revogação durante o probe com proxy real.",
        ("test_revogacao_durante_probe_trava_concessoes_no_proxy",),
    ),
    (
        "test_stack_stale_profile.py",
        "Prova específica de recusa e recuperação da pilha com perfil alterado.",
        (
            "test_editar_campo_livre_com_a_pilha_de_pe_falha_antes_do_primeiro_pedido_e_recriar_cura",
        ),
    ),
)


def _collect_node_ids(marker: str) -> set[str]:
    result = subprocess.run(  # noqa: S603 - apenas coleta, sem shell.
        (sys.executable, "-m", "pytest", INTEGRATION, "-m", marker, "--collect-only", "-q"),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED), (
        result.stdout
    )
    return {
        line.replace("\\", "/")
        for line in result.stdout.splitlines()
        if "::" in line and line.partition("::")[0].endswith(".py")
    }


@pytest.mark.parametrize("level", ["fast", "prova"])
def test_mapa_cobre_todos_os_arquivos_coletados(level: Literal["fast", "prova"]) -> None:
    mapped = set(load_map(MAP).files(level))
    collected = {
        PurePosixPath(node.partition("::")[0]).name for node in _collect_node_ids(f"lab_{level}")
    }
    # A igualdade também detecta arquivos removidos ou marcados no nível errado.
    assert collected == mapped


def test_cada_caso_de_integracao_tem_nivel_ou_excecao_explicita() -> None:
    missing_level = _collect_node_ids(
        "(integration or e2e) and not (lab_fast or lab_prova or lab_full or regressao_dirigida)"
    )
    exceptions = {
        f"{INTEGRATION}/{file}::{case}": reason
        for file, reason, cases in UNLEVELED_CASES
        for case in cases
    }
    added = sorted(missing_level.difference(exceptions))
    obsolete = sorted(exceptions.keys() - missing_level)
    assert missing_level == exceptions.keys(), (
        f"Casos novos sem nível: {added}\nExceções obsoletas: {obsolete}"
    )


def test_tabela_da_escada_reflete_o_mapa() -> None:
    document = ROOT / "docs/desenvolver/escada-de-testes.md"

    assert render_area_table(load_map(MAP)) in document.read_text(encoding="utf-8")
