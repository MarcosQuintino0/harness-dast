"""Controles seguros B de CORS, autorização e negative com escrita no laboratório."""

import time
from pathlib import Path

import pytest

from tests.integration import test_lab_authz as authz_checks
from tests.integration import test_lab_negative as negative_checks
from tests.integration.lab_support import (
    PILOT_PROFILE,
    VAMPI_OPENAPI,
    VAMPI_PROFILE,
    LabCli,
    require_docker,
    run_audit,
)
from tests.integration.run_support import record_metrics, throwaway_pilot_env
from tests.integration.safe_mode_support import (
    artifact,
    audit_summary,
    current_audit,
    enable_proxy,
    secret_hits,
    start_and_probe,
)
from tests.integration.test_lab_vampi import SEEDED

pytestmark = [pytest.mark.integration, pytest.mark.lab_prova]
PILOT_BASE = "http://clinica-piloto:8080"
VAMPI_BASE = "http://vampi:5000"


@pytest.mark.parametrize("product", ["clinica-piloto", "vampi"])
def test_cors_seguro_b(tmp_path: Path, product: str) -> None:
    """Coleta e encerra a mesma pilha; o ciclo indivisível justifica mais de 40 linhas."""
    require_docker()
    env = throwaway_pilot_env()
    env.update(SEEDED)
    cli = LabCli(tmp_path, env)
    if product == "clinica-piloto":
        folder = cli.install_product(product, PILOT_PROFILE)
        operation, base = "obterPerfil", PILOT_BASE
    else:
        folder = cli.install_product(product, VAMPI_PROFILE, (VAMPI_OPENAPI,))
        operation, base = "api_views.users.me", VAMPI_BASE
    enable_proxy(folder / "target.yml")
    try:
        run_id, outputs = start_and_probe(cli, product, "--only", operation)
        before = len(current_audit(cli))
        done = cli.run("authz", product, "--run", run_id, "--check", "cors", timeout=900)
        assert done.code == 0, done.stdout + done.stderr
        result = artifact(cli, run_id, "authz.json")
        summary = next(row for row in result["checks"] if row["check"] == "cors")
        findings = [row for row in result["findings"] if row["technique"] == "authz_cors"]
        sent = [
            row
            for row in run_audit(cli, run_id)
            if row["phase"] == "decision" and str(row["operation_id"]).startswith("authz:cors:")
        ]
        rows = current_audit(cli)[before:]
        hits = secret_hits(cli, base, [*outputs, done.stdout, done.stderr])
        record_metrics(
            f"v18-b-cors-{product}-secure",
            {
                "product": product,
                "mode": "secure",
                "pacing": "proxy",
                "run_id": run_id,
                "summary": summary,
                "findings_count": len(findings),
                "secret_hit_count": len(hits),
                **audit_summary(rows),
            },
        )
        assert summary["tested"] >= 1
        assert 1 <= len(sent) <= 5
        assert all(row["method"] == "GET" and row["decision"] == "allowed" for row in sent)
        assert len(findings) <= 2
        if product == "clinica-piloto":
            assert not findings
        assert not [row for row in rows if row["decision"] != "allow"]
        assert not hits
    finally:
        cli.stack_down()


def test_authz_com_matriz_e_escrita_seguro_b(tmp_path: Path) -> None:
    """Agrupa asserts do contrato e coleta antes do reset; o ciclo supera 40 linhas."""
    require_docker()
    cli = LabCli(tmp_path, throwaway_pilot_env())
    authz_checks._install_with_writes(cli)
    enable_proxy(cli.products / "clinica-piloto" / "target.yml")
    try:
        run_id, outputs = start_and_probe(cli, "clinica-piloto")
        done = cli.run("authz", "clinica-piloto", "--run", run_id, timeout=1500)
        assert done.code == 0, done.stdout + done.stderr
        result = artifact(cli, run_id, "authz.json")
        rows = current_audit(cli)
        hits = secret_hits(cli, PILOT_BASE, [*outputs, done.stdout, done.stderr])
        lab = authz_checks.AuthzLab("secure", result, run_audit(cli, run_id), rows, hits, {})
        record_metrics(
            "v18-b-authz-clinica-piloto-secure",
            {
                "run_id": run_id,
                "pacing": "proxy",
                "secret_hit_count": len(hits),
                **audit_summary(lab.proxy_in_authz_window()),
                **authz_checks._observations(lab),
            },
        )
        authz_checks.test_all_nine_checks_appear_in_authz_json_with_a_status(lab)
        authz_checks.test_no_delete_request_left_the_harness(lab)
        authz_checks.test_every_authz_request_went_through_the_fence_and_none_was_out_of_scope(lab)
        authz_checks.test_no_token_or_secret_appears_in_the_artifacts_audits_or_cli_output(lab)
        authz_checks.test_created_resources_match_the_posts_the_authz_sent_and_got_accepted(lab)
        authz_checks.test_writes_were_sent_only_because_the_copy_of_the_profile_allows_them(lab)
        authz_checks.test_in_secure_mode_no_authz_finding_is_high(lab)
        authz_checks.test_every_denied_cell_of_the_access_matrix_has_a_verdict_and_allowed_cells_are_not_tested(
            lab
        )
        authz_checks.test_no_authz_request_timed_out_on_the_way_to_the_target(lab)
        authz_checks.test_operacao_de_medico_registra_motivo_compartilhado(
            lab, "horizontal", "buscarPaciente"
        )
        authz_checks.test_operacao_de_medico_registra_motivo_compartilhado(
            lab, "horizontal_write", "atualizarPaciente"
        )
        authz_checks.test_medicos_compartilhados_nao_produzem_achados_horizontais(lab)
        authz_checks.test_escrita_horizontal_em_paciente_por_medico_nao_e_enviada(lab)
    finally:
        cli.stack_down()


def test_negative_com_escrita_e_restauracao_seguro_b(tmp_path: Path) -> None:
    """Mantém escrita, restauração, coleta e encerramento no mesmo ciclo de mais de 40 linhas."""
    require_docker()
    cli = LabCli(tmp_path, throwaway_pilot_env())
    folder = cli.install_product("clinica-piloto", PILOT_PROFILE)
    profile = folder / "target.yml"
    negative_checks._enable_writes(profile)
    enable_proxy(profile)
    try:
        run_id, outputs = start_and_probe(cli, "clinica-piloto")
        cli_before = len(run_audit(cli, run_id))
        proxy_before = len(current_audit(cli))
        started = time.monotonic()
        done = cli.run("negative", "clinica-piloto", "--run", run_id, timeout=1500)
        seconds = round(time.monotonic() - started, 1)
        assert done.code in {0, 1, 3}, done.stdout[-800:]
        item = negative_checks.Round(
            "write",
            done.code,
            seconds,
            artifact(cli, run_id, "negative.json"),
            run_audit(cli, run_id)[cli_before:],
            current_audit(cli)[proxy_before:],
        )
        hits = secret_hits(cli, PILOT_BASE, [*outputs, done.stdout, done.stderr])
        leaked_files, leaked_proxy = negative_checks._scan_for_invalid_values(cli)
        lab = negative_checks.NegativeLab(
            mode="secure",
            probe_run_id=run_id,
            rounds={"write": item},
            leaked_files=leaked_files,
            leaked_proxy=leaked_proxy,
            secret_hits=hits,
        )
        record_metrics(
            "v18-b-negative-write-clinica-piloto-secure",
            {
                "run_id": run_id,
                "pacing": "proxy",
                "secret_hit_count": len(hits),
                **audit_summary(item.proxy_rows),
                **negative_checks._observations(lab),
            },
        )
        negative_checks.test_the_write_round_sends_writes_only_because_the_copy_of_the_profile_allows_them(
            lab
        )
        negative_checks.test_no_delete_request_left_the_harness(lab)
        negative_checks.test_every_request_of_the_stage_went_through_the_fence_and_none_was_out_of_scope(
            lab
        )
        negative_checks.test_the_invalid_value_never_appears_in_an_artifact_nor_in_the_proxy_audit(
            lab
        )
        negative_checks.test_every_accepted_or_5xx_put_or_patch_has_its_restore_recorded(lab)
        negative_checks.test_negative_json_is_coherent_with_the_trail_and_with_itself(lab)
        negative_checks.test_no_token_or_secret_appears_in_the_artifacts(lab)
    finally:
        cli.stack_down()
