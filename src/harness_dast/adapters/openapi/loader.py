"""Carregador de OpenAPI 3.0/3.1 (JSON ou YAML) para o modelo `ApiSpec` do domínio.

Escolha deliberada de biblioteca: `json` da biblioteca padrão + `yaml.safe_load` (PyYAML, já
dependência do projeto) + um resolvedor próprio e limitado de `$ref` locais. Validadores
completos de OpenAPI (`openapi-spec-validator`, `prance`) puxam `jsonschema`/`referencing`,
resolvem referências remotas por padrão e validam mais do que o harness precisa; aqui o
documento é entrada NÃO CONFIÁVEL e cada capacidade a mais é superfície de ataque. Ver
ADR 0015.

O chamador já validou o caminho do arquivo (escopo de pastas, extensão). Este módulo não
abre URL, não lê outro arquivo, não executa nada do documento e limita tamanho, nós,
profundidade e expansão de referências.
"""

import json
from collections.abc import Mapping
from pathlib import Path

import yaml

from harness_dast.adapters.openapi.operation_mapper import OperationMapper, parse_security
from harness_dast.adapters.openapi.refs import (
    MAX_FILE_BYTES,
    Raw,
    RefResolver,
    check_document_shape,
)
from harness_dast.adapters.openapi.schema_mapper import SchemaMapper
from harness_dast.domain.api_model import ApiSpec, safe_identifier
from harness_dast.domain.errors import ConfigError

_MAX_SCHEMES = 50
_SUPPORTED = ("3.0", "3.1")


def load_spec(path: Path) -> ApiSpec:
    """Lê o arquivo e devolve a API normalizada.

    Args:
        path: Arquivo `.json`, `.yaml` ou `.yml` já validado pelo chamador.

    Returns:
        A descrição normalizada da API.

    Raises:
        ConfigError: Arquivo ilegível ou grande demais (acima de 5 MiB), JSON/YAML inválido,
            Swagger 2.0 (conversão fora do escopo da V1), versão não suportada, `$ref`
            remota ou de arquivo externo, estrutura inválida (com localização por ponteiro
            JSON), `operationId` duplicado ou documento além dos limites. Nunca mostra
            trechos do documento além de identificadores curtos.
    """
    document = _parse(_read(path), path.suffix.lower())
    if not isinstance(document, Mapping):
        raise ConfigError("O OpenAPI deve ser um objeto na raiz do documento.")
    check_document_shape(document)
    _check_version(document)
    return _map(document)


def _read(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ConfigError(
                f"O arquivo do OpenAPI tem mais de {MAX_FILE_BYTES // (1024 * 1024)} MiB.",
                hint="Reduza o documento ou separe a API em partes menores.",
            )
        with path.open("rb") as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ConfigError(
                f"O arquivo do OpenAPI tem mais de {MAX_FILE_BYTES // (1024 * 1024)} MiB.",
                hint="Reduza o documento ou separe a API em partes menores.",
            )
        return data.decode("utf-8-sig")
    except OSError:
        raise ConfigError(
            f"Não foi possível ler o arquivo do OpenAPI ({safe_identifier(path.name)}).",
            hint="Confira se o arquivo existe e se há permissão de leitura.",
        ) from None
    except UnicodeDecodeError:
        raise ConfigError(
            "O arquivo do OpenAPI não está em UTF-8.", hint="Salve o arquivo como UTF-8."
        ) from None


def _parse(text: str, suffix: str) -> Raw:
    try:
        if suffix == ".json":
            return json.loads(text)
        return yaml.safe_load(text)
    except (json.JSONDecodeError, ValueError) as error:
        line = getattr(error, "lineno", None)
        where = f" (linha {line})" if isinstance(line, int) else ""
        raise ConfigError(
            f"O arquivo do OpenAPI não é um JSON válido{where}.",
            hint="Corrija a sintaxe do arquivo.",
        ) from None
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f" (linha {mark.line + 1})" if mark is not None else ""
        raise ConfigError(
            f"O arquivo do OpenAPI não é um YAML válido{where}.",
            hint="Corrija a sintaxe do arquivo.",
        ) from None
    except RecursionError:
        raise ConfigError(
            "O arquivo do OpenAPI tem aninhamento profundo demais para ser lido.",
            hint="Simplifique a estrutura do documento.",
        ) from None


def _check_version(document: Mapping[str, Raw]) -> None:
    if "swagger" in document:
        raise ConfigError(
            "Este documento é Swagger 2.0, que a V1 não lê.",
            hint=(
                "Converta o documento para OpenAPI 3.0 ou 3.1 com uma ferramenta de sua escolha "
                "(a conversão está fora do escopo da V1) e aponte para o arquivo convertido."
            ),
        )
    version = document.get("openapi")
    if not isinstance(version, str) or not version:
        raise ConfigError(
            "O documento não declara a versão do OpenAPI (campo 'openapi').",
            hint="Use um documento OpenAPI 3.0 ou 3.1.",
        )
    if not version.startswith(_SUPPORTED):
        raise ConfigError(
            f"Versão do OpenAPI não suportada: {safe_identifier(version[:12])}.",
            hint="A V1 lê OpenAPI 3.0.x e 3.1.x.",
        )


def _map(document: Mapping[str, Raw]) -> ApiSpec:
    resolver = RefResolver(document)
    schemas = SchemaMapper(resolver)
    mapper = OperationMapper(
        resolver, schemas, parse_security(document.get("security"), "#/security")
    )
    info = document.get("info")
    info = info if isinstance(info, Mapping) else {}
    return ApiSpec(
        title=_short(info.get("title"), 200) or "(sem título)",
        version=_short(info.get("version"), 100),
        servers=_servers(document.get("servers")),
        security_schemes=_security_schemes(document.get("components")),
        operations=mapper.map_paths(document.get("paths", {})),
    )


def _short(value: Raw, limit: int) -> str:
    return str(value)[:limit] if isinstance(value, str | int | float) else ""


def _servers(raw: Raw) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    urls = (entry.get("url") for entry in raw if isinstance(entry, Mapping))
    return tuple(_short(url, 200) for url in urls if isinstance(url, str))[:20]


def _security_schemes(components: Raw) -> dict[str, str]:
    schemes = components.get("securitySchemes") if isinstance(components, Mapping) else None
    if not isinstance(schemes, Mapping):
        return {}
    result: dict[str, str] = {}
    for name, entry in list(schemes.items())[:_MAX_SCHEMES]:
        if isinstance(entry, Mapping) and isinstance(entry.get("type"), str):
            kind = str(entry["type"])[:20]
            detail = entry.get("scheme") if kind == "http" else entry.get("in")
            suffix = f"-{str(detail)[:20]}" if isinstance(detail, str) else ""
            result[str(name)[:100]] = kind + suffix
    return result
