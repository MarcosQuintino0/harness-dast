"""Prova do Nuclei como segundo motor no laboratório (ADR 0122, aceites 2 a 6).

Só contra os alvos do laboratório, em contêineres com dados sintéticos: o alvo Spring com o
Actuator aberto (`lab/actuator`), a Clínica Piloto (login por `-sf`), o VAmPI e o crAPI (ruído).
Todo tráfego ao alvo sai pelo `hdast` ou pelo contêiner do Nuclei atrás da `scope-proxy-nuclei`;
o teste só LÊ as trilhas de auditoria, o Docker e os arquivos da execução.

Aprovação do escopo: só a do suporte de integração (`LabCli.approve_installed_products`), que faz
o papel da pessoa nos testes de laboratório; nenhum `profile approve` é rodado. O papel da carta
(`extra_checks.*`) é feito na CÓPIA descartável de cada perfil, como nos outros testes.

Medidas (não asserções) vão para `HDAST_IT_METRICS_DIR/lab-nuclei-*.json`.
"""

import json
import os
import secrets
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from harness_dast.adapters.docker.compose import DockerComposeCli
from harness_dast.adapters.nuclei.engine import DockerNucleiEngine
from harness_dast.adapters.nuclei.manifest_reader import load_nuclei_manifest
from harness_dast.adapters.nuclei.secrets_file import NucleiSecretsFile
from harness_dast.application.lab_targets import PILOT_PROJECT
from harness_dast.application.nuclei import NUCLEI_PROXY_URL, Nuclei, NucleiRequest
from harness_dast.application.nuclei_ports import TEMPLATES_MOUNT, NucleiRunSpec, NucleiSecret
from harness_dast.application.stack import stack_compose_env
from harness_dast.application.stack_images import NUCLEI_SERVICE, OWN_SERVICES, use_local_build
from harness_dast.cli.composition import open_network
from harness_dast.cli.nuclei_composition import build_nuclei
from harness_dast.cli.stack_composition import build_stack_images, open_state_store
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.nuclei_command import NucleiCommandInput, build_nuclei_args
from harness_dast.domain.nuclei_manifest import veto_reasons
from harness_dast.observability.logging import SecretRegistry
from tests.integration.lab_images import PREBUILT_MODE
from tests.integration.lab_support import (
    PILOT_PROFILE,
    REPO,
    VAMPI_OPENAPI,
    VAMPI_PROFILE,
    LabCli,
    read_jsonl,
    require_docker,
    stack_suffix,
)
from tests.integration.run_support import files_containing, record_metrics, throwaway_pilot_env

pytestmark = [pytest.mark.integration, pytest.mark.lab_prova]

ACTUATOR = "alvo-actuator"
ACTUATOR_PROFILE = REPO / "lab" / "actuator" / "product-profile"
ACTUATOR_BASE = "http://alvo-actuator:8080"
PILOT_BASE = "http://clinica-piloto:8080"
CRAPI_PROFILE = REPO / "lab" / "crapi" / "product-profile"
CRAPI_OPENAPI = REPO / "lab" / "crapi" / "openapi.json"
DENY_PATHS = ("/actuator/heapdump", "/actuator/shutdown")
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# As 13 detecções do Actuator do spike (relatório de 2026-11-19). Pela regra do ADR 0122, as duas
# que são só identificação de tecnologia (`springboot-actuator` e `springboot-whitelabel`) vão
# para "Tecnologias identificadas" e não contam como achado: 11 exposições viram achados.
ACTUATOR_FINDINGS = frozenset(
    {
        "springboot-env",
        "springboot-configprops",
        "springboot-beans",
        "springboot-mappings",
        "springboot-threaddump",
        "springboot-loggers",
        "springboot-metrics",
        "springboot-caches",
        "springboot-conditions",
        "springboot-health",
        "springboot-scheduledtasks",
    }
)
ACTUATOR_TECHNOLOGY = "springboot-actuator"
ACTUATOR_DETECTIONS = 13
STACK_UP_SECONDS = 1500
NUCLEI_CLI_SECONDS = 1800
SAMPLE_PERIOD = 0.15


@pytest.fixture(autouse=True)
def _need_docker_and_clone() -> None:
    require_docker()
    if os.environ.get(PREBUILT_MODE) == "1":
        pytest.skip(
            "As imagens do Nuclei e do alvo Actuator ainda não entram no modo pré-construído "
            "(`lab_images`); esta prova constrói as próprias."
        )


# ------------------------------------------------------------------------------------ apoio


def _docker(*args: str, timeout: int = 30) -> str:
    docker = shutil.which("docker")
    assert docker is not None
    done = subprocess.run(  # noqa: S603 - só consultas de controle, argumentos fixos
        [docker, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return done.stdout


def _host_processes() -> str:
    ps = shutil.which("ps")
    assert ps is not None
    done = subprocess.run(  # noqa: S603 - lista os processos do próprio host de teste
        [ps, "-eww", "-o", "args="],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    return done.stdout


def _runner_stdin(container_name: str) -> list[str]:
    """Destino da entrada padrão (fd 0) dos processos `docker ... run ... --name <contêiner>`."""
    found: list[str] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (
                (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace")
            )
            if "--name" in command and container_name in command and " run " in command:
                found.append(os.readlink(entry / "fd" / "0"))
        except OSError:
            continue
    return found


class ContainerSampler(threading.Thread):
    """Amostra `docker inspect`, `docker top` e a lista de processos do host enquanto o
    contêiner cujo nome começa por `prefix` existe (o Nuclei é de uso único e some ao terminar).
    """

    def __init__(self, prefix: str) -> None:
        super().__init__(daemon=True)
        self.prefix = prefix
        self.inspects: list[str] = []
        self.tops: list[str] = []
        self.host_processes: list[str] = []
        self.runner_stdin: list[str] = []
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            names = _docker(
                "ps", "--filter", f"name={self.prefix}", "--format", "{{.Names}}"
            ).split()
            for name in names:
                text = _docker("inspect", name)
                if '"Config"' in text:
                    self.inspects.append(text)
                top = _docker("top", name)
                if top:
                    self.tops.append(top)
            if names:
                self.host_processes.append(_host_processes())
                self.runner_stdin.extend(_runner_stdin(self.prefix))
            self._halt.wait(SAMPLE_PERIOD)

    def finish(self) -> None:
        self._halt.set()
        self.join(30)

    def containers(self) -> list[dict[str, Any]]:
        """Cada amostra de `docker inspect`, já lida como JSON."""
        found: list[dict[str, Any]] = []
        for text in self.inspects:
            loaded = json.loads(text)
            found.extend(item for item in loaded if isinstance(item, dict))
        return found


def _rows(directory: Any) -> list[dict[str, Any]]:
    return read_jsonl(Path(str(directory)) / "audit.jsonl")


def _fence_rows(cli: LabCli) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Auditoria da cerca do ZAP e da cerca do Nuclei da pilha atual."""
    state = cli.state_file()
    return _rows(state["audit_dir"]), _rows(state["nuclei_audit_dir"])


def _nuclei_json(cli: LabCli, run_id: str) -> dict[str, Any]:
    loaded = json.loads((cli.runs / run_id / "nuclei.json").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _edit_profile(cli: LabCli, product: str, edit: Callable[[dict[str, Any]], None]) -> None:
    """Faz o papel da carta na CÓPIA descartável do perfil (antes do `stack up`)."""
    target = cli.products / product / "target.yml"
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    edit(data)
    target.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _nuclei_extra(*, login: bool = False, wide: bool = False) -> Callable[[dict[str, Any]], None]:
    def edit(data: dict[str, Any]) -> None:
        data["extra_checks"] = {"nuclei": True, "nuclei_login": login, "nuclei_wide_paths": wide}

    return edit


def _probe_run_id(cli: LabCli, product: str, *flags: str) -> str:
    probe = cli.run("probe", product, *flags, timeout=900)
    assert probe.code == 0, probe.stdout[-800:]
    return str(probe.envelope["run_id"])


@contextmanager
def _stack(
    tmp_path: Path,
    product: str,
    source: Path,
    *,
    env: Mapping[str, str] | None = None,
    extra_files: tuple[Path, ...] = (),
    edit: Callable[[dict[str, Any]], None] | None = None,
    flags: tuple[str, ...] = (),
) -> Iterator[LabCli]:
    """Sobe a pilha de um produto com o perfil editado e a derruba no fim."""
    cli = LabCli(tmp_path, {"HDAST_ZAP_API_KEY": secrets.token_hex(32), **(env or {})})
    cli.install_product(product, source, extra_files)
    if edit is not None:
        _edit_profile(cli, product, edit)
    try:
        up = cli.stack_up(product, *flags, timeout=STACK_UP_SECONDS)
        assert up.code == 0, up.stdout[-800:] + up.stderr[-400:]
        yield cli
    finally:
        cli.stack_down()


def _engine(cli: LabCli, *, poll: float = 0.5) -> DockerNucleiEngine:
    """O mesmo motor da CLI (`build_nuclei`) sobre a pilha do teste, para provas dirigidas."""
    env = dict(cli.env)
    with patch.dict(os.environ, env, clear=True):
        state = open_state_store().load()
        assert state is not None
        images = build_stack_images()
        refs = images.references((*OWN_SERVICES, NUCLEI_SERVICE), local=use_local_build(os.environ))
        compose_env = {**stack_compose_env(state), **images.compose_env(refs)}
    return DockerNucleiEngine(
        DockerComposeCli(env), state.projects[0], compose_env, poll_seconds=poll
    )


def _spec(
    base_url: str, templates: tuple[str, ...], *, rate: int, timeout: int, name: str
) -> NucleiRunSpec:
    args = build_nuclei_args(
        NucleiCommandInput(
            target_url=base_url,
            proxy_url=NUCLEI_PROXY_URL,
            requests_per_second=rate,
            concurrency=min(5, rate),
            templates_list_path=TEMPLATES_MOUNT,
        )
    )
    return NucleiRunSpec(
        args=args,
        templates=templates,
        secrets_path=None,
        timeout_seconds=timeout,
        container_name=name,
    )


def _container_exists(name: str) -> bool:
    return bool(_docker("ps", "-a", "--filter", f"name={name}", "--format", "{{.Names}}").strip())


def _fence_health(service: str) -> str:
    names = _docker(
        "ps",
        "-a",
        "--filter",
        f"label=com.docker.compose.service={service}",
        "--filter",
        f"label=com.docker.compose.project=hdast{stack_suffix()}",
        "--format",
        "{{.Names}}",
    ).split()
    assert len(names) == 1, names
    return _docker("inspect", "--format", "{{.State.Health.Status}}", names[0]).strip()


def _selected(permissions_writes: bool = False) -> tuple[str, ...]:
    """Modelos do manifesto sem veto, só de leitura (a escolha do domínio sem escrita)."""
    from harness_dast.domain.nuclei_manifest import NucleiPermissions, select_templates

    manifest = load_nuclei_manifest()
    return select_templates(manifest, NucleiPermissions(writes=permissions_writes)).paths


def _summary(findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_severity: dict[str, int] = {}
    for item in findings:
        severity = str(item["proposed_severity"])
        by_severity[severity] = by_severity.get(severity, 0) + 1
    return {
        "findings": len(findings),
        "by_severity": by_severity,
        "templates": sorted({str(i["record"]["template_id"]) for i in findings}),
    }


# ------------------------------------------------------------- alvo Spring (aceites 2 a 4 e 6)


@dataclass
class ActuatorLab:
    """O que a pilha do alvo Spring produziu, medido com ela no ar."""

    cli: LabCli
    run_id: str
    nuclei: dict[str, Any]
    cli_result_code: int
    seconds: float
    zap_before: int
    zap_after_nuclei: int
    nuclei_before: int
    nuclei_after_nuclei: int
    zap_after_scan: int = 0
    nuclei_after_scan: int = 0
    scan_code: int = -1
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def findings(self) -> list[dict[str, Any]]:
        return list(self.nuclei["findings"])


@pytest.fixture(scope="class")
def actuator(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ActuatorLab]:
    require_docker()
    root = tmp_path_factory.mktemp("nuclei-actuator")
    env = {"ACTUATOR_API_KEY": secrets.token_hex(16)}
    with _stack(root, ACTUATOR, ACTUATOR_PROFILE, env=env) as cli:
        run_id = _probe_run_id(cli, ACTUATOR)
        zap_before, nuclei_before = (len(r) for r in _fence_rows(cli))
        started = time.monotonic()
        done = cli.run("nuclei", ACTUATOR, "--run", run_id, timeout=NUCLEI_CLI_SECONDS)
        seconds = round(time.monotonic() - started, 1)
        zap_mid, nuclei_mid = (len(r) for r in _fence_rows(cli))
        lab = ActuatorLab(
            cli,
            run_id,
            _nuclei_json(cli, run_id),
            done.code,
            seconds,
            zap_before,
            zap_mid,
            nuclei_before,
            nuclei_mid,
        )
        scan = cli.run(
            "scan", ACTUATOR, "--run", run_id, "--max-minutes", "5", "--only", "ping", timeout=900
        )
        lab.scan_code = scan.code
        lab.zap_after_scan, lab.nuclei_after_scan = (len(r) for r in _fence_rows(cli))
        yield lab
        record_metrics(
            "lab-nuclei-actuator",
            {
                "nuclei_seconds": seconds,
                "nuclei_exit_code": done.code,
                "status": lab.nuclei["status"],
                "templates_selected": lab.nuclei["templates_selected"],
                "excluded": lab.nuclei["excluded"],
                "findings": _summary(lab.findings),
                "technologies": [t["record"]["template_id"] for t in lab.nuclei["technologies"]],
                "nuclei_fence_rows": nuclei_mid - nuclei_before,
                "zap_fence_rows_during_nuclei": zap_mid - zap_before,
                "scan_exit_code": scan.code,
                "zap_fence_rows_during_scan": lab.zap_after_scan - zap_mid,
                "nuclei_fence_rows_during_scan": lab.nuclei_after_scan - nuclei_mid,
                **lab.extras,
            },
        )


class TestActuatorTarget:
    """Alvo Spring com o Actuator aberto: aceites 2, 3, 4 e 6."""

    def test_aceite_2_cada_cerca_so_ve_o_trafego_do_proprio_motor(
        self, actuator: ActuatorLab
    ) -> None:
        assert actuator.cli_result_code in {0, 1}, actuator.nuclei["status"]
        assert actuator.nuclei_after_nuclei > actuator.nuclei_before
        # O Nuclei sem login não faz nenhum pedido pela cerca do ZAP.
        assert actuator.zap_after_nuclei == actuator.zap_before
        # O scan do ZAP (uma operação) passa pela cerca de hoje e nunca pela do Nuclei.
        assert actuator.scan_code in {0, 3}
        assert actuator.zap_after_scan > actuator.zap_after_nuclei
        assert actuator.nuclei_after_scan == actuator.nuclei_after_nuclei

    def test_aceite_3_acha_os_achados_do_actuator_sem_selecao_manual(
        self, actuator: ActuatorLab
    ) -> None:
        assert actuator.nuclei["status"] == "completed"
        found = {str(f["record"]["template_id"]) for f in actuator.findings}
        technologies = {str(t["record"]["template_id"]) for t in actuator.nuclei["technologies"]}
        assert found >= ACTUATOR_FINDINGS, sorted(ACTUATOR_FINDINGS - found)
        assert ACTUATOR_TECHNOLOGY in technologies, sorted(technologies)
        # Sem escolha manual: o catálogo inteiro que o domínio admite, não uma lista do teste.
        assert actuator.nuclei["templates_selected"] > 5000
        # Lido ao pé da letra, o aceite pede 13 achados no total (e há mais do que isso).
        assert len(actuator.findings) >= ACTUATOR_DETECTIONS, sorted(found)
        actuator.extras["actuator_findings_found"] = len(ACTUATOR_FINDINGS & found)
        actuator.extras["actuator_technologies_found"] = sorted(technologies)
        actuator.extras["spike_whitelabel_detected"] = "springboot-whitelabel" in technologies

    def test_aceite_3_pedidos_batem_com_a_auditoria_e_ficam_nas_origens_aprovadas(
        self, actuator: ActuatorLab
    ) -> None:
        _, nuclei_rows = _fence_rows(actuator.cli)
        rows = nuclei_rows[actuator.nuclei_before : actuator.nuclei_after_nuclei]
        assert rows
        origin = ("alvo-actuator", 8080, "http")
        # Só a origem aprovada recebe pedido liberado; o que os modelos tentaram fora dela
        # (hosts de OAST, `localhost`, outras portas) foi negado pela cerca e consta da trilha.
        allowed_rows = [r for r in rows if r["decision"] == "allow"]
        assert {(r["host"], r["port"], r["scheme"]) for r in allowed_rows} == {origin}
        outside = [r for r in rows if (r["host"], r["port"], r["scheme"]) != origin]
        assert all(r["decision"] == "deny" for r in outside)
        actuator.extras["attempts_outside_origin_all_denied"] = len(outside)
        actuator.extras["outside_origin_hosts"] = sorted({str(r["host"]) for r in outside})[:20]
        allowed = {(r["method"], r["path"]) for r in allowed_rows}
        for finding in actuator.findings:
            record = finding["record"]
            assert (record["method"] or "GET", record["matched_path"]) in allowed, record[
                "template_id"
            ]
        # Nenhum pedido liberado acerta um deny_paths; o que o Nuclei tentou ali foi negado.
        on_denied = [r for r in rows if r["path"] in DENY_PATHS]
        assert all(r["decision"] == "deny" for r in on_denied)
        actuator.extras["denied_path_attempts"] = len(on_denied)
        actuator.extras["audit_allow"] = sum(r["decision"] == "allow" for r in rows)
        actuator.extras["audit_deny"] = sum(r["decision"] == "deny" for r in rows)
        actuator.extras["audit_deny_reasons"] = sorted(
            {str(r["reason"]) for r in rows if r["decision"] == "deny"}
        )

    def test_aceite_4_sem_permissao_de_escrita_nenhum_metodo_de_escrita_passa_a_cerca(
        self, actuator: ActuatorLab
    ) -> None:
        _, nuclei_rows = _fence_rows(actuator.cli)
        rows = nuclei_rows[actuator.nuclei_before : actuator.nuclei_after_nuclei]
        assert {r["method"] for r in rows if r["decision"] == "allow"} <= READ_METHODS
        assert all(r["decision"] == "deny" for r in rows if r["method"] == "CONNECT")
        # Prova da cerca em si: modelos de ESCRITA do catálogo, forçados pelo motor (fora da
        # escolha do domínio), batem na segunda cerca e todos os pedidos de escrita são negados.
        manifest = load_nuclei_manifest()
        writers = tuple(
            sorted(
                e.path
                for e in manifest.entries
                if not veto_reasons(e) and set(e.methods) & WRITE_METHODS
            )
        )[:30]
        assert writers, "o manifesto não tem modelo de escrita sem veto"
        engine = _engine(actuator.cli)
        before = len(_fence_rows(actuator.cli)[1])
        run = engine.run(
            _spec(ACTUATOR_BASE, writers, rate=25, timeout=180, name="hdast-nuclei-p8-escrita"),
            lambda: False,
        )
        engine.discard(run.raw_jsonl)
        attempts = _fence_rows(actuator.cli)[1][before:]
        writes = [r for r in attempts if r["method"] in WRITE_METHODS]
        assert writes, "nenhum pedido de escrita chegou à cerca: a prova ficaria vazia"
        assert all(r["decision"] == "deny" for r in writes)
        actuator.extras["write_templates_forced"] = len(writers)
        actuator.extras["write_requests_at_fence"] = len(writes)
        actuator.extras["write_requests_allowed"] = sum(r["decision"] == "allow" for r in writes)
        actuator.extras["write_deny_reasons"] = sorted({str(r["reason"]) for r in writes})
        actuator.extras["write_methods_seen"] = sorted({str(r["method"]) for r in writes})

    def test_aceite_2_e_6_prazo_curto_derruba_o_conteiner_so_na_zap_net_e_sem_entrada_padrao(
        self, actuator: ActuatorLab
    ) -> None:
        name = "hdast-nuclei-p8-prazo"
        # `-rl 1` com centenas de modelos leva minutos; o prazo de 4 s estoura bem antes.
        spec = _spec(ACTUATOR_BASE, _selected()[:300], rate=1, timeout=4, name=name)
        engine = _engine(actuator.cli)
        sampler = ContainerSampler(name)
        sampler.start()
        started = time.monotonic()
        try:
            with pytest.raises(ExternalToolError):
                engine.run(spec, lambda: False)
        finally:
            elapsed = round(time.monotonic() - started, 1)
            sampler.finish()
        assert not _container_exists(name)
        assert elapsed < 60
        seen = sampler.containers()
        assert seen, "o amostrador não viu o contêiner do Nuclei"
        for item in seen:
            networks = set(item["NetworkSettings"]["Networks"])
            assert len(networks) == 1, networks
            assert next(iter(networks)).endswith("_zap_net"), networks
            config = item["Config"]
            actuator.extras.setdefault(
                "container_stdin_flags",
                {k: config[k] for k in ("OpenStdin", "StdinOnce", "AttachStdin", "Tty")},
            )
            assert config["Cmd"][config["Cmd"].index("-proxy") + 1] == NUCLEI_PROXY_URL
            assert not any("proxy" in e.lower() for e in config["Env"]), "proxy no ambiente"
            assert item["HostConfig"]["CapDrop"] == ["ALL"]
            assert item["HostConfig"]["ReadonlyRootfs"] is True
        # A entrada padrão do processo `docker compose run` é /dev/null (lição do spike).
        assert sampler.runner_stdin, "o amostrador não achou o processo do `docker compose run`"
        assert set(sampler.runner_stdin) == {"/dev/null"}, set(sampler.runner_stdin)
        actuator.extras["runner_stdin_samples"] = len(sampler.runner_stdin)
        actuator.extras["deadline_seconds_until_error"] = elapsed
        actuator.extras["deadline_timeout_seconds"] = 4
        actuator.extras["inspect_samples"] = len(seen)

    def test_run_encadeado_tem_a_etapa_nuclei(self, actuator: ActuatorLab) -> None:
        started = time.monotonic()
        done = actuator.cli.run(
            "run", ACTUATOR, "--no-authz", "--no-negative", timeout=NUCLEI_CLI_SECONDS
        )
        seconds = round(time.monotonic() - started, 1)
        assert done.code in {0, 1, 3}, done.stdout[-800:]
        run_id = str(done.envelope["run_id"])
        summary = json.loads((actuator.cli.runs / run_id / "run.json").read_text(encoding="utf-8"))
        stages = {s["name"]: s for s in summary["stages"]}
        assert stages["nuclei"]["status"] == "ok", stages["nuclei"]
        assert summary["nuclei_templates_selected"] > 0
        actuator.extras["run_exit_code"] = done.code
        actuator.extras["run_seconds"] = seconds
        actuator.extras["run_nuclei_stage"] = stages["nuclei"]
        actuator.extras["run_nuclei_findings_by_severity"] = summary["nuclei_findings_by_severity"]


# ---------------------------------------------------------- prazo curto de ponta a ponta (6)


class TestShortDeadlineEndToEnd:
    """O prazo do perfil (1 minuto, 1 pedido por segundo) estoura no `hdast nuclei`."""

    def test_aceite_6_prazo_do_perfil_estourado_nao_deixa_conteiner(self, tmp_path: Path) -> None:
        def edit(data: dict[str, Any]) -> None:
            _nuclei_extra(wide=True)(data)
            data["limits"].update({"requests_per_second": 1, "max_duration_minutes": 1})

        with _stack(
            tmp_path, ACTUATOR, ACTUATOR_PROFILE, env={"ACTUATOR_API_KEY": "x" * 24}, edit=edit
        ) as cli:
            run_id = _probe_run_id(cli, ACTUATOR)
            started = time.monotonic()
            done = cli.run("nuclei", ACTUATOR, "--run", run_id, timeout=600)
            seconds = round(time.monotonic() - started, 1)
            assert not _container_exists("hdast-nuclei-")
            # O portão da CLI para o Nuclei no prazo do perfil e devolve o resultado parcial
            # (saída 3, `stopped_deadline`); o prazo do contêiner é só a rede de segurança.
            assert done.code == 3, done.stdout[-600:]
            assert done.data["status"] == "stopped_deadline"
            assert 55 <= seconds <= 90, seconds
            assert (cli.runs / run_id / "nuclei.json").is_file()
            error = done.envelope.get("error") or {}
            data = done.data
            record_metrics(
                "lab-nuclei-prazo-do-perfil",
                {
                    "exit_code": done.code,
                    "seconds": seconds,
                    "error_code": error.get("code") if isinstance(error, dict) else None,
                    "status": data.get("status"),
                    "findings": len(data.get("findings", [])),
                },
            )


# ------------------------------------------------------------- segunda cerca desligada (7)


class TestSecondFenceDeniesAll:
    """Perfil sem `extra_checks.nuclei`: a segunda cerca sobe, saudável, negando tudo."""

    def test_sem_nuclei_no_perfil_a_cerca_sobe_saudavel_e_nega_tudo(self, tmp_path: Path) -> None:
        with _stack(
            tmp_path,
            ACTUATOR,
            ACTUATOR_PROFILE,
            env={"ACTUATOR_API_KEY": "y" * 24},
            edit=lambda data: data.pop("extra_checks", None),
        ) as cli:
            status = cli.run("stack", "status")
            assert status.data["running"] is True
            assert _fence_health("scope-proxy-nuclei") == "healthy"
            state = cli.state_file()
            policy = json.loads(
                (Path(state["nuclei_policy_dir"]) / "policy.json").read_text(encoding="utf-8")
            )
            assert policy["scope"]["allow"][0]["host"] == "deny-all.example"
            assert policy["scope"]["deny_paths"] == ["/**"]
            run_id = _probe_run_id(cli, ACTUATOR)
            refused = cli.run("nuclei", ACTUATOR, "--run", run_id)
            assert refused.code != 0
            assert "extra_checks.nuclei" in refused.stdout
            # Mesmo forçado pelo motor, tudo que bate na cerca é negado.
            image_ready = bool(
                _docker("image", "inspect", "--format", "{{.Id}}", "hdast/nuclei:local").strip()
            )
            denied = 0
            if image_ready:
                engine = _engine(cli)
                before = len(_fence_rows(cli)[1])
                run = engine.run(
                    _spec(
                        ACTUATOR_BASE,
                        _selected()[:60],
                        rate=50,
                        timeout=120,
                        name="hdast-nuclei-p8-off",
                    ),
                    lambda: False,
                )
                engine.discard(run.raw_jsonl)
                rows = _fence_rows(cli)[1][before:]
                assert rows
                assert all(r["decision"] == "deny" for r in rows)
                denied = len(rows)
            record_metrics(
                "lab-nuclei-cerca-desligada",
                {
                    "health": "healthy",
                    "policy_host": policy["scope"]["allow"][0]["host"],
                    "forced_run_rows_all_denied": denied,
                    "image_available_for_forced_run": image_ready,
                },
            )


# ------------------------------------------------------------------- login por -sf (aceite 5)


class _Recorded:
    """O que o gravador espiado viu do arquivo `-sf` (o valor fica só em memória)."""

    def __init__(self) -> None:
        self.paths: list[Path] = []
        self.values: list[str] = []
        self.modes: list[int] = []
        self.owners: list[int] = []
        self.dirs: list[Path] = []


def _recording_writer(recorded: _Recorded) -> type[NucleiSecretsFile]:
    class Recording(NucleiSecretsFile):
        def write(self, secret: NucleiSecret) -> Path:
            path = super().write(secret)
            stat = path.stat()
            recorded.paths.append(path)
            recorded.dirs.append(path.parent)
            recorded.values.append(secret.value)
            recorded.modes.append(stat.st_mode & 0o777)
            recorded.owners.append(stat.st_uid)
            return path

    return Recording


def _needles(values: list[str]) -> list[str]:
    """O valor do cabeçalho, o token e cada trecho do JWT (sem nunca imprimir nenhum)."""
    found: set[str] = set()
    for value in values:
        token = value.split(" ", 1)[-1]
        found.update({value, token})
        found.update(part for part in token.split(".") if len(part) >= 16)
    return sorted(found)


def _hits(needles: list[str], texts: list[str]) -> int:
    return sum(any(n in text for n in needles) for text in texts)


@contextmanager
def _nuclei_in_process(cli: LabCli, product: str, recorded: _Recorded) -> Iterator[Nuclei]:
    """O caso de uso real do `hdast nuclei`, em processo, com o ambiente isolado do laboratório
    e o gravador do `-sf` espiado (o valor do token fica só na memória do teste).
    """
    registry = SecretRegistry()
    cli.approve_installed_products()
    with patch.dict(os.environ, dict(cli.env), clear=True):
        network = open_network(product, cli.products, registry)
        try:
            with patch(
                "harness_dast.cli.nuclei_composition.NucleiSecretsFile",
                _recording_writer(recorded),
            ):
                nuclei = build_nuclei(cli.products, registry, network)
            yield nuclei
        finally:
            network.close()


class TestLoginBySecretsFile:
    """Clínica Piloto (conta sintética do laboratório): o token nunca aparece fora do `-sf`."""

    def test_aceite_5_token_ausente_de_inspect_processos_logs_json_e_relatorio(
        self, tmp_path: Path, capfd: pytest.CaptureFixture[str]
    ) -> None:
        def edit(data: dict[str, Any]) -> None:
            _nuclei_extra(login=True)(data)

        with _stack(
            tmp_path, "clinica-piloto", PILOT_PROFILE, env=throwaway_pilot_env(), edit=edit
        ) as cli:
            run_id = _probe_run_id(cli, "clinica-piloto", "--only", "obterPerfil")
            # O `report` exige o `scan.json`: uma varredura curta (uma operação) o produz.
            scan = cli.run(
                "scan", "clinica-piloto", "--run", run_id, "--max-minutes", "5",
                "--only", "obterPerfil", timeout=900,
            )  # fmt: skip
            assert scan.code in {0, 3}, scan.stdout[-400:]
            capfd.readouterr()
            recorded = _Recorded()
            sampler = ContainerSampler("hdast-nuclei-")
            with _nuclei_in_process(cli, "clinica-piloto", recorded) as nuclei:
                sampler.start()
                started = time.monotonic()
                try:
                    result = nuclei.execute(NucleiRequest(product="clinica-piloto", run_id=run_id))
                finally:
                    seconds = round(time.monotonic() - started, 1)
                    sampler.finish()
            output = capfd.readouterr()
            report = cli.run("report", "clinica-piloto", "--run", run_id)
            assert report.code in {0, 1}, report.stdout[-400:]

            assert result.logged_in
            assert result.account is not None
            assert len(recorded.values) == 1
            needles = _needles(recorded.values)
            assert needles
            assert all(len(n) >= 16 for n in needles)
            assert sampler.inspects, "o amostrador não viu o contêiner do Nuclei"
            # O arquivo existia no modo e no dono previstos e SOME no fim (pasta inclusive).
            assert recorded.modes[0] in {0o400, 0o444}
            assert not recorded.paths[0].exists()
            assert not recorded.dirs[0].exists()

            logs = [
                _docker("logs", name, timeout=60)
                for project in (f"hdast{stack_suffix()}", f"{PILOT_PROJECT}{stack_suffix()}")
                for name in _docker(
                    "ps",
                    "-a",
                    "--filter",
                    f"label=com.docker.compose.project={project}",
                    "--format",
                    "{{.Names}}",
                ).split()
            ]
            state_dir = cli.state
            run_hits = files_containing(cli.runs, needles, [output.out, output.err])
            state_hits = files_containing(state_dir, needles, [])
            hits: dict[str, int | list[str]] = {
                "docker_inspect": _hits(needles, sampler.inspects),
                "docker_top": _hits(needles, sampler.tops),
                "host_processes": _hits(needles, sampler.host_processes),
                "container_logs": _hits(needles, logs),
                "run_files_and_output": run_hits,
                "state_files": state_hits,
            }
            record_metrics(
                "lab-nuclei-login",
                {
                    "seconds": seconds,
                    "logged_in": result.logged_in,
                    "account": result.account,
                    "templates_selected": result.templates_selected,
                    "findings": len(result.findings),
                    "secret_file_mode": oct(recorded.modes[0]),
                    "secret_file_owner_uid": recorded.owners[0],
                    "samples": {
                        "inspect": len(sampler.inspects),
                        "top": len(sampler.tops),
                        "host_processes": len(sampler.host_processes),
                        "logs_read": len(logs),
                    },
                    "report_files": sorted(
                        p.name for p in (cli.runs / run_id).iterdir() if "report" in p.name
                    ),
                    "occurrences": {
                        k: (v if isinstance(v, int) else len(v)) for k, v in hits.items()
                    },
                    "secret_file_args_seen_in_inspect": any("-sf" in t for t in sampler.inspects),
                },
            )
            assert hits["docker_inspect"] == 0
            assert hits["docker_top"] == 0
            assert hits["host_processes"] == 0
            assert hits["container_logs"] == 0
            assert hits["run_files_and_output"] == [], hits["run_files_and_output"]
            assert hits["state_files"] == [], hits["state_files"]
            nuclei_json = (cli.runs / run_id / "nuclei.json").read_text(encoding="utf-8")
            assert not any(n in nuclei_json for n in needles)
            # Só leitura com login: nenhum pedido de escrita do Nuclei chegou à cerca.
            rows = _fence_rows(cli)[1]
            assert {r["method"] for r in rows if r["decision"] == "allow"} <= READ_METHODS

    def test_aceite_5_arquivo_some_tambem_apos_falha_forcada(self, tmp_path: Path) -> None:
        with _stack(
            tmp_path,
            "clinica-piloto",
            PILOT_PROFILE,
            env=throwaway_pilot_env(),
            edit=_nuclei_extra(login=True),
        ) as cli:
            run_id = _probe_run_id(cli, "clinica-piloto", "--only", "obterPerfil")
            recorded = _Recorded()
            # Falha forçada do motor depois de o `-sf` ser gravado: o `finally` do caso de uso
            # tem de apagar o arquivo mesmo assim.
            with (
                _nuclei_in_process(cli, "clinica-piloto", recorded) as nuclei,
                patch.object(
                    DockerNucleiEngine,
                    "run",
                    side_effect=ExternalToolError("falha forçada do contêiner"),
                ),
                pytest.raises(ExternalToolError),
            ):
                nuclei.execute(NucleiRequest(product="clinica-piloto", run_id=run_id))
            assert len(recorded.paths) == 1
            assert not recorded.paths[0].exists()
            assert not recorded.dirs[0].exists()


# ------------------------------------------------------------------- ruído: VAmPI e crAPI


def _noise_metrics(
    name: str, cli: LabCli, run_id: str, done_code: int, seconds: float, origin: str
) -> dict[str, Any]:
    data = _nuclei_json(cli, run_id)
    findings = list(data["findings"])
    _, rows = _fence_rows(cli)
    metrics = {
        "product": name,
        "exit_code": done_code,
        "wall_seconds": seconds,
        "status": data["status"],
        "started_at": data["started_at"],
        "finished_at": data["finished_at"],
        "templates_selected": data["templates_selected"],
        "excluded": data["excluded"],
        "findings": _summary(findings),
        "finding_paths": sorted(
            f"{f['record']['template_id']} {f['record']['method'] or 'GET'} "
            f"{f['record']['matched_path']}"
            for f in findings
        ),
        "technologies": sorted({str(t["record"]["template_id"]) for t in data["technologies"]}),
        "fence_rows": len(rows),
        "fence_allowed": sum(r["decision"] == "allow" for r in rows),
        "fence_denied": sum(r["decision"] == "deny" for r in rows),
        "fence_methods_allowed": sorted(
            {str(r["method"]) for r in rows if r["decision"] == "allow"}
        ),
        "fence_connect_allowed": sum(
            r["method"] == "CONNECT" and r["decision"] == "allow" for r in rows
        ),
        "fence_outside_origin_allowed": sum(
            r["decision"] == "allow" and f"{r['host']}:{r['port']}" != origin for r in rows
        ),
        "fence_hosts": sorted({f"{r['host']}:{r['port']}" for r in rows}),
        "malformed_lines": data["malformed_lines"],
    }
    record_metrics(f"lab-nuclei-ruido-{name}", metrics)
    return metrics


def _assert_quiet(metrics: dict[str, Any]) -> None:
    severities = metrics["findings"]["by_severity"]
    assert severities.get("high", 0) == 0, metrics["finding_paths"]
    assert severities.get("medium", 0) == 0, metrics["finding_paths"]
    assert metrics["status"] == "completed"
    assert set(metrics["fence_methods_allowed"]) <= READ_METHODS
    assert metrics["fence_connect_allowed"] == 0
    assert metrics["fence_outside_origin_allowed"] == 0


class TestNoiseOnVampi:
    def test_nuclei_no_vampi_nao_acha_medio_ou_maior(self, tmp_path: Path) -> None:
        env = {
            "VAMPI_USER_A_USERNAME": "name1",
            "VAMPI_USER_A_PASSWORD": "pass1",
            "VAMPI_USER_B_USERNAME": "name2",
            "VAMPI_USER_B_PASSWORD": "pass2",
            "VAMPI_ADMIN_USERNAME": "admin",
            "VAMPI_ADMIN_PASSWORD": "pass1",
        }
        with _stack(
            tmp_path,
            "vampi",
            VAMPI_PROFILE,
            env=env,
            extra_files=(VAMPI_OPENAPI,),
            edit=_nuclei_extra(wide=True),
        ) as cli:
            assert cli.run("preflight", "vampi").code == 0
            run_id = _probe_run_id(cli, "vampi")
            started = time.monotonic()
            done = cli.run("nuclei", "vampi", "--run", run_id, timeout=NUCLEI_CLI_SECONDS)
            seconds = round(time.monotonic() - started, 1)
            metrics = _noise_metrics("vampi", cli, run_id, done.code, seconds, "vampi:5000")
            _assert_quiet(metrics)


class TestNoiseOnCrapi:
    def test_nuclei_no_crapi_nao_acha_medio_ou_maior(self, tmp_path: Path) -> None:
        with _stack(
            tmp_path,
            "crapi",
            CRAPI_PROFILE,
            extra_files=(CRAPI_OPENAPI,),
            edit=_nuclei_extra(wide=True),
        ) as cli:
            run_id = _probe_run_id(cli, "crapi", "--only", "get_products")
            started = time.monotonic()
            done = cli.run("nuclei", "crapi", "--run", run_id, timeout=NUCLEI_CLI_SECONDS)
            seconds = round(time.monotonic() - started, 1)
            metrics = _noise_metrics("crapi", cli, run_id, done.code, seconds, "crapi:80")
            _assert_quiet(metrics)
