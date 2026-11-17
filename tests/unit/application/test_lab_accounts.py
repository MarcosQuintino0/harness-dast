"""Seleção das operações de cadastro a partir do contrato normalizado."""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.openapi.spec_loader import FileSpecLoader
from harness_dast.adapters.storage.product_paths import resolve_product_file
from harness_dast.application.lab_accounts import account_paths
from harness_dast.domain.api_model import ApiSpec, Operation
from harness_dast.domain.errors import ConfigError
from tests.fakes.profile_data import valid_profile

IDS = ("signup", "login", "vehicle_resend_email", "add_vehicle")


def _spec() -> ApiSpec:
    return ApiSpec(
        title="lab",
        version="1",
        operations=tuple(
            Operation(operation_id=name, method="post", path=f"/test/{index}")
            for index, name in enumerate(IDS)
        ),
    )


def test_obtem_caminhos_do_openapi_no_diretorio_inputs(tmp_path: Path) -> None:
    products = tmp_path / "products"
    inputs = products / "demo" / "inputs"
    inputs.mkdir(parents=True)
    document = {
        "openapi": "3.0.0",
        "info": {"title": "lab", "version": "1"},
        "paths": {
            f"/test/{index}": {
                "post": {"operationId": name, "responses": {"200": {"description": "ok"}}}
            }
            for index, name in enumerate(IDS)
        },
    }
    (inputs / "contract.json").write_text(json.dumps(document), encoding="utf-8")
    profile = valid_profile("demo").model_copy(update={"openapi": "inputs/contract.json"})
    loader = FileSpecLoader(lambda product, path: resolve_product_file(products, product, path))

    paths = account_paths(loader.load("demo", profile))

    assert (paths.signup, paths.login, paths.resend, paths.vehicle) == tuple(
        f"/test/{index}" for index in range(4)
    )


@pytest.mark.parametrize("content", [None, "{malformado", "{}"])
def test_openapi_ausente_malformado_ou_invalido_e_recusado(
    tmp_path: Path, content: str | None
) -> None:
    product = tmp_path / "demo"
    product.mkdir()
    if content is not None:
        (product / "openapi.json").write_text(content, encoding="utf-8")
    loader = FileSpecLoader(lambda name, path: resolve_product_file(tmp_path, name, path))

    with pytest.raises(ConfigError):
        account_paths(loader.load("demo", valid_profile("demo")))


def test_operacao_ausente_e_recusada() -> None:
    spec = _spec().model_copy(update={"operations": _spec().operations[:-1]})
    with pytest.raises(ConfigError, match="não existe"):
        account_paths(spec)


@pytest.mark.parametrize(
    "path", ["//evil", "/a/../b", "/test/{id}", "/x?y=z", "/x%2fy", "/x#fragment", "/x\n"]
)
def test_caminho_nao_literal_ou_inseguro_e_recusado(path: str) -> None:
    spec = _spec()
    changed = spec.operations[0].model_copy(update={"path": path})
    with pytest.raises(ConfigError, match="caminho inválido"):
        account_paths(spec.model_copy(update={"operations": (changed, *spec.operations[1:])}))


@pytest.mark.parametrize("change", [{"method": "get"}, {"id_synthesized": True}])
def test_operacao_incompativel_e_recusada(change: dict[str, object]) -> None:
    spec = _spec()
    changed = spec.operations[0].model_copy(update=change)
    with pytest.raises(ConfigError, match="operações POST"):
        account_paths(spec.model_copy(update={"operations": (changed, *spec.operations[1:])}))


def test_caminhos_repetidos_sao_recusados() -> None:
    spec = _spec()
    changed = spec.operations[0].model_copy(update={"path": spec.operations[1].path})
    with pytest.raises(ConfigError, match="caminho inválido"):
        account_paths(spec.model_copy(update={"operations": (changed, *spec.operations[1:])}))
