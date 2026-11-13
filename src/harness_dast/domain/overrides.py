"""Sobrescritas que só estreitam: flags da CLI nunca ampliam escopo nem limites.

Regra (CLAUDE.md, Parte B): "flags só reduzem". Aqui a regra é código: cada função recebe o
que o perfil autorizou e o que foi pedido, e devolve algo igual ou menor, ou levanta
`ConfigError`. Nenhuma altera os argumentos.

Construir uma sobrescrita inválida levanta `pydantic.ValidationError`.
"""

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.host import parse_host
from harness_dast.domain.pathpattern import covers, format_pattern, parse_pattern
from harness_dast.domain.run import (
    MAX_DURATION_MINUTES,
    MAX_REQUESTS_PER_SECOND,
    MAX_ZAP_THREADS_PER_HOST,
    RunLimits,
)
from harness_dast.domain.scope import Scope, ScopeRule
from harness_dast.domain.urlnorm import KNOWN_METHODS

_HINT = "Flags só reduzem escopo e limites. Para ampliar, peça nova autorização ao dono do produto."


class ScopeOverride(BaseModel):
    """Restrições pedidas sobre o escopo do perfil. `None` significa "não restringir".

    Attributes:
        hosts: Manter somente estes hosts.
        methods: Manter somente estes métodos.
        paths: Manter somente caminhos cobertos por estes padrões.
        deny_paths: Padrões de caminho adicionais a negar.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    hosts: tuple[str, ...] | None = None
    methods: tuple[str, ...] | None = None
    paths: tuple[str, ...] | None = None
    deny_paths: tuple[str, ...] = ()

    @field_validator("methods")
    @classmethod
    def validate_methods(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        """Aceita só métodos conhecidos, em maiúsculas."""
        if value is not None and not set(value) <= KNOWN_METHODS:
            raise ValueError("método HTTP desconhecido ou fora de maiúsculas")
        return value

    @field_validator("paths", "deny_paths")
    @classmethod
    def validate_patterns(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        """Valida cada padrão de caminho."""
        for pattern in value or ():
            parse_pattern(pattern)
        return value


class LimitsOverride(BaseModel):
    """Limites menores pedidos; `None` significa "manter o do perfil"."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requests_per_second: float | None = Field(
        default=None, gt=0, le=MAX_REQUESTS_PER_SECOND, allow_inf_nan=False, strict=True
    )
    max_duration_minutes: StrictInt | None = Field(default=None, ge=1, le=MAX_DURATION_MINUTES)
    zap_threads_per_host: StrictInt | None = Field(default=None, ge=1, le=MAX_ZAP_THREADS_PER_HOST)


def narrow_limits(limits: RunLimits, override: LimitsOverride) -> RunLimits:
    """Aplica limites menores ou iguais aos do perfil.

    Returns:
        Novos limites; cada campo é o menor entre o do perfil e o pedido.

    Raises:
        ConfigError: Se algum valor pedido for MAIOR que o do perfil.
    """
    pairs = {
        "requests_per_second": (limits.requests_per_second, override.requests_per_second),
        "max_duration_minutes": (limits.max_duration_minutes, override.max_duration_minutes),
        "zap_threads_per_host": (limits.zap_threads_per_host, override.zap_threads_per_host),
    }
    widened = [name for name, (current, wanted) in pairs.items() if wanted and wanted > current]
    if widened:
        raise ConfigError(
            "A sobrescrita amplia limites do perfil: " + ", ".join(sorted(widened)) + ".",
            hint=_HINT,
        )
    return RunLimits(
        requests_per_second=override.requests_per_second or limits.requests_per_second,
        max_duration_minutes=override.max_duration_minutes or limits.max_duration_minutes,
        zap_threads_per_host=override.zap_threads_per_host or limits.zap_threads_per_host,
    )


def narrow_scope(scope: Scope, override: ScopeOverride) -> Scope:
    """Aplica restrições ao escopo sem nunca ampliá-lo.

    Returns:
        Novo escopo com um subconjunto das regras (hosts, métodos e caminhos) e com as
        negações do perfil mais as pedidas.

    Raises:
        ConfigError: Se a sobrescrita citar host, método ou caminho que o escopo do perfil
            não cobre (isso seria ampliar).
    """
    rules = list(scope.allow)
    if override.hosts is not None:
        rules = _keep_hosts(rules, override.hosts)
    if override.methods is not None:
        rules = _keep_methods(rules, override.methods)
    if override.paths is not None:
        rules = _keep_paths(rules, override.paths)
    if not rules:
        raise ConfigError(
            "A sobrescrita deixaria o escopo sem nenhuma regra de permissão.",
            hint="Informe ao menos um host, método ou caminho do perfil, ou omita a flag.",
        )
    return Scope(
        allow=tuple(rules),
        deny_paths=tuple(dict.fromkeys((*scope.deny_paths, *override.deny_paths))),
    )


def _widening(what: str) -> ConfigError:
    return ConfigError(f"A sobrescrita amplia o escopo: {what} não está no perfil.", hint=_HINT)


def _keep_hosts(rules: list[ScopeRule], hosts: tuple[str, ...]) -> list[ScopeRule]:
    wanted = {parse_host(host).text for host in hosts}
    if not wanted <= {rule.host for rule in rules}:
        raise _widening("host pedido")
    return [rule for rule in rules if rule.host in wanted]


def _keep_methods(rules: list[ScopeRule], methods: tuple[str, ...]) -> list[ScopeRule]:
    wanted = set(methods)
    if not wanted <= {method for rule in rules for method in rule.methods}:
        raise _widening("método pedido")
    kept: list[ScopeRule] = []
    for rule in rules:
        common = sorted(wanted & set(rule.methods))
        if common:
            # Sem revalidar: `common` é subconjunto de métodos já validados.
            kept.append(rule.model_copy(update={"methods": tuple(common)}))
    return kept


def _keep_paths(rules: list[ScopeRule], paths: tuple[str, ...]) -> list[ScopeRule]:
    wanted = [parse_pattern(path) for path in paths]
    kept: list[ScopeRule] = []
    covered: set[tuple[str, ...]] = set()
    for rule in rules:
        allowed = [parse_pattern(path) for path in rule.paths]
        inside = [p for p in wanted if any(covers(a, p) for a in allowed)]
        covered.update(inside)
        if inside:
            kept.append(
                rule.model_copy(update={"paths": tuple(dict.fromkeys(map(format_pattern, inside)))})
            )
    if not all(pattern in covered for pattern in wanted):
        raise _widening("caminho pedido")
    return kept
