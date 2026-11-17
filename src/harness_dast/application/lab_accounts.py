"""Seleciona operações do OpenAPI para preparar contas sintéticas do laboratório."""

from pydantic import ValidationError

from harness_dast.application.stack_models import LabAccountPaths
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.errors import ConfigError


def account_paths(spec: ApiSpec) -> LabAccountPaths:
    """Extrai operações POST declaradas explicitamente e caminhos literais seguros.

    Raises:
        ConfigError: Operação ausente, método incompatível ou caminho inválido.
    """
    ids = {
        "signup": "signup",
        "login": "login",
        "resend": "vehicle_resend_email",
        "vehicle": "add_vehicle",
    }
    selected = {name: spec.get_operation(operation_id) for name, operation_id in ids.items()}
    if any(op.method != "post" or op.id_synthesized for op in selected.values()):
        raise ConfigError(
            "O OpenAPI não declara as operações POST necessárias ao cadastro do laboratório.",
            hint="Confira os identificadores e métodos no OpenAPI do produto.",
        )
    try:
        return LabAccountPaths.model_validate({name: op.path for name, op in selected.items()})
    except ValidationError:
        raise ConfigError(
            "O OpenAPI contém caminho inválido para cadastro do laboratório.",
            hint="Use caminhos literais absolutos sem parâmetros ou segmentos relativos.",
        ) from None
