"""Falsos com comportamento e o cenário do caso de uso `nuclei` (ADR 0122).

- `FakeNucleiEngine`: devolve um JSONL de fixtura, registra o que recebeu (argumentos, arquivo de
  segredos no instante da execução) e pode falhar, estourar o prazo ou ser derrubado pelo `KILL`.
- `FakeNucleiSecretsWriter`: grava de verdade um arquivo numa pasta do teste, para provar que ele
  existe durante a execução e some depois.
- `FakeNucleiFence`, `FakeNucleiImages` e `FakeNucleiArtifacts`: política publicada, imagem e
  `nuclei.json` em memória.
- `NucleiRig`: o perfil, o alvo falso, o relógio e o caso de uso montados.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from harness_dast.adapters.nuclei.jsonl_reader import NucleiJsonlReader
from harness_dast.application.nuclei import Nuclei
from harness_dast.application.nuclei_ports import (
    NucleiRunResult,
    NucleiRunSpec,
    NucleiSecret,
)
from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.nuclei_manifest import NucleiManifest, NucleiTemplateEntry
from harness_dast.domain.nuclei_result import NucleiResult
from harness_dast.domain.nuclei_scope import NucleiScope, nuclei_scope_for
from harness_dast.domain.nuclei_version import (
    NUCLEI_VERSION,
    TEMPLATES_ARCHIVE_SHA256,
    TEMPLATES_VERSION,
)
from harness_dast.domain.profile import ProductProfile
from tests.fakes.probe_ports import Handler, InMemoryRunStore
from tests.fakes.rig import Rig, default_handler, profile_data

RUN_ID = "2026-11-10T10-00-00Z-agenda-7f3a"
READ_TEMPLATE = "http/misconfiguration/read.yaml"
WRITE_TEMPLATE = "http/cves/write.yaml"
DELETE_TEMPLATE = "http/cves/delete.yaml"
UNSAFE_TEMPLATE = "http/cves/unsafe.yaml"


def template_entry(path: str, **changes: Any) -> NucleiTemplateEntry:
    """Metadados de um modelo, de leitura e sem veto, com ajustes."""
    parts = path.split("/")
    data: dict[str, Any] = {
        "path": path,
        "sha256": "b" * 64,
        "protocols": ["http"],
        "methods": ["GET"],
        "raw": False,
        "unsafe": False,
        "code": False,
        "headless": False,
        "oast": False,
        "dast": False,
        "unparsed_method": False,
        "tags": ["exposure"],
        "severity": "low",
        "category": parts[1] if len(parts) >= 3 else None,
    }
    data.update(changes)
    return NucleiTemplateEntry.model_validate(data)


def sample_manifest() -> NucleiManifest:
    """Um modelo de leitura, um de escrita, um de `DELETE` e um vetado."""
    return NucleiManifest(
        nuclei_version=NUCLEI_VERSION,
        templates_version=TEMPLATES_VERSION,
        templates_archive_sha256=TEMPLATES_ARCHIVE_SHA256,
        entries=(
            template_entry(READ_TEMPLATE),
            template_entry(WRITE_TEMPLATE, methods=["POST"]),
            template_entry(DELETE_TEMPLATE, methods=["DELETE"]),
            template_entry(UNSAFE_TEMPLATE, unsafe=True),
        ),
    )


def result_line(
    template_id: str = "springboot-env",
    *,
    severity: str = "medium",
    path: str = "/actuator/env",
    **extra: object,
) -> str:
    """Uma linha JSONL como o Nuclei a escreve, com os campos que a projeção deve descartar."""
    record: dict[str, object] = {
        "template-id": template_id,
        "template-path": f"http/misconfiguration/{template_id}.yaml",
        "info": {"name": "x", "severity": severity},
        "type": "http",
        "host": "api.hml.acme-teste.net.br",
        "matched-at": f"https://api.hml.acme-teste.net.br{path}",
        "method": "GET",
        "curl-command": "curl -H 'X-Marcador: CURL-SEGREDO' http://alvo",
        "request": "GET / HTTP/1.1\r\nAuthorization: Bearer REQ-SEGREDO",
        "response": "HTTP/1.1 200 OK\r\n\r\nRESP-SEGREDO",
        "extracted-results": ["EXTRAIDO-SEGREDO"],
        **extra,
    }
    return json.dumps(record)


class FakeNucleiEngine:
    """`NucleiEngine` falso: escreve o JSONL de fixtura e registra a execução."""

    def __init__(
        self,
        workdir: Path,
        *,
        lines: tuple[str, ...] = (),
        exit_code: int = 0,
        error: Exception | None = None,
        during_run: Callable[[], None] | None = None,
    ) -> None:
        self._workdir = workdir
        self.lines = lines
        self.exit_code = exit_code
        self.error = error
        self.during_run = during_run
        self.specs: list[NucleiRunSpec] = []
        self.secret_text_during_run: str | None = None
        self.stop_answers: list[bool] = []
        self.killed_containers: list[str] = []
        self.discarded: list[Path] = []
        self._count = 0

    def run(self, spec: NucleiRunSpec, stop_requested: Callable[[], bool]) -> NucleiRunResult:
        self.specs.append(spec)
        if spec.secrets_path is not None:
            self.secret_text_during_run = spec.secrets_path.read_text(encoding="utf-8")
        if self.during_run is not None:
            self.during_run()
        if self.error is not None:
            # O motor real mata o contêiner antes de o erro de prazo subir.
            self.killed_containers.append(spec.container_name)
            raise self.error
        killed = stop_requested()
        self.stop_answers.append(killed)
        if killed:
            self.killed_containers.append(spec.container_name)
        self._count += 1
        raw = self._workdir / f"raw-{self._count}.jsonl"
        raw.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        return NucleiRunResult(exit_code=self.exit_code, raw_jsonl=raw, killed=killed)

    def discard(self, raw_jsonl: Path) -> None:
        self.discarded.append(raw_jsonl)
        raw_jsonl.unlink(missing_ok=True)


class FakeNucleiSecretsWriter:
    """`NucleiSecretsWriter` falso: grava o valor num arquivo de verdade e o apaga no `remove`."""

    def __init__(self, workdir: Path) -> None:
        self._workdir = workdir
        self.written: list[Path] = []
        self.removed: list[Path] = []
        self.secrets: list[NucleiSecret] = []

    def write(self, secret: NucleiSecret) -> Path:
        path = self._workdir / f"secrets-{len(self.written)}.yaml"
        path.write_text(secret.value, encoding="utf-8")
        self.written.append(path)
        self.secrets.append(secret)
        return path

    def remove(self, path: Path) -> None:
        path.unlink(missing_ok=True)
        self.removed.append(path)


class FakeNucleiFence:
    """`NucleiFence` falso: devolve a política que o teste mandou publicar."""

    def __init__(self, scope: NucleiScope | None) -> None:
        self.scope = scope

    def published_scope(self) -> NucleiScope | None:
        return self.scope


class FakeNucleiImages:
    """`NucleiImages` falso: a instalação traz ou não o Nuclei."""

    def __init__(self, *, available: bool = True) -> None:
        self.available = available

    def require_nuclei(self) -> None:
        if not self.available:
            raise ConfigError("Sem imagem do Nuclei.", hint="Reinstale.")


class FakeNucleiArtifacts:
    """`NucleiArtifacts` falso sobre o `InMemoryRunStore` (auditoria) e um dicionário."""

    def __init__(self, store: InMemoryRunStore) -> None:
        self._store = store
        self.results: dict[str, NucleiResult] = {}
        self.serialized: dict[str, str] = {}

    def read_audit(self, run_id: str) -> tuple[AuditEntry, ...]:
        return tuple(self._store.audit.get(run_id, []))

    def write_nuclei(self, run_id: str, result: NucleiResult) -> None:
        self.results[run_id] = result
        self.serialized[run_id] = result.model_dump_json(indent=2)


class KillSwitchFake:
    """`KillSwitch` falso acionável pelo teste."""

    def __init__(self) -> None:
        self.on = False

    def engaged(self) -> bool:
        return self.on


def nuclei_profile_data(**extra_checks: bool) -> dict[str, Any]:
    """Perfil base com o Nuclei e o login ligados (a carta), com ajustes em `extra_checks`."""
    checks = {"nuclei": True, "nuclei_login": True, **extra_checks}
    return profile_data(extra_checks=checks)


class NucleiRig(Rig):
    """`Rig` com o caso de uso `nuclei` e todos os falsos."""

    def __init__(
        self,
        workdir: Path,
        *,
        profile_data_override: dict[str, Any] | None = None,
        lines: tuple[str, ...] = (),
        manifest: NucleiManifest | None = None,
        fence_scope: NucleiScope | str | None = "profile",
        images_available: bool = True,
        handler: Handler = default_handler,
    ) -> None:
        profile = ProductProfile.from_data(profile_data_override or nuclei_profile_data())
        super().__init__(profile=profile, handler=handler)
        self.kill = KillSwitchFake()
        self.engine = FakeNucleiEngine(workdir, lines=lines)
        self.writer = FakeNucleiSecretsWriter(workdir)
        scope = nuclei_scope_for(profile) if fence_scope == "profile" else fence_scope
        self.fence = FakeNucleiFence(scope if not isinstance(scope, str) else None)
        self.images = FakeNucleiImages(available=images_available)
        self.artifacts = FakeNucleiArtifacts(self.store)
        self.manifest = manifest or sample_manifest()

    def nuclei(self) -> Nuclei:
        return Nuclei(
            profiles=self.profiles,
            load_manifest=lambda: self.manifest,
            images=self.images,
            fence=self.fence,
            engine=self.engine,
            secrets_writer=self.writer,
            reader=NucleiJsonlReader(),
            artifacts=self.artifacts,
            secrets=self.secrets,
            vault=self.vault,
            client=self.target,
            store=self.store,
            clock=self.clock,
            sleeper=self.clock,
            kill_switch=self.kill,
        )
