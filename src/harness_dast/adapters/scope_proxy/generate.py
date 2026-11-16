"""Geração da política do proxy de escopo a partir do perfil do produto.

O esquema do arquivo é definido uma única vez, em `policy.py`: este módulo monta um
`ProxyPolicy`, serializa e CONFERE o resultado relendo-o com o mesmo validador que o contêiner
usa na partida. A política nunca é mais larga que o perfil: o escopo e os limites são os do
perfil, sem acréscimo; a verificação de TLS do destino só é relaxada quando o perfil a desliga
(`environment.verify_tls: false`, que o perfil só aceita para host local) E todas as regras
são locais.

Também aciona a trava de emergência (arquivo `KILL` ao lado da política).
"""

import hashlib
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from harness_dast.adapters.scope_proxy.approval_watch import file_signature
from harness_dast.adapters.scope_proxy.policy import (
    KILL_FLAG_NAME,
    SCHEMA_VERSION,
    ApprovalBinding,
    ProxyPolicy,
    parse_policy,
)
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.proxy_deadline import stack_validity_minutes
from harness_dast.domain.run import RunId
from harness_dast.domain.scope_approval import ScopeApproval, check_approval

POLICY_FILE_NAME = "policy.json"
_WRITE_HINT = "Confira o espaço em disco e a permissão de escrita da pasta de estado."


def build_proxy_policy(profile: ProductProfile, run_id: RunId, not_after: datetime) -> ProxyPolicy:
    """Monta a política de uma execução com o escopo e os limites do perfil, sem ampliá-los.

    Raises:
        ValueError: Se `not_after` não tiver fuso (validação do esquema).
    """
    scope = profile.scope.to_scope()
    relax_tls = not profile.environment.verify_tls and all(r.allow_local for r in scope.allow)
    # `model_validate` com texto ISO 8601: o esquema recusa objeto datetime (um número
    # viraria data em silêncio), e assim o caminho de geração é o mesmo da leitura.
    return ProxyPolicy.model_validate(
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id.value,
            "scope": scope,
            "limits": profile.limits,
            "path_mode": profile.scope.path_mode,
            "not_after": not_after.isoformat(),
            "stack_minutes": stack_validity_minutes(profile),
            "tls_verify_upstream": not relax_tls,
        }
    )


class FileProxyPolicyStore:
    """Grava a política e aciona a trava no sistema de arquivos (implementa `ProxyPolicyStore`)."""

    def __init__(
        self,
        products_dir: Path | None = None,
        approvals_dir: Path | None = None,
        reload_profile: Callable[[str], ProductProfile] | None = None,
    ) -> None:
        """Recebe as fontes reais; os tres argumentos sao obrigatorios em pilha gerenciada."""
        self._products_dir = products_dir
        self._approvals_dir = approvals_dir
        self._reload_profile = reload_profile
        if any(
            value is not None for value in (products_dir, approvals_dir, reload_profile)
        ) and any(value is None for value in (products_dir, approvals_dir, reload_profile)):
            raise ValueError("Fontes da politica gerenciada incompletas")

    def _bind(self, profile: ProductProfile) -> ApprovalBinding:
        if (
            self._products_dir is None
            or self._approvals_dir is None
            or self._reload_profile is None
        ):
            raise ConfigError("Fontes da politica incompletas.", hint="Recrie a pilha.")
        target = self._products_dir / profile.product / "target.yml"
        approval_path = self._approvals_dir / f"{profile.product}.json"
        target_raw, target_stat = _read_snapshot(target)
        approval_raw, approval_stat = _read_snapshot(approval_path)
        try:
            approval = ScopeApproval.model_validate_json(approval_raw)
        except ValidationError:
            raise ConfigError(
                "Aprovacao invalida ao vincular o proxy.", hint="Revise a aprovacao."
            ) from None
        check_approval(profile, approval).ensure_approved()
        if self._reload_profile(profile.product) != profile:
            raise ConfigError("Perfil mudou ao vincular o proxy.", hint="Reinicie a pilha.")
        try:
            if (
                file_signature(target.stat()) != target_stat
                or file_signature(approval_path.stat()) != approval_stat
            ):
                raise ConfigError("Fonte alterada ao vincular proxy.", hint="Reinicie a pilha.")
        except OSError:
            raise ConfigError(
                "Fonte alterada ao vincular o proxy.", hint="Reinicie a pilha."
            ) from None
        return ApprovalBinding(
            product=profile.product,
            approval_sha256=hashlib.sha256(approval_raw).hexdigest(),
            profile_sha256=hashlib.sha256(target_raw).hexdigest(),
            authorization=profile.scope.authorization,
            windows=profile.scope.windows,
        )

    def publish(
        self, profile: ProductProfile, run_id: RunId, not_after: datetime, directory: Path
    ) -> Path:
        """Gera, valida e grava `policy.json` em `directory`; devolve o caminho do arquivo.

        Garante: o arquivo gravado passa em `parse_policy` (o mesmo validador do contêiner) e a
        gravação é atômica.

        Raises:
            ConfigError: A política gerada é inválida ou a gravação falhou.
        """
        policy = build_proxy_policy(profile, run_id, not_after)
        if self._products_dir is not None:
            policy = policy.model_copy(update={"binding": self._bind(profile)})
        raw = (policy.model_dump_json(indent=2) + "\n").encode("utf-8")
        parse_policy(raw)
        target = directory / POLICY_FILE_NAME
        temporary = directory / f".{POLICY_FILE_NAME}.tmp"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(raw)
            os.replace(temporary, target)
        except OSError:
            raise ConfigError(
                "Não foi possível gravar a política do proxy de escopo.", hint=_WRITE_HINT
            ) from None
        return target

    def trigger_kill(self, directory: Path) -> bool:
        """Cria o arquivo `KILL` em `directory`; devolve `False` se ele já existia.

        Raises:
            ConfigError: A pasta não existe ou o arquivo não pôde ser criado.
        """
        flag = directory / KILL_FLAG_NAME
        if not directory.is_dir():
            raise ConfigError(
                "A pasta da política do proxy não existe; a trava não pode ser criada.",
                hint="Confira a pasta de estado (hdast stack status) ou HDAST_SCOPE_POLICY_DIR.",
            )
        existed = flag.exists()
        try:
            flag.touch()
        except OSError:
            raise ConfigError(
                "Não foi possível criar o arquivo KILL da trava de emergência.",
                hint="Crie o arquivo KILL à mão na pasta da política do proxy.",
            ) from None
        return not existed

    def kill_active(self, directory: Path) -> bool:
        """Diz se o arquivo `KILL` existe em `directory`."""
        return (directory / KILL_FLAG_NAME).exists()


def _read_snapshot(path: Path) -> tuple[bytes, tuple[int, int, int, int, int]]:
    try:
        with path.open("rb") as handle:
            before = file_signature(os.fstat(handle.fileno()))
            raw = handle.read(1024 * 1024 + 1)
            after = file_signature(os.fstat(handle.fileno()))
        stable = before == after == file_signature(path.stat()) and len(raw) <= 1024 * 1024
    except OSError:
        raise ConfigError(
            "Nao foi possivel vincular fonte local do proxy.",
            hint="Confira as fontes e reinicie a pilha.",
        ) from None
    if not stable:
        raise ConfigError("Fonte alterada ou grande demais.", hint="Reinicie a pilha.")
    return raw, after
