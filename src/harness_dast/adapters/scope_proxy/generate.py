"""Geração da política do proxy de escopo a partir do perfil do produto.

O esquema do arquivo é definido uma única vez, em `policy.py`: este módulo monta um
`ProxyPolicy`, serializa e CONFERE o resultado relendo-o com o mesmo validador que o contêiner
usa na partida. A política nunca é mais larga que o perfil: o escopo e os limites são os do
perfil, sem acréscimo; a verificação de TLS do destino só é relaxada quando o perfil a desliga
(`environment.verify_tls: false`, que o perfil só aceita para host local) E todas as regras
são locais.

Também aciona a trava de emergência (arquivo `KILL` ao lado da política).
"""

import os
from datetime import datetime
from pathlib import Path

from harness_dast.adapters.scope_proxy.policy import (
    KILL_FLAG_NAME,
    SCHEMA_VERSION,
    ProxyPolicy,
    parse_policy,
)
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.run import RunId

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
            "tls_verify_upstream": not relax_tls,
        }
    )


class FileProxyPolicyStore:
    """Grava a política e aciona a trava no sistema de arquivos (implementa `ProxyPolicyStore`)."""

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
