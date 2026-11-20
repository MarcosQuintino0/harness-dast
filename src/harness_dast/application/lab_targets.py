"""Alvos de laboratório que o `hdast stack up` sabe anexar.

Reconhecidos pelo host de `environment.base_url` do perfil. Só dados: quais serviços subir,
em qual projeto compose e quais variáveis o alvo exige. Nada aqui decide escopo.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit

PILOT_PROJECT = "hdast-pilotrun"
"""Projeto compose do alvo piloto: distinto de `hdast-pilot` (usado à mão, com Oracle)."""
CRAPI_PROJECT = "hdast-crapi"
ACTUATOR_PROJECT = "hdast-actuator"
OAST_GATEWAY_FILE = "lab/oast/compose.yaml"
OAST_GATEWAY_SERVICE = "oast-gateway"
CRAPI_OAST_FILE = "compose.oast.yaml"

PILOT_API_PORT = 28080
PILOT_MANAGEMENT_PORT = 29091
PILOT_ORACLE_PORT = 21521
"""Porta do Oracle no host (127.0.0.1), publicada só com `stack up --oracle`, para a limpeza."""

PILOT_ORACLE_FILE = "compose.oracle-port.yaml"
PILOT_ORACLE_PROFILE = "oracle"
PILOT_ORACLE_ENV_FIXED = {
    "PILOT_DB_URL": "jdbc:oracle:thin:@//oracle:1521/FREEPDB1",
    "PILOT_DB_USER": "clinica",
    "PILOT_ORACLE_CLEANUP_CONNECTION": f"127.0.0.1:{PILOT_ORACLE_PORT}/FREEPDB1",
    "PILOT_ORACLE_CLEANUP_USER": "HDAST_LIMPEZA",
}
"""Variáveis sem segredo do modo Oracle: banco do piloto e destino/usuário da limpeza."""


@dataclass(frozen=True)
class LabTarget:
    """Alvo de laboratório.

    Attributes:
        name: Nome curto.
        host: Host do `base_url` que o identifica (nome DNS na rede interna do lab).
        main_profiles: Perfis do compose raiz a ativar.
        main_services: Serviços do compose raiz que sobem junto com a pilha base.
        attached_workdir: Pasta (relativa à raiz do repositório) de um compose próprio que é
            anexado à rede interna do lab, ou `None` quando o alvo é do compose raiz.
        attached_files: Arquivos desse compose.
        credential_env: Variáveis de credencial que o alvo exige (nomes dos `secret_ref`).
        inert_env: Variáveis que o compose exige mesmo de serviços desligados (perfil `oracle`);
            recebem um valor sem uso, porque nada as lê.
        vulnerable_env: Variável de modo vulnerável (1) ou seguro (0).
        ttl_env: Variável de vida do token, em segundos.
        project: Projeto compose do alvo anexado (sem o sufixo da pilha).
    """

    name: str
    host: str
    main_profiles: tuple[str, ...]
    main_services: tuple[str, ...]
    attached_workdir: str | None
    attached_files: tuple[str, ...]
    credential_env: tuple[str, ...]
    inert_env: tuple[str, ...]
    vulnerable_env: str
    ttl_env: str
    project: str = PILOT_PROJECT


VAMPI = LabTarget(
    name="vampi",
    host="vampi",
    main_profiles=("lab",),
    main_services=("vampi",),
    attached_workdir=None,
    attached_files=(),
    credential_env=(),
    inert_env=(),
    vulnerable_env="HDAST_VAMPI_VULNERABLE",
    ttl_env="HDAST_VAMPI_TOKEN_TTL",
)

CLINICA_PILOTO = LabTarget(
    name="clinica-piloto",
    host="clinica-piloto",
    main_profiles=(),
    main_services=(),
    attached_workdir="lab/pilot",
    attached_files=("compose.yaml", "compose.lab-net.yaml"),
    credential_env=(
        "PILOT_ADMIN_USERNAME",
        "PILOT_ADMIN_PASSWORD",
        "PILOT_MEDICO_USERNAME",
        "PILOT_MEDICO_PASSWORD",
        "PILOT_MEDICO_B_USERNAME",
        "PILOT_MEDICO_B_PASSWORD",
        "PILOT_PACIENTE_A_USERNAME",
        "PILOT_PACIENTE_A_PASSWORD",
        "PILOT_PACIENTE_B_USERNAME",
        "PILOT_PACIENTE_B_PASSWORD",
    ),
    inert_env=("PILOT_ORACLE_PASSWORD",),
    vulnerable_env="PILOT_VULNERABLE",
    ttl_env="PILOT_JWT_TTL_SECONDS",
)

CRAPI = LabTarget(
    name="crapi",
    host="crapi",
    main_profiles=(),
    main_services=(),
    attached_workdir="lab/crapi",
    attached_files=("compose.yaml",),
    credential_env=(
        "CRAPI_DB_PASSWORD",
        "CRAPI_USER_A_EMAIL",
        "CRAPI_USER_A_PASSWORD",
        "CRAPI_USER_B_EMAIL",
        "CRAPI_USER_B_PASSWORD",
    ),
    inert_env=(),
    vulnerable_env="",
    ttl_env="",
    project=CRAPI_PROJECT,
)

ALVO_ACTUATOR = LabTarget(
    name="alvo-actuator",
    host="alvo-actuator",
    main_profiles=(),
    main_services=(),
    attached_workdir="lab/actuator",
    attached_files=("compose.yaml",),
    credential_env=("ACTUATOR_API_KEY",),
    inert_env=(),
    vulnerable_env="",
    ttl_env="",
    project=ACTUATOR_PROJECT,
)

_TARGETS = (VAMPI, CLINICA_PILOTO, CRAPI, ALVO_ACTUATOR)


def lab_target_for(base_url: str) -> LabTarget | None:
    """Devolve o alvo de laboratório cujo host é o de `base_url`, ou `None`."""
    host = (urlsplit(base_url).hostname or "").lower()
    return next((target for target in _TARGETS if target.host == host), None)
