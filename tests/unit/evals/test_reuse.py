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

OPENAPI = json.dumps(
    {
        "openapi": "3.0.3",
        "info": {"title": "synthetic", "version": "1"},
        "paths": {
            "/create": {
                "post": {
                    "operationId": "create",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "enum": ["ready", "waiting"]}
                                    },
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"id": {"type": "string"}},
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/items/{item}": {
                "get": {
                    "operationId": "read",
                    "parameters": [
                        {
                            "name": "item",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    }
)


def _profile(product: str) -> ProductProfile:
    data = deepcopy(GOOD_PROFILE)
    case = load_case(product, CASES) if product == "mini" else load_case(product)
    data["product"] = product
    data["openapi"] = "openapi.json"
    data["scope"]["allow"][0]["allow_local"] = True
    data["auth"]["type"] = "login_password"
    data["auth"]["token_path"] = "/api/login"  # noqa: S105 - rota sintética, não é segredo
    data["auth"]["accounts"] = [
        {
            "alias": item.alias,
            "role": item.role,
            "username": {"secret_ref": f"env:{item.username_env}"},
            "password": {"secret_ref": f"env:{item.password_env}"},
        }
        for item in case.expected.accounts
    ]
    return ProductProfile.from_data(data)


def _knowledge(product: str = "mini", contract: str = OPENAPI) -> str:
    basis = describe_strategy_basis(
        _profile(product),
        openapi_sha256=digest_strategy_document(contract.encode()),
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


def _write_profile(root: Path, product: str, contract: str = OPENAPI) -> None:
    path = root / "trace/profile/final" / product
    write(path / "target.yml", yaml.safe_dump(_profile(product).model_dump(mode="json")))
    write(path / "openapi.json", contract)
    write(path / "knowledge.yml", _knowledge(product, contract))


def _source(repo: Path, out: Path) -> Path:
    dirs = make_round(repo, out)
    write_json(dirs.trace / "collect.json", {"copied": ["profile/final/mini"]})
    file = dirs.trace / "profile/final/mini/knowledge.yml"
    _write_profile(out, "mini")
    return file


def _recipes(out: Path, value: str = "ready") -> None:
    folder = out / "trace/profile/final/mini"
    rules = {
        "schema_version": 1,
        "rules": [
            {
                "match": {"operation": "create", "field": "status", "location": "body"},
                "generator": "constant",
                "args": {"value": value},
            }
        ],
    }
    flow = {
        "schema_version": 1,
        "bindings": [
            {
                "produces": {"operation": "create", "field": "id"},
                "consumed_by": [{"operation": "read", "param": "item"}],
            }
        ],
    }
    rules_text, flow_text = yaml.safe_dump(rules), yaml.safe_dump(flow)
    write(folder / "data-rules.yml", rules_text)
    write(folder / "flows.yml", flow_text)
    knowledge_path = folder / "knowledge.yml"
    knowledge = yaml.safe_load(knowledge_path.read_text(encoding="utf-8"))
    knowledge["basis"]["data_rules"] = digest_strategy_document(
        (folder / "data-rules.yml").read_bytes()
    )
    knowledge["basis"]["flows"] = digest_strategy_document((folder / "flows.yml").read_bytes())
    write(knowledge_path, yaml.safe_dump(knowledge))
    strategy = {
        "schema_version": 1,
        "references": {
            "target": "target.yml",
            "data_rules": "data-rules.yml",
            "flows": "flows.yml",
        },
        "choices": [
            {
                "name": "coverage",
                "value": "preserve",
                "source": "contract",
                "reason": "preserve_baseline",
                "valid_until": "2027-12-31",
                "state": "validated",
                "basis": knowledge["basis"],
            }
        ],
    }
    write(folder / "strategy.yml", yaml.safe_dump(strategy))


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
    assert set(p.name for p in package.iterdir()) == {
        "knowledge.yml",
        "target.reuse.yml",
        "manifest.json",
    }
    assert "Complemento da carta" in (result.workspace / "EVAL-BRIEFING.md").read_text(
        encoding="utf-8"
    )
    assert not (result.workspace / "state").exists()


def test_exports_validated_recipes_as_proposals(repo: Path, out: Path, tmp_path: Path) -> None:
    _source(repo, out)
    _recipes(out)
    package = export_reuse(out, tmp_path / "package")
    _, files = verify_reuse(out, package, "mini")
    assert set(files) == {
        "knowledge.yml",
        "target.reuse.yml",
        "data-rules.yml",
        "flows.yml",
        "strategy.yml",
    }
    assert yaml.safe_load(files["strategy.yml"])["choices"][0]["state"] == "review_required"
    basis = yaml.safe_load(files["knowledge.yml"])["basis"]
    assert basis["data_rules"] == digest_strategy_document(files["data-rules.yml"].encode())
    assert basis["flows"] == digest_strategy_document(files["flows.yml"].encode())
    assert yaml.safe_load(files["strategy.yml"])["choices"][0]["basis"] == basis
    projection = yaml.safe_load(files["target.reuse.yml"])
    assert projection["state"] == "review_required"
    assert "scope" not in projection
    assert "env:" in files["target.reuse.yml"]


def test_prepare_delivers_recipes_only_in_declared_quarantine(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    _source(repo, out)
    _recipes(out)
    package = export_reuse(out, tmp_path / "package")
    result = prepare(
        "mini",
        "secure",
        9,
        tmp_path / "second",
        source=repo,
        cases_dir=CASES,
        reuse_from=out,
        reuse_package=package,
    )
    folder = result.workspace / "inputs/reuse"
    assert {p.name for p in folder.iterdir()} == {
        "knowledge.yml",
        "target.reuse.yml",
        "data-rules.yml",
        "flows.yml",
        "strategy.yml",
    }
    briefing = (result.workspace / "EVAL-BRIEFING.md").read_text(encoding="utf-8")
    assert all(f"inputs/reuse/{p.name}" in briefing for p in folder.iterdir())
    assert not (result.workspace / "products/mini").exists()


def test_refuses_stale_strategy(repo: Path, out: Path, tmp_path: Path) -> None:
    _source(repo, out)
    _recipes(out)
    strategy = out / "trace/profile/final/mini/strategy.yml"
    data = yaml.safe_load(strategy.read_text(encoding="utf-8"))
    data["choices"][0]["basis"]["openapi"] = "b" * 64
    write(strategy, yaml.safe_dump(data))
    with pytest.raises(EvalError, match="Estratégia"):
        export_reuse(out, tmp_path / "package")


def test_constant_not_proven_by_enum_rejects_entire_export(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    _source(repo, out)
    _recipes(out, "unproven")
    with pytest.raises(EvalError, match="Constante"):
        export_reuse(out, tmp_path / "package")
    assert not (tmp_path / "package").exists()


def test_free_text_in_generator_args_is_rejected(repo: Path, out: Path, tmp_path: Path) -> None:
    _source(repo, out)
    _recipes(out)
    folder = out / "trace/profile/final/mini"
    rules = {
        "schema_version": 1,
        "rules": [
            {
                "match": {"operation": "create", "field": "status", "location": "body"},
                "generator": "alphanumeric",
                "args": {"prefix": "arbitrary"},
            }
        ],
    }
    content = yaml.safe_dump(rules)
    write(folder / "data-rules.yml", content)
    knowledge_path = folder / "knowledge.yml"
    knowledge = yaml.safe_load(knowledge_path.read_text(encoding="utf-8"))
    knowledge["basis"]["data_rules"] = digest_strategy_document(
        (folder / "data-rules.yml").read_bytes()
    )
    write(knowledge_path, yaml.safe_dump(knowledge))
    with pytest.raises(EvalError, match="textual"):
        export_reuse(out, tmp_path / "package")


def test_undeclared_numeric_bound_is_rejected(repo: Path, out: Path, tmp_path: Path) -> None:
    _source(repo, out)
    _recipes(out)
    folder = out / "trace/profile/final/mini"
    rules = {
        "schema_version": 1,
        "rules": [
            {
                "match": {"operation": "create", "field": "status", "location": "body"},
                "generator": "integer",
                "args": {"min": 73},
            }
        ],
    }
    write(folder / "data-rules.yml", yaml.safe_dump(rules))
    path = folder / "knowledge.yml"
    knowledge = yaml.safe_load(path.read_text(encoding="utf-8"))
    knowledge["basis"]["data_rules"] = digest_strategy_document(
        (folder / "data-rules.yml").read_bytes()
    )
    write(path, yaml.safe_dump(knowledge))
    with pytest.raises(EvalError, match="Limite numérico"):
        export_reuse(out, tmp_path / "package")


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


def test_unknown_bearer_in_comment_is_rejected(repo: Path, out: Path, tmp_path: Path) -> None:
    file = _source(repo, out)
    file.write_text(
        _knowledge() + "\n# Authorization: Bearer synthetic-secret-12345\n", encoding="utf-8"
    )
    with pytest.raises(EvalError, match="credencial"):
        export_reuse(out, tmp_path / "package")
    assert not (tmp_path / "package").exists()


def test_comments_are_not_exported(repo: Path, out: Path, tmp_path: Path) -> None:
    file = _source(repo, out)
    file.write_text(_knowledge() + "\n# unrelated private text\n", encoding="utf-8")
    package = export_reuse(out, tmp_path / "package")
    assert "unrelated private text" not in (package / "knowledge.yml").read_text(encoding="utf-8")


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


def test_verify_rejects_byte_change_even_if_text_normalizes(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    _source(repo, out)
    package = export_reuse(out, tmp_path / "package")
    file = package / "knowledge.yml"
    file.write_bytes(file.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(EvalError, match="alterado"):
        verify_reuse(out, package, "mini")


def test_rejects_account_not_declared_by_letter(repo: Path, out: Path, tmp_path: Path) -> None:
    _source(repo, out)
    folder = out / "trace/profile/final/mini"
    data = _profile("mini").model_dump(mode="json")
    data["auth"]["accounts"][0]["role"] = "unknown_role"
    profile = ProductProfile.from_data(data)
    write(folder / "target.yml", yaml.safe_dump(data))
    basis = describe_strategy_basis(
        profile,
        openapi_sha256=digest_strategy_document(OPENAPI.encode()),
        data_rules_sha256=digest_strategy_document(None),
        flows_sha256=digest_strategy_document(None),
        engine_version="synthetic-engine",
    )
    path = folder / "knowledge.yml"
    knowledge = yaml.safe_load(path.read_text(encoding="utf-8"))
    knowledge["basis"] = basis.model_dump(mode="json")
    write(path, yaml.safe_dump(knowledge))
    with pytest.raises(EvalError, match="carta"):
        export_reuse(out, tmp_path / "package")


def test_missing_secret_lacre_fails_closed(repo: Path, out: Path, tmp_path: Path) -> None:
    _source(repo, out)
    (out / "sealed/secrets.json").unlink()
    with pytest.raises(EvalError):
        export_reuse(out, tmp_path / "package")


def test_manifest_contains_no_sealed_data(repo: Path, out: Path, tmp_path: Path) -> None:
    _source(repo, out)
    package = export_reuse(out, tmp_path / "package")
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"schema_version", "product", "files"}


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
    root = Path(__file__).resolve().parents[3]
    input_path = root / (
        "lab/pilot/openapi.json" if case_name == "clinica-piloto" else "lab/vampi/openapi3.yml"
    )
    contract = json.dumps(yaml.safe_load(input_path.read_text(encoding="utf-8")))
    _write_profile(source, case.product, contract)
    package = export_reuse(source, tmp_path / "package")
    product, content = verify_reuse(source, package, case_name)
    assert product == case.product
    assert yaml.safe_load(content["knowledge.yml"])["entries"][0]["state"] == "review_required"


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


def test_package_carries_provenance_of_origin_round_and_nothing_else_identifying(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    run_id = "2026-11-16T14-30-24Z-mini-bed9"
    _source(repo, out)
    path = out / "trace/profile/final/mini/knowledge.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["provenance"] = {
        "run_id": run_id,
        "manifest_sha256": "a" * 64,
        "probe_sha256": "b" * 64,
        "authz_sha256": None,
    }
    write(path, yaml.safe_dump(data))

    package = export_reuse(out, tmp_path / "package")
    _, files = verify_reuse(out, package, "mini")

    carried = yaml.safe_load(files["knowledge.yml"])["provenance"]
    assert carried == data["provenance"]
    assert all(run_id not in text for name, text in files.items() if name != "knowledge.yml")
