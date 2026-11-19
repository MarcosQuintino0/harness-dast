"""Permissões do Nuclei derivadas do perfil aprovado (ADR 0122).

O Nuclei não tem chave própria de escrita nem de `DELETE`: reaproveita as permissões que já
existem. Este módulo é puro.
"""

from typing import NamedTuple

from harness_dast.domain.profile import ProductProfile

_DELETE = "DELETE"


class NucleiProfilePermissions(NamedTuple):
    """O que o perfil permite ao Nuclei.

    Attributes:
        writes: Métodos que gravam (`POST`, `PUT`, `PATCH`) liberados.
        delete: `DELETE` liberado.
        login: Autenticação com a conta de teste do perfil liberada.
    """

    writes: bool
    delete: bool
    login: bool


def nuclei_permissions(profile: ProductProfile) -> NucleiProfilePermissions:
    """Devolve as permissões do Nuclei para o perfil; tudo `False` com o motor desautorizado.

    - `writes` exige as três escritas que já existem (`authz.allow_writes`,
      `negative.allow_writes` e `scan.allow_upload_scan`), que a pergunta 4 do pedido mínimo
      liga juntas. Uma só delas não basta.
    - `delete` exige `writes` e um método `DELETE` em alguma regra de `scope.allow` (o pedido
      explícito que o pedido mínimo e a carta já usam).
    - `login` vem de `extra_checks.nuclei_login`.

    Args:
        profile: Perfil já validado.

    Returns:
        As três permissões. Não decide escopo: a cerca continua valendo.
    """
    checks = profile.extra_checks
    if not checks.nuclei:
        return NucleiProfilePermissions(writes=False, delete=False, login=False)
    writes = (
        profile.authz.allow_writes
        and profile.negative.allow_writes
        and profile.scan.allow_upload_scan
    )
    delete = writes and any(_DELETE in rule.methods for rule in profile.scope.allow)
    return NucleiProfilePermissions(writes=writes, delete=delete, login=checks.nuclei_login)
