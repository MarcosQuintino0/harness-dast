"""Leitura estrita e captura separada do conhecimento do produto."""

from pathlib import Path

import yaml

from harness_dast.adapters.storage.product_paths import resolve_product_file
from harness_dast.adapters.storage.strict_yaml import MAX_PROFILE_BYTES, parse_yaml_document
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.knowledge import Knowledge
from harness_dast.domain.knowledge_evidence import KnowledgeRunEvidence


class FileKnowledgeStore:
    """Lê conhecimento confinado ao produto e não substitui arquivos na captura."""

    def __init__(self, root: Path) -> None:
        """Recebe diretório de produtos."""
        self._root = root

    def read(self, product: str) -> dict[str, object] | None:
        """Lê YAML estrito; ausência não altera o comportamento legado."""
        path = resolve_product_file(self._root, product, "knowledge.yml")
        if not path.exists():
            return None
        try:
            with path.open("rb") as stream:
                data = stream.read(MAX_PROFILE_BYTES + 1)
            if len(data) > MAX_PROFILE_BYTES:
                raise ConfigError("knowledge.yml excede o tamanho permitido.")
            content = data.decode("utf-8-sig")
        except (OSError, UnicodeError):
            raise ConfigError("Não foi possível ler knowledge.yml.") from None
        return parse_yaml_document(content, "knowledge.yml")

    def write_capture(self, product: str, knowledge: object) -> str:
        """Cria cópia separada com modelo validado, sem ativação implícita."""
        model = Knowledge.from_data(knowledge)
        path = resolve_product_file(self._root, product, "knowledge.captured.yml")
        text = yaml.safe_dump(model.model_dump(mode="json"), sort_keys=False)
        try:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
        except OSError:
            raise ConfigError("Não foi possível criar knowledge.captured.yml.") from None
        return path.name


class FileKnowledgeRunStore:
    """Lê apenas artefatos de execução confinados, com limite e hash dos bytes."""

    def __init__(self, runs_dir: Path) -> None:
        """Recebe a raiz das execuções."""
        self._runs = runs_dir

    def _read(self, run_id: str, name: str, *, optional: bool = False) -> bytes | None:
        from harness_dast.domain.run_ref import require_run_id

        valid = require_run_id(run_id)
        try:
            root = self._runs.resolve(strict=True)
            directory = (root / valid).resolve(strict=True)
            path = (directory / name).resolve(strict=False)
            if directory.parent != root or path.parent != directory:
                raise ConfigError("Caminho de artefato de conhecimento inválido.")
            if optional and not path.exists():
                return None
            with path.open("rb") as stream:
                content = stream.read(16 * 1024 * 1024 + 1)
            if len(content) > 16 * 1024 * 1024:
                raise ConfigError("Artefato de conhecimento excede o limite.")
        except OSError:
            raise ConfigError("Artefato da execução ausente ou inacessível.") from None
        else:
            return content

    def read(self, run_id: str) -> "KnowledgeRunEvidence":
        """Interpreta manifesto/probe e recibos authz, sem exportar o corpo dos arquivos."""
        import hashlib
        import json

        from pydantic import TypeAdapter, ValidationError

        from harness_dast.domain.knowledge import KnowledgeEffect, KnowledgeProvenance
        from harness_dast.domain.knowledge_evidence import KnowledgeRunEvidence
        from harness_dast.domain.probe_result import ProbeResult, RunManifest

        manifest_raw = self._read(run_id, "manifest.json")
        probe_raw = self._read(run_id, "probe.json")
        authz_raw = self._read(run_id, "authz.json", optional=True)
        if manifest_raw is None or probe_raw is None:
            raise ConfigError("Artefatos obrigatórios ausentes.")
        try:
            manifest = RunManifest.model_validate_json(manifest_raw)
            probe = ProbeResult.model_validate_json(probe_raw)
            data: object = json.loads(authz_raw) if authz_raw is not None else None
            if data is not None and not isinstance(data, dict):
                raise ConfigError("authz inválido")
            obj = data if isinstance(data, dict) else {}
            effects = TypeAdapter(tuple[KnowledgeEffect, ...]).validate_python(
                obj.get("effects", [])
            )
            provenance = KnowledgeProvenance(
                run_id=run_id,
                manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
                probe_sha256=hashlib.sha256(probe_raw).hexdigest(),
                authz_sha256=hashlib.sha256(authz_raw).hexdigest() if authz_raw else None,
            )
            return KnowledgeRunEvidence(
                manifest=manifest,
                probe=probe,
                effects=effects,
                authz_product=obj.get("product"),
                authz_run_id=obj.get("run_id"),
                authz_status=obj.get("status"),
                authz_dry_run=obj.get("dry_run"),
                provenance=provenance,
            )
        except (ValidationError, ValueError, TypeError, UnicodeError):
            raise ConfigError("Artefato de conhecimento inválido ou malformado.") from None
