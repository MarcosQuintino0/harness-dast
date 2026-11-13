"""Referências de segredo citadas por um perfil."""

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.secret_ref import SecretRef


def profile_secret_refs(profile: ProductProfile) -> list[tuple[str, SecretRef]]:
    """Lista (campo do perfil, referência) de todo `secret_ref` do perfil.

    O campo é um rótulo como `auth.accounts[user_a].password`; nunca contém valor.
    """
    found: list[tuple[str, SecretRef]] = []
    for account in profile.auth.accounts:
        for name in type(account).model_fields:
            value = getattr(account, name)
            if isinstance(value, SecretRef):
                found.append((f"auth.accounts[{account.alias}].{name}", value))
    if profile.cleanup is not None:
        found.append(("cleanup.connection", profile.cleanup.connection))
    return found
