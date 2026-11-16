"""Contratos offline do único canal exportável entre rodadas."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from evals.runner.cases import EvalError, load_case
from evals.runner.cli import main
from evals.runner.prepare import prepare
from evals.runner.reuse import export_reuse, verify_reuse
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.strategy_basis import describe_strategy_basis, digest_strategy_document
from tests.unit.evals.support import CASES, GOOD_PROFILE, make_round, write, write_json


def _profile(product: str) -> ProductProfile:
    data = deepcopy(GOOD_PROFILE)
    data["product"] = product
    data["openapi"] = "openapi.json"
    data["scope"]["allow"][0]["allow_local"] = True
    data["auth"]["type"] = "login_password"
    data["auth"]["token_path"] = "/api/login"  # noqa: S105 - rota sintética, não é segredo
    return ProductProfile.from_data(data)


def _knowledge(product: str = "mini") -> str:
    basis = describe_strategy_basis(
        _profile(product),
        openapi_sha256=digest_strategy_document(b"{}"),
        data_rules_sha256=digest_strategy_document(None),
        flows_sha256=digest_strategy_document(None),
        engine_version="synthetic-engine",
    )
    data = {
        "schema_version": 1,
        "basis": basis.model_dump(mode="json"),
        "references": {
            "target": "target.yml",
            "data_rules": "data-rules.yml",
            "flows": "flows.yml",
        },
        "entries": [
            {
                "kind": kind,
                "source": "contract",
                "reason": "references_existing_documents",
                "state": "validated",
                "valid_until": "2027-12-31",
                "dependencies": [
                    "environment",
                    "authorization",
                    "accounts",
                    "planning",
                    "openapi",
                    "data_rules",
                    "flows",
                    "engine",
                ],
            }
            for kind in ("account", "data", "flow", "effect", "authentication")
        ],
    }
    return yaml.safe_dump(data)


def _write_profile(root: Path, product: str) -> None:
    path = root / "trace/profile/final" / product
    write(path / "target.yml", yaml.safe_dump(_profile(product).model_dump(mode="json")))
    write(path / "openapi.json", "{}")
    write(path / "knowledge.yml", _knowledge(product))


def _source(repo: Path, out: Path) -> Path:
    dirs = make_round(repo, out)
    write_json(dirs.trace / "collect.json", {"copied": ["profile/final/mini"]})
    file = dirs.trace / "profile/final/mini/knowledge.yml"
    _write_profile(out, "mini")
    return file


def test_export_and_prepare_quarantine_only_allowed_file(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    _source(repo, out)
    package = tmp_path / "package"
    export_reuse(out, package)
    result = prepare(
        "mini",
        "secure",
        5,
        tmp_path / "second",
        source=repo,
        cases_dir=CASES,
        reuse_from=out,
        reuse_package=package,
    )
    item = yaml.safe_load((result.workspace / "inputs/reuse/knowledge.yml").read_text())
    assert item["entries"][0]["state"] == "review_required"
    assert set(p.name for p in package.iterdir()) == {"knowledge.yml", "manifest.json"}
    assert "Complemento da carta" in (result.workspace / "EVAL-BRIEFING.md").read_text(
        encoding="utf-8"
    )
    assert not (result.workspace / "state").exists()


@pytest.mark.parametrize(
    "bad", ["", "[", "schema_version: 1\nschema_version: 1\n", "schema_version: 2\n"]
)
def test_export_rejects_invalid_or_ambiguous_data(
    repo: Path, out: Path, tmp_path: Path, bad: str
) -> None:
    file = _source(repo, out)
    file.write_text(bad, encoding="utf-8")
    with pytest.raises(EvalError):
        export_reuse(out, tmp_path / "package")
    assert not (tmp_path / "package").exists()


def test_export_rejects_round_secret_even_if_short(repo: Path, out: Path, tmp_path: Path) -> None:
    file = _source(repo, out)
    secret_path = out / "sealed/secrets.json"
    secrets = json.loads(secret_path.read_text(encoding="utf-8"))
    secrets[next(iter(secrets))] = "contract"
    write_json(secret_path, secrets)
    with pytest.raises(EvalError, match="Segredo"):
        export_reuse(out, tmp_path / "package")
    assert file.is_file()
    assert not (tmp_path / "package").exists()


def test_export_rejects_leak_term(repo: Path, out: Path, tmp_path: Path) -> None:
    file = _source(repo, out)
    file.write_text(_knowledge() + "\n# segredo-do-gabarito\n", encoding="utf-8")
    with pytest.raises(EvalError, match="gabarito"):
        export_reuse(out, tmp_path / "package")


def test_verify_rejects_extra_files_and_wrong_case(repo: Path, out: Path, tmp_path: Path) -> None:
    _source(repo, out)
    package = tmp_path / "package"
    export_reuse(out, package)
    with pytest.raises(EvalError, match="caso"):
        verify_reuse(out, package, "other")
    write(package / "extra", "x")
    with pytest.raises(EvalError, match="extras"):
        verify_reuse(out, package, "mini")


def test_verify_rejects_modified_package(repo: Path, out: Path, tmp_path: Path) -> None:
    _source(repo, out)
    package = tmp_path / "package"
    export_reuse(out, package)
    (package / "knowledge.yml").write_text("schema_version: 1", encoding="utf-8")
    with pytest.raises(EvalError, match="alterado"):
        verify_reuse(out, package, "mini")


def test_missing_secret_lacre_fails_closed(repo: Path, out: Path, tmp_path: Path) -> None:
    _source(repo, out)
    (out / "sealed/secrets.json").unlink()
    with pytest.raises(EvalError):
        export_reuse(out, tmp_path / "package")


def test_manifest_contains_no_sealed_data(repo: Path, out: Path, tmp_path: Path) -> None:
    _source(repo, out)
    package = export_reuse(out, tmp_path / "package")
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"schema_version", "product", "sha256"}


@pytest.mark.parametrize("case_name", ["clinica-piloto", "vampi"])
def test_synthetic_dry_run_real_case_export(case_name: str, tmp_path: Path) -> None:
    case = load_case(case_name)
    source = tmp_path / "source"
    write_json(source / "sealed/mode.json", {"case": case.name})
    write_json(source / "sealed/case.json", case.model_dump(mode="json"))
    names = set(case.secrets.generate) | set(case.secrets.fixed)
    write_json(
        source / "sealed/secrets.json",
        {name: f"zZ97_synthetic_{i}" for i, name in enumerate(sorted(names))},
    )
    write_json(source / "trace/collect.json", {"copied": [f"profile/final/{case.product}"]})
    _write_profile(source, case.product)
    package = export_reuse(source, tmp_path / "package")
    product, content = verify_reuse(source, package, case_name)
    assert product == case.product
    assert content == _knowledge(case.product)


def test_cli_missing_source_returns_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = main(
        [
            "export-reuse",
            "--out",
            str(tmp_path / "missing"),
            "--destination",
            str(tmp_path / "package"),
        ]
    )
    assert result == 2
    assert "erro:" in capsys.readouterr().err


def test_extra_hardlink_is_rejected(repo: Path, out: Path, tmp_path: Path) -> None:
    file = _source(repo, out)
    try:
        (tmp_path / "hardlink").hardlink_to(file)
    except OSError:
        pytest.skip("Sistema não permite criar hardlink no teste")
    with pytest.raises(EvalError):
        export_reuse(out, tmp_path / "package")


@pytest.mark.parametrize("name", ["openapi.json", "data-rules.yml", "flows.yml"])
def test_changed_source_refuses_export(repo: Path, out: Path, tmp_path: Path, name: str) -> None:
    _source(repo, out)
    write(out / "trace/profile/final/mini" / name, "{}\n")
    with pytest.raises(EvalError, match="mudaram"):
        export_reuse(out, tmp_path / "package")


def test_changed_profile_refuses_export(repo: Path, out: Path, tmp_path: Path) -> None:
    _source(repo, out)
    target = out / "trace/profile/final/mini/target.yml"
    profile = yaml.safe_load(target.read_text(encoding="utf-8"))
    profile["limits"]["requests_per_second"] = 9
    write(target, yaml.safe_dump(profile))
    with pytest.raises(EvalError, match="mudaram"):
        export_reuse(out, tmp_path / "package")


def test_symlink_is_rejected(repo: Path, out: Path, tmp_path: Path) -> None:
    file = _source(repo, out)
    target = tmp_path / "other.yml"
    target.write_text(file.read_text(encoding="utf-8"), encoding="utf-8")
    file.unlink()
    try:
        file.symlink_to(target)
    except OSError:
        pytest.skip("Sistema não permite criar link simbólico no teste")
    with pytest.raises(EvalError, match="Links"):
        export_reuse(out, tmp_path / "package")
