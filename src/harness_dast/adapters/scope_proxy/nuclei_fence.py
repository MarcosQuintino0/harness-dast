"""Leitura da política publicada na `scope-proxy-nuclei` (implementa `NucleiFence`, ADR 0122).

O que garante: só lê o `policy.json` que o `hdast stack up` gravou na pasta da segunda cerca e o
devolve como `NucleiScope` (escopo, modo de caminho, limites e janelas), para o caso de uso
comparar com o que o perfil aprovado pede. Sem pasta, sem arquivo ou com a política que nega tudo
devolve `None`; arquivo ilegível ou inválido levanta `ConfigError` (a cerca falharia fechada).
Política sem vínculo com a aprovação (`binding`) não traz as janelas e por isso nunca é igual à
esperada: falha fechada, nunca aceita.
O que não faz: não escreve, não valida a aprovação nem aciona a trava.
"""

from pathlib import Path

from harness_dast.adapters.scope_proxy.generate import DENY_ALL_NOT_AFTER, POLICY_FILE_NAME
from harness_dast.adapters.scope_proxy.policy import load_policy
from harness_dast.domain.nuclei_scope import NucleiScope

__all__ = ["FileNucleiFence"]


class FileNucleiFence:
    """Lê a política da segunda cerca na pasta de política do `StackState`."""

    def __init__(self, policy_dir: Path | None) -> None:
        """Cria o leitor.

        Args:
            policy_dir: Pasta da política da `scope-proxy-nuclei` (`StackState.nuclei_policy_dir`),
                ou `None` em estado gravado antes da segunda cerca.
        """
        self._policy_dir = policy_dir

    def published_scope(self) -> NucleiScope | None:
        """Política que a cerca do Nuclei tem agora, ou `None` sem política ou se ela nega tudo.

        Raises:
            ConfigError: Política ilegível ou inválida.
        """
        if self._policy_dir is None:
            return None
        path = self._policy_dir / POLICY_FILE_NAME
        if not path.is_file():
            return None
        policy = load_policy(path)
        if policy.not_after == DENY_ALL_NOT_AFTER:
            return None
        windows = policy.binding.windows if policy.binding is not None else ()
        return NucleiScope(
            scope=policy.scope, path_mode=policy.path_mode, limits=policy.limits, windows=windows
        )
