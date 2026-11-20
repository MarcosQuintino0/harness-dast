"""Escopo da segunda cerca do Nuclei (`scope-proxy-nuclei`, ADR 0122).

O que garante: deriva do escopo APROVADO do perfil a política própria do Nuclei sem nunca
ampliar origem (host, esquema e porta), `deny_paths`, limites nem janelas. Só o caminho e o
método diferem do perfil, e só dentro do que o ADR permite: caminhos amplos com `wide_paths`
(modo amplo de caminho, ADR 0026) e métodos pelas permissões.
O que não faz: não lê o perfil de disco, não decide permissões e não toca no `ScopeGuard`.
A restrição de métodos usa o campo `methods` de cada regra, que o guarda já impõe.
"""

from harness_dast.domain.nuclei_manifest import NucleiPermissions
from harness_dast.domain.nuclei_permissions import nuclei_permissions
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.run import RunLimits
from harness_dast.domain.scope import PathMode, Scope, ScopeRule
from harness_dast.domain.secret_ref import ProfileModel
from harness_dast.domain.window import ExecutionWindow

__all__ = ["NucleiScope", "build_nuclei_scope", "nuclei_methods", "nuclei_scope_for"]

_READ_METHODS = ("GET", "HEAD", "OPTIONS")
_WRITE_METHODS = ("PATCH", "POST", "PUT")
_ALL_PATHS = "/**"


class NucleiScope(ProfileModel):
    """Política da cerca do Nuclei: escopo, modo de caminho, limites e janelas.

    Attributes:
        scope: Regras de permissão e `deny_paths`.
        path_mode: `wide` só com `wide_paths`; senão `strict`.
        limits: Mesmos limites do perfil.
        windows: Mesmas janelas do perfil.
    """

    scope: Scope
    path_mode: PathMode
    limits: RunLimits
    windows: tuple[ExecutionWindow, ...]


def nuclei_methods(permissions: NucleiPermissions) -> tuple[str, ...]:
    """Métodos que a cerca do Nuclei libera: leitura sempre; escrita e `DELETE` por permissão."""
    methods = list(_READ_METHODS)
    if permissions.writes:
        methods.extend(_WRITE_METHODS)
    if permissions.delete:
        methods.append("DELETE")
    return tuple(methods)


def _origin_key(rule: ScopeRule) -> tuple[str, str, int | None, bool]:
    return (rule.host, rule.scheme, rule.port, rule.allow_local)


def _derive_rules(
    rules: tuple[ScopeRule, ...], methods: tuple[str, ...], *, wide_paths: bool
) -> tuple[ScopeRule, ...]:
    if not wide_paths:
        return tuple(rule.model_copy(update={"methods": methods}) for rule in rules)
    # Uma regra por origem distinta: o escopo amplo não cria origem, só junta as do perfil.
    unique = {_origin_key(rule): rule for rule in rules}
    return tuple(
        rule.model_copy(update={"paths": (_ALL_PATHS,), "methods": methods})
        for rule in unique.values()
    )


def build_nuclei_scope(
    profile: ProductProfile, permissions: NucleiPermissions, *, wide_paths: bool
) -> NucleiScope:
    """Deriva a política da cerca do Nuclei a partir do perfil aprovado.

    Args:
        profile: Perfil já validado; sua origem, `deny_paths`, limites e janelas são mantidos.
        permissions: Permissões da execução (escrita e `DELETE`).
        wide_paths: Libera qualquer caminho das origens aprovadas, em `path_mode: wide`.
            Com `False`, os caminhos de cada regra e o modo `strict` ficam como no perfil.

    Returns:
        A política: nunca tem origem a mais, e `deny_paths` continua vencendo.
    """
    methods = tuple(sorted(nuclei_methods(permissions)))
    scope = Scope(
        allow=_derive_rules(profile.scope.allow, methods, wide_paths=wide_paths),
        deny_paths=profile.scope.deny_paths,
    )
    return NucleiScope(
        scope=scope,
        path_mode="wide" if wide_paths else "strict",
        limits=profile.limits,
        windows=profile.scope.windows,
    )


def nuclei_scope_for(profile: ProductProfile) -> NucleiScope | None:
    """Política da cerca do Nuclei para o perfil, ou `None` com o motor desligado.

    As permissões vêm de `nuclei_permissions` e os caminhos amplos de
    `extra_checks.nuclei_wide_paths`. `None` quer dizer que a segunda cerca sobe com a política
    que nega tudo: nunca há política padrão permissiva.

    Args:
        profile: Perfil já validado e aprovado.
    """
    if not profile.extra_checks.nuclei:
        return None
    granted = nuclei_permissions(profile)
    permissions = NucleiPermissions(
        writes=granted.writes, delete=granted.delete, login=granted.login
    )
    return build_nuclei_scope(
        profile, permissions, wide_paths=profile.extra_checks.nuclei_wide_paths
    )
