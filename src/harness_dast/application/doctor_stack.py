"""Diagnóstico compartilhado do Docker, das imagens e das portas da pilha."""

from collections.abc import Mapping

from harness_dast.application.doctor_ports import HostInspector
from harness_dast.application.doctor_report import DoctorCheck, DoctorStatus, make_check
from harness_dast.application.lab_targets import (
    CLINICA_PILOTO,
    PILOT_API_PORT,
    PILOT_MANAGEMENT_PORT,
    LabTarget,
)
from harness_dast.application.stack import BASE_SERVICES, DEFAULT_PROXY_PORT, DEFAULT_ZAP_PORT
from harness_dast.application.stack_images import (
    IMAGE_RECOVERY,
    OWN_SERVICES,
    PROXY_SERVICE,
    StackImages,
    use_local_build,
)
from harness_dast.domain.errors import ConfigError, ExternalToolError

ZAP_PORT_ENV = "HDAST_ZAP_HOST_PORT"
PROXY_PORT_ENV = "HDAST_PROXY_HOST_PORT"
_MAX_PORT = 65535
_MAX_LISTED_IMAGES = 3


class DoctorStackChecks:
    """Confere os pré-requisitos da pilha sem iniciar contêineres."""

    def __init__(
        self, host: HostInspector, images: StackImages, environ: Mapping[str, str]
    ) -> None:
        """Recebe o inspetor, a seleção de imagens e a configuração de portas."""
        self._host = host
        self._images = images
        self._environ = environ

    def execute(
        self, target: LabTarget | None, *, managed: bool = False, offline: bool = False
    ) -> tuple[DoctorCheck, ...]:
        """Devolve as conferências. Em modo offline todas as imagens devem estar locais."""
        docker = self._docker_check()
        checks = [docker]
        if docker.status == "ok":
            checks.append(self._images_check(target, offline=offline))
        checks.extend(self._port_checks(target, managed=managed))
        return tuple(checks)

    def _docker_check(self) -> DoctorCheck:
        try:
            version = self._host.docker_version()
        except ExternalToolError as error:
            hint = error.hint or "Abra o Docker Desktop e espere ele terminar de subir."
            return make_check("docker", "fail", f"{error.message} {hint}")
        return make_check("docker", "ok", f"Docker {version} respondendo.")

    def _images_check(self, target: LabTarget | None, *, offline: bool) -> DoctorCheck:
        local = use_local_build(self._environ)
        try:
            services = BASE_SERVICES + (target.main_services if target else ())
            refs = self._images.references(services, local=local)
            if offline and (undeclared := sorted(set(services) - refs.keys())):
                return make_check(
                    "images",
                    "fail",
                    f"Faltam imagens declaradas no Compose para {', '.join(undeclared)}. "
                    "Restaure o compose.yaml do checkout.",
                )
            inspected = self._images.inspect(refs)
        except ExternalToolError as error:
            return make_check(
                "images", "fail", f"{error.message} Aguarde e rode hdast doctor novamente."
            )
        except ConfigError as error:
            hint = error.hint or ""
            return make_check("images", "fail", f"{error.message} {hint}".strip())

        proxy = inspected[refs[PROXY_SERVICE]]
        version_note = ""
        if proxy is not None:
            try:
                version = self._images.require_proxy_version(proxy)
            except ExternalToolError as error:
                return make_check("images", "fail", f"{error.message} {error.hint or ''}".strip())
            version_note = f" O proxy de escopo tem a versão da CLI ({version})."

        missing = [image for image, info in inspected.items() if info is None]
        if not missing:
            return make_check(
                "images", "ok", f"As {len(inspected)} imagens já estão no Docker.{version_note}"
            )
        missing_result: tuple[DoctorStatus, str] = (
            ("fail", "Prepare todas as imagens antes de iniciar a demonstração.")
            if offline
            else _missing_image_hint(refs, missing, local=local)
        )
        status, hint = missing_result
        return make_check(
            "images",
            status,
            f"Faltam {len(missing)} de {len(inspected)} imagens ({_list_images(missing)}). "
            f"{hint}{version_note}",
        )

    def _port_checks(self, target: LabTarget | None, *, managed: bool) -> list[DoctorCheck]:
        wanted = [
            (ZAP_PORT_ENV, self._environ.get(ZAP_PORT_ENV, DEFAULT_ZAP_PORT), "ZAP"),
            (
                PROXY_PORT_ENV,
                self._environ.get(PROXY_PORT_ENV, DEFAULT_PROXY_PORT),
                "proxy de escopo",
            ),
        ]
        checks = [self._port_check(name, raw, what, managed=managed) for name, raw, what in wanted]
        if target is CLINICA_PILOTO:
            for port, what in (
                (PILOT_API_PORT, "API da Clínica Piloto"),
                (PILOT_MANAGEMENT_PORT, "gestão da Clínica Piloto"),
            ):
                checks.append(self._port_check(None, str(port), what, managed=managed))
        return checks

    def _port_check(
        self, env_name: str | None, raw: str, what: str, *, managed: bool
    ) -> DoctorCheck:
        port = _parse_port(raw)
        if port is None:
            return make_check(
                f"port:{env_name or raw}",
                "fail",
                f"A porta do {what} ({raw!r}) não é um número de 1 a {_MAX_PORT}. "
                f"Corrija {env_name} ou remova a variável.",
                kind="config",
            )
        check_id = f"port:{port}"
        if self._host.port_is_free(port):
            return make_check(check_id, "ok", f"Porta {port} ({what}) livre.")
        if managed:
            return make_check(
                check_id, "ok", f"Porta {port} ({what}) em uso, provavelmente pela pilha atual."
            )
        change = f"defina {env_name} com outra porta" if env_name else "libere a porta"
        return make_check(
            check_id,
            "fail",
            f"A porta {port} ({what}) já está em uso por outro programa. Feche-o ou {change}.",
        )


def _parse_port(raw: str) -> int | None:
    if not raw.isascii() or not raw.isdigit():
        return None
    port = int(raw)
    return port if 1 <= port <= _MAX_PORT else None


def _list_images(missing: list[str]) -> str:
    shown = ", ".join(image.split("@", 1)[0] for image in missing[:_MAX_LISTED_IMAGES])
    more = len(missing) - _MAX_LISTED_IMAGES
    return shown + (f" e mais {more}" if more > 0 else "")


def _missing_image_hint(
    refs: Mapping[str, str], missing: list[str], *, local: bool
) -> tuple[DoctorStatus, str]:
    if any(refs[service] in missing for service in OWN_SERVICES):
        if local:
            return "warn", "As imagens próprias serão construídas no próximo hdast stack up."
        return "fail", IMAGE_RECOVERY
    return "warn", "As imagens auxiliares serão baixadas no próximo hdast stack up."
