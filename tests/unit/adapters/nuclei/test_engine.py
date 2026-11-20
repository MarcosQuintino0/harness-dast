"""Motor do Nuclei sobre o `ComposeRunner`: montagens, segredo, parada e limpeza."""

import threading
from pathlib import Path

import pytest

from harness_dast.adapters.nuclei.engine import DockerNucleiEngine
from harness_dast.application.nuclei_ports import (
    CATALOG_ROOT,
    SECRETS_MOUNT,
    TEMPLATES_MOUNT,
    NucleiRunSpec,
)
from harness_dast.application.stack_models import ComposeProject, OneShotResult
from harness_dast.domain.errors import ConfigError, ExternalToolError

PROJECT = ComposeProject(name="hdast-x", workdir=".", files=("compose.yaml",), profiles=("nuclei",))
MARKER = "TOKEN-SINTETICO-DO-TESTE"
ENV = {"HDAST_ZAP_API_KEY": "chave-da-pilha"}


class FakeCompose:
    """`ComposeRunner` falso com comportamento: lê as montagens e pode ficar preso até o kill."""

    def __init__(
        self,
        *,
        stdout: str = "",
        exit_code: int = 0,
        error: Exception | None = None,
        hang: bool = False,
    ) -> None:
        self.stdout = stdout
        self.exit_code = exit_code
        self.error = error
        self.hang = hang
        self.calls: list[dict[str, object]] = []
        self.mount_text: dict[str, str] = {}
        self.killed: list[str] = []
        self._released = threading.Event()

    def run_once(
        self,
        project: ComposeProject,
        env: dict[str, str],
        service: str,
        args: tuple[str, ...],
        *,
        container_name: str,
        timeout_seconds: int,
        mounts: tuple[str, ...] = (),
    ) -> OneShotResult:
        self.calls.append(
            {
                "service": service,
                "args": args,
                "env": dict(env),
                "name": container_name,
                "timeout": timeout_seconds,
                "mounts": mounts,
            }
        )
        for mount in mounts:
            source, destination, mode = mount.rsplit(":", 2)
            self.mount_text[destination] = Path(source).read_text(encoding="utf-8")
            assert mode == "ro"
        if self.error is not None:
            raise self.error
        if self.hang:
            assert self._released.wait(timeout=10)
        return OneShotResult(exit_code=self.exit_code, stdout=self.stdout)

    def kill_container(
        self, project: ComposeProject, env: dict[str, str], container_name: str
    ) -> None:
        self.killed.append(container_name)
        self._released.set()


def _spec(secrets_path: Path | None = None, **changes: object) -> NucleiRunSpec:
    data: dict[str, object] = {
        "args": ("-ni", "-t", TEMPLATES_MOUNT),
        "templates": ("http/misconfiguration/a.yaml", "http/cves/b.yaml"),
        "secrets_path": secrets_path,
        "timeout_seconds": 90,
        "container_name": "hdast-nuclei-abc",
    }
    data.update(changes)
    return NucleiRunSpec(**data)  # type: ignore[arg-type]


def _engine(compose: FakeCompose) -> DockerNucleiEngine:
    return DockerNucleiEngine(compose, PROJECT, ENV, poll_seconds=0.01)  # type: ignore[arg-type]


def test_roda_o_servico_nuclei_com_os_argumentos_e_o_prazo_da_especificacao() -> None:
    compose = FakeCompose()

    _engine(compose).run(_spec(), lambda: False)

    call = compose.calls[0]
    assert call["service"] == "nuclei"
    assert call["args"] == ("-ni", "-t", TEMPLATES_MOUNT)
    assert call["name"] == "hdast-nuclei-abc"
    assert call["timeout"] == 90


def test_lista_de_modelos_vai_montada_somente_leitura_com_caminhos_do_catalogo() -> None:
    compose = FakeCompose()

    _engine(compose).run(_spec(), lambda: False)

    assert compose.mount_text[TEMPLATES_MOUNT] == (
        f"{CATALOG_ROOT}/http/misconfiguration/a.yaml\n{CATALOG_ROOT}/http/cves/b.yaml\n"
    )
    mounts = compose.calls[0]["mounts"]
    assert isinstance(mounts, tuple)
    assert all(mount.endswith(":ro") for mount in mounts)


def test_token_nao_aparece_em_argumento_ambiente_nem_montagem_alem_do_arquivo(
    tmp_path: Path,
) -> None:
    secrets = tmp_path / "secrets.yaml"
    secrets.write_text(f"valor: {MARKER}", encoding="utf-8")
    compose = FakeCompose()

    _engine(compose).run(_spec(secrets), lambda: False)

    call = compose.calls[0]
    assert compose.mount_text[SECRETS_MOUNT] == f"valor: {MARKER}"
    assert MARKER not in repr(call["args"])
    assert MARKER not in repr(call["env"])
    assert MARKER not in repr(call["mounts"])
    assert call["env"] == ENV


def test_sem_login_nao_ha_montagem_de_segredos() -> None:
    compose = FakeCompose()

    _engine(compose).run(_spec(), lambda: False)

    assert SECRETS_MOUNT not in compose.mount_text


def test_saida_bruta_vai_para_arquivo_privado_e_discard_apaga_o_diretorio() -> None:
    compose = FakeCompose(stdout='{"a": 1}\n', exit_code=3)
    engine = _engine(compose)

    result = engine.run(_spec(), lambda: False)

    assert result.exit_code == 3
    assert result.killed is False
    assert result.raw_jsonl.read_text(encoding="utf-8") == '{"a": 1}\n'
    engine.discard(result.raw_jsonl)
    assert not result.raw_jsonl.parent.exists()
    engine.discard(result.raw_jsonl)


def test_discard_nao_apaga_arquivo_que_o_motor_nao_criou(tmp_path: Path) -> None:
    foreign = tmp_path / "nuclei.jsonl"
    foreign.write_text("x", encoding="utf-8")

    _engine(FakeCompose()).discard(foreign)

    assert foreign.exists()


def test_prazo_estourado_sobe_o_erro_e_nao_deixa_saida_bruta_nem_lista(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    compose = FakeCompose(error=ExternalToolError("O contêiner nuclei passou do prazo."))

    with pytest.raises(ExternalToolError, match="passou do prazo"):
        _engine(compose).run(_spec(), lambda: False)

    assert list(tmp_path.iterdir()) == []


def test_montagem_ou_nome_invalidos_sobem_como_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    compose = FakeCompose(error=ConfigError("Nome de contêiner inválido."))

    with pytest.raises(ConfigError, match="Nome de contêiner"):
        _engine(compose).run(_spec(container_name="Nome Ruim"), lambda: False)

    assert list(tmp_path.iterdir()) == []


def test_pedido_de_parada_derruba_o_conteiner_pelo_nome_e_devolve_a_saida_parcial() -> None:
    compose = FakeCompose(stdout='{"parcial": true}\n', exit_code=137, hang=True)
    asked = threading.Event()

    def stop() -> bool:
        asked.set()
        return True

    result = _engine(compose).run(_spec(), stop)

    assert asked.is_set()
    assert result.killed is True
    assert result.exit_code == 137
    assert compose.killed == ["hdast-nuclei-abc"]
    assert result.raw_jsonl.read_text(encoding="utf-8") == '{"parcial": true}\n'


def test_sem_pedido_de_parada_nao_derruba_o_conteiner() -> None:
    compose = FakeCompose()

    result = _engine(compose).run(_spec(), lambda: False)

    assert compose.killed == []
    assert result.killed is False


def test_falha_ao_derrubar_o_conteiner_sobe_o_erro() -> None:
    compose = FakeCompose(hang=True)

    def failing_kill(project: ComposeProject, env: dict[str, str], container_name: str) -> None:
        compose._released.set()
        raise ExternalToolError("não pôde ser encerrado", hint="docker rm -f")

    compose.kill_container = failing_kill  # type: ignore[method-assign]

    with pytest.raises(ExternalToolError, match="não pôde ser encerrado"):
        _engine(compose).run(_spec(), lambda: True)
