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


def _rename_to_captured(out: Path) -> Path:
    folder = out / "trace/profile/final/mini"
    captured = folder / "knowledge.captured.yml"
    (folder / "knowledge.yml").rename(captured)
    return captured


def test_export_aceita_so_a_captura_quando_nao_ha_conhecimento_ativo(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    _source(repo, out)
    _rename_to_captured(out)

    package = export_reuse(out, tmp_path / "package")
    _, files = verify_reuse(out, package, "mini")

    exported = yaml.safe_load(files["knowledge.yml"])
    assert {entry["state"] for entry in exported["entries"]} == {"review_required"}
    assert not (package / "knowledge.captured.yml").exists()


def test_export_prefere_o_conhecimento_ativo_a_captura(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    _source(repo, out)
    folder = out / "trace/profile/final/mini"
    active = yaml.safe_load((folder / "knowledge.yml").read_text(encoding="utf-8"))
    active["provenance"] = {
        "run_id": "2026-11-16T14-30-24Z-mini-bed9",
        "manifest_sha256": "a" * 64,
        "probe_sha256": "b" * 64,
        "authz_sha256": None,
    }
    write(folder / "knowledge.yml", yaml.safe_dump(active))
    write(folder / "knowledge.captured.yml", "isto nao e conhecimento valido: [")

    package = export_reuse(out, tmp_path / "package")
    _, files = verify_reuse(out, package, "mini")

    assert yaml.safe_load(files["knowledge.yml"])["provenance"] == active["provenance"]


def test_export_sem_nenhum_dos_dois_diz_quais_arquivos_faltam(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    _source(repo, out)
    (out / "trace/profile/final/mini/knowledge.yml").unlink()

    with pytest.raises(EvalError) as caught:
        export_reuse(out, tmp_path / "package")

    message = str(caught.value)
    assert "knowledge.yml" in message
    assert "knowledge.captured.yml" in message
    assert "capturar" in message
    assert not (tmp_path / "package").exists()


def test_export_com_captura_grande_demais_diz_qual_arquivo_excede_o_limite(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    _source(repo, out)
    captured = _rename_to_captured(out)
    captured.write_text("a: " + "x" * 100_000, encoding="utf-8")

    with pytest.raises(EvalError) as caught:
        export_reuse(out, tmp_path / "package")

    message = str(caught.value)
    assert "excede o limite" in message
    assert "knowledge.captured.yml" in message


def test_export_com_conhecimento_ativo_grande_demais_nao_cai_na_captura(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    _source(repo, out)
    folder = out / "trace/profile/final/mini"
    write(folder / "knowledge.captured.yml", (folder / "knowledge.yml").read_text(encoding="utf-8"))
    (folder / "knowledge.yml").write_text("a: " + "x" * 100_000, encoding="utf-8")

    with pytest.raises(EvalError, match=r"excede o limite.*knowledge\.yml"):
        export_reuse(out, tmp_path / "package")


def test_export_com_captura_malformada_recusa(repo: Path, out: Path, tmp_path: Path) -> None:
    _source(repo, out)
    captured = _rename_to_captured(out)
    captured.write_text("schema_version: [", encoding="utf-8")

    with pytest.raises(EvalError, match="Conhecimento ausente ou malformado"):
        export_reuse(out, tmp_path / "package")


def _email_rule(out: Path, domain: str) -> None:
    folder = out / "trace/profile/final/mini"
    rules = {
        "schema_version": 1,
        "rules": [
            {
                "match": {"operation": "create", "field": "status", "location": "body"},
                "generator": "email",
                "args": {"domain": domain},
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


@pytest.mark.parametrize(
    "domain",
    [
        "teste.exemplo.com.br",
        "example.test",
        "a.b.example",
        "x.invalid",
        "app.localhost",
        "teste.local",
        "example.com",
        "mail.example.net",
        "deep.sub.example.org",
    ],
)
def test_email_domain_from_template_or_reserved_is_exported(
    repo: Path, out: Path, tmp_path: Path, domain: str
) -> None:
    _source(repo, out)
    _email_rule(out, domain)
    package = export_reuse(out, tmp_path / "package")
    _, files = verify_reuse(out, package, "mini")
    assert domain in files["data-rules.yml"]


@pytest.mark.parametrize(
    "domain",
    [
        "empresa-real.com.br",
        "notexample.com",
        "example.com.br",
        "notlocal",
        "Example.TEST",
        "a..example.test",
        ".example.test",
        "café.example.test",
        "a_b.example.test",
        "a b.example.test",
        ("a" * 60 + ".") * 4 + "example.test",
    ],
)
def test_email_domain_outside_template_and_reserved_is_rejected(
    repo: Path, out: Path, tmp_path: Path, domain: str
) -> None:
    _source(repo, out)
    _email_rule(out, domain)
    with pytest.raises(EvalError, match="textual"):
        export_reuse(out, tmp_path / "package")
    assert not (tmp_path / "package").exists()


@pytest.mark.parametrize("content", [None, "rules: [", "schema_version: 9\n"])
def test_missing_or_malformed_template_fails_closed(
    repo: Path,
    out: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: str | None,
) -> None:
    _source(repo, out)
    _email_rule(out, "empresa-real.com.br")
    fake_root = tmp_path / "root"
    if content is not None:
        write(fake_root / "products/_template/data-rules.yml", content)
    monkeypatch.setattr("evals.runner.reuse_recipes.REPO_ROOT", fake_root)
    with pytest.raises(EvalError, match="Modelo products/_template"):
        export_reuse(out, tmp_path / "package")
    assert not (tmp_path / "package").exists()


def _seal_case(
    out: Path, fixed: dict[str, str], generate: list[str], values: dict[str, str]
) -> None:
    case_path = out / "sealed/case.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["secrets"] = {"generate": generate, "fixed": fixed}
    write_json(case_path, case)
    write_json(out / "sealed/secrets.json", values)


def test_fixed_secret_equal_to_declared_role_is_public(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    _source(repo, out)
    _seal_case(
        out,
        {"MINI_ADMIN_USER": "Admin"},
        ["MINI_ADMIN_PASS"],
        {"MINI_ADMIN_USER": "Admin", "MINI_ADMIN_PASS": "senha-sorteada-9z"},
    )
    package = export_reuse(out, tmp_path / "package")
    assert (package / "target.reuse.yml").is_file()


def test_same_value_as_generated_secret_is_still_rejected(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    _source(repo, out)
    _seal_case(
        out,
        {},
        ["MINI_ADMIN_USER", "MINI_ADMIN_PASS"],
        {"MINI_ADMIN_USER": "admin", "MINI_ADMIN_PASS": "senha-sorteada-9z"},
    )
    with pytest.raises(EvalError, match="Segredo"):
        export_reuse(out, tmp_path / "package")


def test_fixed_secret_not_equal_to_a_role_is_still_rejected(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    _source(repo, out)
    _seal_case(
        out,
        {"MINI_ADMIN_USER": "contract"},
        ["MINI_ADMIN_PASS"],
        {"MINI_ADMIN_USER": "contract", "MINI_ADMIN_PASS": "senha-sorteada-9z"},
    )
    with pytest.raises(EvalError, match="Segredo"):
        export_reuse(out, tmp_path / "package")


def test_other_secret_of_the_same_case_is_still_scanned_when_user_is_public(
    repo: Path, out: Path, tmp_path: Path
) -> None:
    file = _source(repo, out)
    _seal_case(
        out,
        {"MINI_ADMIN_USER": "admin"},
        ["MINI_ADMIN_PASS"],
        {"MINI_ADMIN_USER": "admin", "MINI_ADMIN_PASS": "senha-sorteada-9z"},
    )
    file.write_text(_knowledge() + "\n# senha-sorteada-9z\n", encoding="utf-8")
    with pytest.raises(EvalError, match="Segredo"):
        export_reuse(out, tmp_path / "package")
