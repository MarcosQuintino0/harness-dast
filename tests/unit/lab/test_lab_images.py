"""Confere o preparo de imagens com um executor de Compose em memória."""

import os
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from harness_dast import __version__
from harness_dast.adapters.docker.compose import CommandResult
from harness_dast.domain.errors import ConfigError, ExternalToolError
from tests.integration import lab_images
from tests.integration.lab_images import (
    PILOT_IMAGE,
    PREBUILD_TIMEOUT,
    PREBUILT_TAG,
    build_session_images,
    prepare_session_images,
)


class FakeCompose:
    """Devolve o resultado do build e guarda as entradas recebidas pelo processo."""

    def __init__(self, code: int = 0) -> None:
        self.code = code
        self.commands: list[tuple[Path, list[str], float]] = []
        self.environ: dict[str, str] = {}

    def __call__(
        self, args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
    ) -> CommandResult:
        self.commands.append((cwd, args[1:], timeout))
        self.environ = dict(env)
        return CommandResult(self.code, "", "saída interna")


@pytest.fixture
def docker_env(tmp_path: Path) -> dict[str, str]:
    executable = tmp_path / ("docker.exe" if os.name == "nt" else "docker")
    executable.touch(mode=0o700)
    return {"PATH": str(tmp_path)}


def test_builds_each_project_quando_prepara_imagens(
    tmp_path: Path, docker_env: dict[str, str]
) -> None:
    compose = FakeCompose()
    repo = tmp_path / "checkout"

    build_session_images(repo, "sessao", docker_env, runner=compose)

    assert compose.commands == [
        (repo, ["compose", "-f", "compose.yaml", "build", "zap", "scope-proxy"], PREBUILD_TIMEOUT),
        (
            repo / "lab" / "pilot",
            ["compose", "-f", "compose.yaml", "-f", "compose.lab-net.yaml", "build", "pilot"],
            PREBUILD_TIMEOUT,
        ),
    ]


def test_uses_checkout_tags_quando_ambiente_tem_overrides(
    tmp_path: Path, docker_env: dict[str, str]
) -> None:
    compose = FakeCompose()
    docker_env.update(
        HDAST_SCOPE_PROXY_IMAGE="outra:imagem",
        HDAST_IMAGE_VERSION="outra",
        COMPOSE_ENV_FILES="outro-arquivo",
        PILOT_ADMIN_USERNAME="outra",
    )

    images = build_session_images(tmp_path, "sessao", docker_env, runner=compose)

    expected = {
        "HDAST_ZAP_IMAGE": "hdast/zap:sessao",
        "HDAST_SCOPE_PROXY_IMAGE": "hdast/scope-proxy:sessao",
    }
    assert images == expected
    assert {key: compose.environ[key] for key in expected} == images
    assert compose.environ["HDAST_IMAGE_VERSION"] == __version__
    assert compose.environ["PILOT_ADMIN_USERNAME"] == "lab-build"
    assert compose.environ["COMPOSE_DISABLE_ENV_FILE"] == "1"
    assert "COMPOSE_ENV_FILES" not in compose.environ


def test_reports_failure_quando_compose_recusa_build(
    tmp_path: Path, docker_env: dict[str, str]
) -> None:
    compose = FakeCompose(code=7)

    with pytest.raises(ExternalToolError, match="build de zap, scope-proxy falhou com código 7"):
        build_session_images(tmp_path, "sessao", docker_env, runner=compose)

    assert len(compose.commands) == 1


def test_reports_timeout_quando_build_ultrapassa_prazo(
    tmp_path: Path, docker_env: dict[str, str]
) -> None:
    def expires(
        args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
    ) -> CommandResult:
        raise subprocess.TimeoutExpired(args, timeout)

    with pytest.raises(ExternalToolError, match=f"ultrapassou {PREBUILD_TIMEOUT} s"):
        build_session_images(tmp_path, "sessao", docker_env, runner=expires)


class DockerFake(FakeCompose):
    """Simula o Docker: imagens com Id, marcação de identidade e contagem de builds."""

    def __init__(self, images: dict[str, str] | None = None) -> None:
        super().__init__()
        self.images = dict(images or {})
        self.builds = 0
        self.tagged: list[tuple[str, str]] = []

    def __call__(
        self, args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
    ) -> CommandResult:
        if args[1:3] == ["image", "inspect"]:
            refs = args[5:]
            if any(ref not in self.images for ref in refs):
                return CommandResult(1, "", "no such image")
            return CommandResult(0, "\n".join(self.images[ref] for ref in refs) + "\n", "")
        if args[1] == "tag":
            self.tagged.append((args[2], args[3]))
            self.images[args[3]] = self.images.get(args[2], f"sha256:novo{len(self.images)}")
            return CommandResult(0, "", "")
        self.builds += 1
        return super().__call__(args, env, cwd, timeout)


def _loaded(tag: str, identity: str, *, drift: bool = False) -> dict[str, str]:
    """Imagens como ficam depois de `docker save` e `docker load` de um checkout."""
    named = [f"hdast/zap:{tag}", f"hdast/scope-proxy:{tag}", PILOT_IMAGE]
    marked = lab_images.identity_refs(identity)
    images = {ref: f"sha256:{n}" for n, ref in enumerate(named)}
    images.update({ref: images[source] for source, ref in zip(named, marked, strict=True)})
    if drift:
        images[PILOT_IMAGE] = "sha256:outra-clinica"
    return images


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "modulo.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("leia-me\n", encoding="utf-8")
    return tmp_path


def _identity(checkout: Path) -> str:
    return f"inputs-{lab_images.inputs_hash(checkout)}"


def test_reuses_images_quando_as_tres_tem_a_identidade_do_checkout(
    checkout: Path, docker_env: dict[str, str]
) -> None:
    docker = DockerFake(_loaded("gh-abc", _identity(checkout)))
    docker_env[PREBUILT_TAG] = "gh-abc"

    images = prepare_session_images(checkout, docker_env, "outra", runner=docker)

    assert images["HDAST_ZAP_IMAGE"] == "hdast/zap:gh-abc"
    assert docker.builds == 0
    assert docker.tagged == []


def test_rebuilds_and_warns_quando_identidade_e_de_outro_checkout(
    checkout: Path, docker_env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    docker = DockerFake(_loaded("gh-abc", "inputs-antigo"))
    docker_env[PREBUILT_TAG] = "gh-abc"

    prepare_session_images(checkout, docker_env, "outra", runner=docker)

    assert docker.builds == 2
    assert [target for _, target in docker.tagged] == list(
        lab_images.identity_refs(_identity(checkout))
    )
    assert "Reconstruindo" in capsys.readouterr().err


def test_rebuilds_quando_a_clinica_com_a_tag_fixa_e_outra_imagem(
    checkout: Path, docker_env: dict[str, str]
) -> None:
    docker = DockerFake(_loaded("gh-abc", _identity(checkout), drift=True))
    docker_env[PREBUILT_TAG] = "gh-abc"

    prepare_session_images(checkout, docker_env, "outra", runner=docker)

    assert docker.builds == 2


def test_rebuilds_quando_imagens_da_tag_nao_existem(
    checkout: Path, docker_env: dict[str, str]
) -> None:
    docker = DockerFake()
    docker_env[PREBUILT_TAG] = "gh-abc"

    images = prepare_session_images(checkout, docker_env, "outra", runner=docker)

    assert images["HDAST_ZAP_IMAGE"] == "hdast/zap:gh-abc"
    assert docker.builds == 2
    assert len(docker.tagged) == 3


def test_marks_identity_quando_constroi_com_a_tag_da_sessao(
    checkout: Path, docker_env: dict[str, str]
) -> None:
    docker = DockerFake()

    images = prepare_session_images(checkout, docker_env, "sessao", runner=docker)

    assert images["HDAST_ZAP_IMAGE"] == "hdast/zap:sessao"
    assert docker.tagged[0] == ("hdast/zap:sessao", f"hdast/zap:{_identity(checkout)}")
    assert docker.tagged[2][0] == PILOT_IMAGE


def test_ignores_empty_tag_quando_variavel_esta_vazia(
    checkout: Path, docker_env: dict[str, str]
) -> None:
    docker = DockerFake()
    docker_env[PREBUILT_TAG] = ""

    images = prepare_session_images(checkout, docker_env, "sessao", runner=docker)

    assert images["HDAST_ZAP_IMAGE"] == "hdast/zap:sessao"


@pytest.mark.parametrize("tag", ["com espaço", "-inicio", "a/b", "x" * 129])
def test_rejects_tag_quando_formato_invalido(
    checkout: Path, docker_env: dict[str, str], tag: str
) -> None:
    docker = DockerFake()
    docker_env[PREBUILT_TAG] = tag

    with pytest.raises(ConfigError, match=PREBUILT_TAG):
        prepare_session_images(checkout, docker_env, "sessao", runner=docker)

    assert docker.builds == 0


def test_rebuilds_quando_conferencia_de_imagem_expira(
    checkout: Path, docker_env: dict[str, str]
) -> None:
    docker = DockerFake()

    def expires(
        args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
    ) -> CommandResult:
        if args[1:3] == ["image", "inspect"]:
            raise subprocess.TimeoutExpired(args, timeout)
        return docker(args, env, cwd, timeout)

    docker_env[PREBUILT_TAG] = "gh-abc"

    prepare_session_images(checkout, docker_env, "sessao", runner=expires)

    assert docker.builds == 2


def test_fails_quando_marcacao_de_identidade_falha(
    checkout: Path, docker_env: dict[str, str]
) -> None:
    class RefusesTag(DockerFake):
        def __call__(
            self, args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
        ) -> CommandResult:
            if args[1] == "tag":
                return CommandResult(1, "", "recusado")
            return super().__call__(args, env, cwd, timeout)

    with pytest.raises(ExternalToolError, match="marcação de identidade"):
        prepare_session_images(checkout, docker_env, "sessao", runner=RefusesTag())


def test_hash_changes_quando_arquivo_de_insumo_muda(checkout: Path) -> None:
    before = lab_images.inputs_hash(checkout)

    (checkout / "src" / "modulo.py").write_text("x = 2\n", encoding="utf-8")

    assert lab_images.inputs_hash(checkout) != before


def test_hash_changes_quando_arquivos_so_diferem_em_lf_e_crlf(checkout: Path) -> None:
    script = checkout / "docker" / "entrypoint.sh"
    script.parent.mkdir()
    script.write_bytes(b"echo ok\n")
    lf = lab_images.inputs_hash(checkout)

    script.write_bytes(b"echo ok\r\n")

    assert lab_images.inputs_hash(checkout) != lf


def test_hash_ignores_caches_quando_so_eles_mudam(checkout: Path) -> None:
    before = lab_images.inputs_hash(checkout)
    cache = checkout / "src" / "__pycache__"
    cache.mkdir()
    (cache / "x.pyc").write_bytes(b"lixo")

    assert lab_images.inputs_hash(checkout) == before


def test_hash_ignores_files_fora_dos_insumos(checkout: Path) -> None:
    before = lab_images.inputs_hash(checkout)

    (checkout / "docs").mkdir()
    (checkout / "docs" / "nota.md").write_text("fora", encoding="utf-8")

    assert lab_images.inputs_hash(checkout) == before


def _copied_sources(dockerfile: Path) -> list[str]:
    sources: list[str] = []
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts or parts[0].upper() != "COPY":
            continue
        if any(part.startswith("--from=") for part in parts[1:]):
            continue
        args = [part for part in parts[1:] if not part.startswith("--")]
        sources.extend(args[:-1])
    return sources


def _is_covered(relative: str) -> bool:
    path = relative.rstrip("/")
    return path in lab_images.INPUT_FILES or any(
        path == directory or path.startswith(f"{directory}/") for directory in lab_images.INPUT_DIRS
    )


@pytest.mark.parametrize(
    ("dockerfile", "context"),
    [
        ("docker/scope-proxy/Dockerfile", "."),
        ("docker/zap/Dockerfile", "docker/zap"),
        ("lab/pilot/Dockerfile", "lab/pilot"),
    ],
)
def test_hash_covers_every_copied_path_quando_le_os_dockerfiles(
    dockerfile: str, context: str
) -> None:
    repo = Path(lab_images.__file__).resolve().parents[2]

    for source in _copied_sources(repo / dockerfile):
        relative = (Path(context) / source).as_posix().removeprefix("./")
        assert _is_covered(relative), f"{dockerfile} copia {relative}, fora do hash de insumos"


def test_hash_covers_the_compose_files_quando_define_os_contextos() -> None:
    assert _is_covered("compose.yaml")
    assert _is_covered("lab/pilot/compose.yaml")
    assert _is_covered("docker/scope-proxy/addon.py")


def test_prints_key_quando_main_recebe_chave(capsys: pytest.CaptureFixture[str]) -> None:
    assert lab_images.main(["--chave"]) == 0

    assert re.fullmatch(r"[0-9a-f]{64}", capsys.readouterr().out.strip())


def test_prints_references_quando_main_prepara_a_tag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    refs = {"HDAST_ZAP_IMAGE": "hdast/zap:t", "HDAST_SCOPE_PROXY_IMAGE": "hdast/scope-proxy:t"}
    monkeypatch.setattr(lab_images, "prepare_session_images", lambda *_a, **_k: refs)

    assert lab_images.main(["t"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[:3] == [*refs.values(), PILOT_IMAGE]
    assert len(lines) == 6
    assert len({line.rsplit(":", 1)[1] for line in lines[3:]}) == 1


def test_rejects_usage_quando_main_nao_recebe_a_tag(capsys: pytest.CaptureFixture[str]) -> None:
    assert lab_images.main([]) == 2
    assert "Uso:" in capsys.readouterr().err
