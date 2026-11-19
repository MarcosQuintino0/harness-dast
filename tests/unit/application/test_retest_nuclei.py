"""`retestar` com o Nuclei (ADR 0122): só os modelos dos achados abertos, e só se houver."""

from tests.fakes.nuclei import nuclei_finding, nuclei_result
from tests.fakes.retest import InMemoryRetestArtifacts
from tests.unit.application.test_retest import AFTER, BEFORE, _after, _fake, _finding, _request
from tests.unit.domain.test_findings_triage_qa import report_with


def _artifacts(**nuclei: object) -> InMemoryRetestArtifacts:
    kept = _finding("a", "op1")
    reports = {BEFORE: report_with(kept, run_id=BEFORE), AFTER: _after([kept], [])}
    return InMemoryRetestArtifacts(reports, nuclei=nuclei)  # type: ignore[arg-type]


def test_reteste_repete_so_os_modelos_dos_achados_do_nuclei_da_execucao_anterior() -> None:
    previous = nuclei_result(
        run_id=BEFORE,
        findings=(
            nuclei_finding("b-id"),
            nuclei_finding("a-id"),
            nuclei_finding("a-id", path="/x"),
        ),
    )
    case, pipeline = _fake(_artifacts(**{BEFORE: previous}))

    case.execute(_request())

    (run,) = pipeline.requests
    assert run.nuclei is True
    assert run.nuclei_templates == (
        "http/misconfiguration/a-id.yaml",
        "http/misconfiguration/b-id.yaml",
    )


def test_sem_nuclei_json_anterior_o_estagio_do_nuclei_fica_desligado() -> None:
    case, pipeline = _fake(_artifacts())

    case.execute(_request())

    (run,) = pipeline.requests
    assert run.nuclei is False
    assert run.nuclei_templates == ()


def test_nuclei_json_anterior_sem_achados_deixa_o_estagio_desligado() -> None:
    case, pipeline = _fake(_artifacts(**{BEFORE: nuclei_result(run_id=BEFORE, findings=())}))

    case.execute(_request())

    (run,) = pipeline.requests
    assert run.nuclei is False
    assert run.nuclei_templates == ()


def test_authz_e_negative_continuam_desligados_no_reteste() -> None:
    previous = nuclei_result(run_id=BEFORE, findings=(nuclei_finding(),))
    case, pipeline = _fake(_artifacts(**{BEFORE: previous}))

    case.execute(_request())

    (run,) = pipeline.requests
    assert (run.authz, run.negative) == (False, False)
