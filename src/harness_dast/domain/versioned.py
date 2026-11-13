"""Validação comum dos arquivos versionados do perfil (`data-rules.yml`, `flows.yml`).

Converte qualquer problema de estrutura em `ConfigError` com a lista de campos, sem repetir
valores recebidos. Este módulo é puro: o YAML já chega como dados Python.
"""

from collections.abc import Mapping

from pydantic import ValidationError

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile_errors import to_config_error

SUPPORTED_SCHEMA_VERSION = 1


def validate_versioned[M: ApiModel](model: type[M], data: object, *, document: str, hint: str) -> M:
    """Valida `data` como o modelo `model`, exigindo `schema_version: 1`.

    Args:
        model: Modelo pydantic do arquivo.
        data: Dados lidos do YAML (esperado: um mapa).
        document: Nome do arquivo, para as mensagens (por exemplo `data-rules.yml`).
        hint: Dica de correção repetida no erro.

    Returns:
        O modelo validado e congelado.

    Raises:
        ConfigError: Não é um mapa, falta `schema_version`, a versão não é suportada ou
            há campo ausente, desconhecido ou inválido. Nunca repete os valores recebidos.
    """
    if not isinstance(data, Mapping):
        raise ConfigError(f"O arquivo {document} deve ser um mapa de campos.", hint=hint)
    version = data.get("schema_version")
    if "schema_version" not in data:
        raise ConfigError(
            f"O arquivo {document} não informa schema_version.",
            hint=f"Adicione schema_version: {SUPPORTED_SCHEMA_VERSION}.",
        )
    if type(version) is not int or version != SUPPORTED_SCHEMA_VERSION:
        shown = f" {version}" if type(version) is int else ""
        raise ConfigError(
            f"schema_version{shown} de {document} não é suportada; esta versão aceita "
            f"apenas {SUPPORTED_SCHEMA_VERSION}.",
            hint="Atualize o arquivo para o schema atual ou use a CLI correspondente.",
        )
    try:
        return model.model_validate(data)
    except ValidationError as error:
        translated = to_config_error(error, hint=hint)
        message = translated.message.replace("Perfil inválido", f"Arquivo {document} inválido", 1)
        raise ConfigError(message, hint=hint) from None
