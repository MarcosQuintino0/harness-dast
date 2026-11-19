"""Caso de uso `nuclei` (ADR 0122): recusas, escolha pelas permissões, login sem vazar e limpeza."""

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import structlog

from harness_dast.adapters.nuclei.jsonl_reader import NucleiJsonlReader
from harness_dast.application.account_session import TokenCache
from harness_dast.application.login_budget import LoginBudget
from harness_dast.application.nuclei import (
    NUCLEI_CONCURRENCY,
    NUCLEI_PROXY_URL,
    NUCLEI_RUNNER_GRACE_SECONDS,
    Nuclei,
    NucleiRequest,
)
from harness_dast.application.nuclei_ports import SECRETS_MOUNT, TEMPLATES_MOUNT
from harness_dast.application.run_support import KillSwitchEngaged
from harness_dast.domain.errors import ConfigError, ExternalToolError, PreflightError
from harness_dast.domain.nuclei_command import NUCLEI_FORBIDDEN_FLAGS
from harness_dast.domain.nuclei_result import NucleiResult
from tests.fakes.nuclei import (
    DELETE_TEMPLATE,
    READ_TEMPLATE,
    RUN_ID,
    UNSAFE_TEMPLATE,
    WRITE_TEMPLATE,
    NucleiRig,
    nuclei_profile_data,
    result_line,
)
from tests.fakes.probe_ports import reply
from tests.fakes.rig import TOKEN

REQUEST = NucleiRequest(product="agenda", run_id=RUN_ID)
FORBIDDEN_IN_OUTPUT = (
    "curl-command",
    "request",
    "response",
    "extracted-results",
    "CURL-SEGREDO",
    "REQ-SEGREDO",
    "RESP-SEGREDO",
    "EXTRAIDO-SEGREDO",
)


def _rig(tmp_path: Path, **kwargs: Any) -> NucleiRig:
    return NucleiRig(tmp_path, **kwargs)


def _writes_profile() -> dict[str, Any]:
    data = nuclei_profile_data(nuclei_login=False)
    data["authz"] = {"allow_writes": True}
    data["negative"] = {"allow_writes": True}
    data["scan"] = {"allow_upload_scan": True}
    return data


def _templates(rig: NucleiRig) -> tuple[str, ...]:
    return rig.engine.specs[0].templates


def test_recusa_quando_extra_checks_nuclei_desligado(tmp_path: Path) -> None:
    data = nuclei_profile_data(nuclei=False)
    rig = _rig(tmp_path, profile_data_override=data)

    with pytest.raises(ConfigError, match=r"extra_checks\.nuclei"):
        rig.nuclei().execute(REQUEST)

    assert rig.engine.specs == []
    assert rig.writer.written == []


def test_recusa_quando_a_politica_da_cerca_nao_esta_publicada(tmp_path: Path) -> None:
    rig = _rig(tmp_path, fence_scope=None)

    with pytest.raises(ConfigError, match="scope-proxy-nuclei"):
        rig.nuclei().execute(REQUEST)

    assert rig.engine.specs == []


def test_recusa_quando_a_politica_publicada_e_de_outro_perfil(tmp_path: Path) -> None:
    other = _rig(tmp_path, profile_data_override=_writes_profile())
    rig = _rig(tmp_path, fence_scope=other.fence.scope)

    with pytest.raises(ConfigError, match="scope-proxy-nuclei"):
        rig.nuclei().execute(REQUEST)

    assert rig.engine.specs == []


def test_recusa_quando_a_instalacao_nao_traz_a_imagem(tmp_path: Path) -> None:
    rig = _rig(tmp_path, images_available=False)

    with pytest.raises(ConfigError, match="Sem imagem"):
        rig.nuclei().execute(REQUEST)

    assert rig.engine.specs == []


def test_recusa_run_id_invalido(tmp_path: Path) -> None:
    rig = _rig(tmp_path)

    with pytest.raises(ConfigError, match="Identificador"):
        rig.nuclei().execute(NucleiRequest(product="agenda", run_id="../x"))

    assert rig.engine.specs == []


def test_sem_escrita_nenhum_modelo_de_escrita_entra_na_lista(tmp_path: Path) -> None:
    rig = _rig(tmp_path, profile_data_override=nuclei_profile_data(nuclei_login=False))

    rig.nuclei().execute(REQUEST)

    assert _templates(rig) == (READ_TEMPLATE,)


def test_com_escrita_sem_delete_no_escopo_modelo_de_delete_nao_entra(tmp_path: Path) -> None:
    data = _writes_profile()
    data["scope"]["allow"][0]["methods"] = ["GET", "POST", "PUT", "PATCH"]
    rig = _rig(tmp_path, profile_data_override=data)

    rig.nuclei().execute(REQUEST)

    assert _templates(rig) == (WRITE_TEMPLATE, READ_TEMPLATE)


def test_com_escrita_e_delete_pedido_no_escopo_modelo_de_delete_entra(tmp_path: Path) -> None:
    rig = _rig(tmp_path, profile_data_override=_writes_profile())

    rig.nuclei().execute(REQUEST)

    assert _templates(rig) == (DELETE_TEMPLATE, WRITE_TEMPLATE, READ_TEMPLATE)


def test_com_login_so_modelos_de_leitura_rodam_mesmo_com_escrita(tmp_path: Path) -> None:
    data = _writes_profile()
    data["extra_checks"]["nuclei_login"] = True
    rig = _rig(tmp_path, profile_data_override=data)

    rig.nuclei().execute(REQUEST)

    templates = _templates(rig)
    assert templates == (READ_TEMPLATE,)
    assert UNSAFE_TEMPLATE not in templates
    assert DELETE_TEMPLATE not in templates


def test_argumentos_levam_as_opcoes_fixas_e_nunca_as_proibidas(tmp_path: Path) -> None:
    rig = _rig(tmp_path, profile_data_override=nuclei_profile_data(nuclei_login=False))

    rig.nuclei().execute(REQUEST)

    args = rig.engine.specs[0].args
    assert not NUCLEI_FORBIDDEN_FLAGS & set(args)
    assert args[args.index("-proxy") + 1] == NUCLEI_PROXY_URL
    assert args[args.index("-t") + 1] == TEMPLATES_MOUNT
    assert args[args.index("-u") + 1] == "https://api.hml.acme-teste.net.br"
    assert args[args.index("-rl") + 1] == "5"
    assert args[args.index("-c") + 1] == str(min(NUCLEI_CONCURRENCY, 5))
    assert "-sf" not in args


def test_prazo_vem_do_menor_entre_o_perfil_e_o_run_encadeado(tmp_path: Path) -> None:
    rig = _rig(tmp_path, profile_data_override=nuclei_profile_data(nuclei_login=False))
    chained = rig.clock.now() + timedelta(minutes=10)

    rig.nuclei().execute(NucleiRequest(product="agenda", run_id=RUN_ID, deadline=chained))

    assert rig.engine.specs[0].timeout_seconds == 600 + NUCLEI_RUNNER_GRACE_SECONDS


def test_prazo_e_o_do_perfil_sem_run_encadeado(tmp_path: Path) -> None:
    rig = _rig(tmp_path, profile_data_override=nuclei_profile_data(nuclei_login=False))

    rig.nuclei().execute(REQUEST)

    assert rig.engine.specs[0].timeout_seconds == 60 * 60 + NUCLEI_RUNNER_GRACE_SECONDS


def test_prazo_do_perfil_para_pelo_portao_e_devolve_o_parcial_antes_do_contêiner(
    tmp_path: Path,
) -> None:
    # Defeito achado na prova de laboratório: o prazo do contêiner era igual ao do portão, então
    # o runner estourava junto, o erro vencia e o resultado parcial se perdia (saída 5, sem
    # `nuclei.json`). O falso abaixo modela o runner real: mata o contêiner no próprio prazo.
    rig = _rig(tmp_path, profile_data_override=nuclei_profile_data(nuclei_login=False))
    rig.engine.lines = (result_line(),)
    profile_seconds = 60 * 60

    def at_profile_deadline() -> None:
        rig.clock.advance(profile_seconds)
        if profile_seconds >= rig.engine.specs[-1].timeout_seconds:
            rig.engine.error = ExternalToolError("O contêiner nuclei passou do prazo.")

    rig.engine.during_run = at_profile_deadline

    result = rig.nuclei().execute(REQUEST)

    assert result.status == "stopped_deadline"
    assert len(result.findings) == 1
    assert rig.artifacts.results[RUN_ID].status == "stopped_deadline"


def test_sem_login_nao_grava_arquivo_de_segredos_nem_faz_login(tmp_path: Path) -> None:
    rig = _rig(tmp_path, profile_data_override=nuclei_profile_data(nuclei_login=False))

    result = rig.nuclei().execute(REQUEST)

    assert rig.writer.written == []
    assert rig.target.requests == []
    assert result.logged_in is False
    assert result.account is None


def test_com_login_o_token_vai_so_no_arquivo_de_segredos(tmp_path: Path) -> None:
    rig = _rig(tmp_path, lines=(result_line(),))

    with structlog.testing.capture_logs() as logs:
        result = rig.nuclei().execute(REQUEST)

    spec = rig.engine.specs[0]
    assert rig.engine.secret_text_during_run == f"Bearer {TOKEN}"
    assert spec.args[spec.args.index("-sf") + 1] == SECRETS_MOUNT
    assert TOKEN not in " ".join(spec.args)
    assert TOKEN not in str(spec)
    assert TOKEN not in repr(rig.writer.secrets[0])
    assert TOKEN not in repr(logs)
    assert TOKEN not in rig.artifacts.serialized[RUN_ID]
    assert TOKEN not in rig.store.serialized()
    assert result.logged_in is True
    assert result.account == "user_a"


def test_cabecalho_do_login_vale_so_para_a_origem_aprovada(tmp_path: Path) -> None:
    rig = _rig(tmp_path)

    rig.nuclei().execute(REQUEST)

    secret = rig.writer.secrets[0]
    assert secret.header == "Authorization"
    assert secret.domains == ("api.hml.acme-teste.net.br", "api.hml.acme-teste.net.br:443")


def test_login_consome_o_orcamento_de_logins(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    budget = _CountingBudget(rig)

    nuclei = Nuclei(**{**_wiring(rig), "login_budget": budget})
    nuclei.execute(REQUEST)

    assert budget.acquired == 1


def test_login_reusa_o_token_do_cache_sem_novo_pedido(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    cache = TokenCache()
    cache.put("user_a", "tok-do-cache")

    Nuclei(**{**_wiring(rig), "token_cache": cache}).execute(REQUEST)

    assert rig.engine.secret_text_during_run == "Bearer tok-do-cache"  # noqa: S105
    assert [r for r in rig.target.requests if r.method == "POST"] == []


def test_arquivo_de_segredos_some_no_sucesso(tmp_path: Path) -> None:
    rig = _rig(tmp_path)

    rig.nuclei().execute(REQUEST)

    assert rig.writer.written
    assert rig.engine.secret_text_during_run is not None
    assert all(not path.exists() for path in rig.writer.written)
    assert rig.writer.removed == rig.writer.written


def test_arquivo_de_segredos_some_quando_o_nuclei_falha(tmp_path: Path) -> None:
    rig = _rig(tmp_path, lines=(result_line(),))
    rig.engine.exit_code = 2

    with pytest.raises(ExternalToolError, match="código 2"):
        rig.nuclei().execute(REQUEST)

    assert rig.writer.removed == rig.writer.written
    assert all(not path.exists() for path in rig.writer.written)
    assert RUN_ID not in rig.artifacts.results
    assert rig.engine.discarded


def test_arquivo_de_segredos_some_e_o_conteiner_morre_quando_o_prazo_estoura(
    tmp_path: Path,
) -> None:
    rig = _rig(tmp_path)
    rig.engine.error = ExternalToolError("O contêiner nuclei passou do prazo e foi encerrado.")

    with pytest.raises(ExternalToolError, match="passou do prazo"):
        rig.nuclei().execute(REQUEST)

    assert all(not path.exists() for path in rig.writer.written)
    assert rig.writer.removed == rig.writer.written
    assert rig.engine.killed_containers == [rig.engine.specs[0].container_name]
    assert RUN_ID not in rig.artifacts.results


def test_arquivo_de_segredos_some_quando_o_kill_derruba_o_conteiner(tmp_path: Path) -> None:
    rig = _rig(tmp_path, lines=(result_line(),))
    rig.engine.during_run = lambda: setattr(rig.kill, "on", True)

    result = rig.nuclei().execute(REQUEST)

    assert result.status == "stopped_kill"
    assert rig.engine.stop_answers == [True]
    assert rig.engine.killed_containers == [rig.engine.specs[0].container_name]
    assert all(not path.exists() for path in rig.writer.written)
    assert rig.writer.removed == rig.writer.written
    assert rig.artifacts.results[RUN_ID].status == "stopped_kill"
    assert len(result.findings) == 1


def test_arquivo_de_segredos_some_quando_a_gravacao_do_resultado_falha(tmp_path: Path) -> None:
    rig = _rig(tmp_path)

    def boom(run_id: str, result: NucleiResult) -> None:
        raise ConfigError("disco cheio")

    rig.artifacts.write_nuclei = boom  # type: ignore[method-assign]

    with pytest.raises(ConfigError, match="disco cheio"):
        rig.nuclei().execute(REQUEST)

    assert all(not path.exists() for path in rig.writer.written)


def test_arquivo_de_segredos_some_quando_o_login_e_recusado(tmp_path: Path) -> None:
    rig = _rig(tmp_path, handler=lambda request, jar: reply(401, {"detail": "recusado"}))

    with pytest.raises(PreflightError):
        rig.nuclei().execute(REQUEST)

    assert rig.writer.written == []
    assert rig.engine.specs == []


def test_kill_antes_de_comecar_recusa_sem_login_nem_contêiner(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    rig.kill.on = True

    with pytest.raises(KillSwitchEngaged):
        rig.nuclei().execute(REQUEST)

    assert rig.writer.written == []
    assert rig.engine.specs == []
    assert rig.target.requests == []


def test_saida_bruta_e_sempre_descartada(tmp_path: Path) -> None:
    rig = _rig(tmp_path, lines=(result_line(),))

    rig.nuclei().execute(REQUEST)

    assert len(rig.engine.discarded) == 1
    assert not rig.engine.discarded[0].exists()


def test_nuclei_json_nao_tem_conteudo_bruto_nem_valor_extraido(tmp_path: Path) -> None:
    line = result_line()
    rig = _rig(tmp_path, lines=(line,))

    result = rig.nuclei().execute(REQUEST)

    text = rig.artifacts.serialized[RUN_ID]
    for forbidden in FORBIDDEN_IN_OUTPUT:
        assert forbidden not in text
    finding = result.findings[0]
    assert finding.record.extracted_count == 1
    assert finding.record.extracted_bytes == len("EXTRAIDO-SEGREDO")
    assert finding.proposed_severity == "medium"
    assert finding.record.template_id == "springboot-env"


def test_linha_malformada_e_contada_e_nao_derruba(tmp_path: Path) -> None:
    rig = _rig(tmp_path, lines=("{nao e json", result_line(), '{"template-id": 7}', ""))

    result = rig.nuclei().execute(REQUEST)

    assert result.malformed_lines == 2
    assert len(result.findings) == 1
    assert "nao e json" not in rig.artifacts.serialized[RUN_ID]


def test_achados_repetidos_sao_agrupados_e_tecnologia_nao_vira_achado(tmp_path: Path) -> None:
    tech = result_line("nginx-detect", severity="info", type="technology")
    rig = _rig(tmp_path, lines=(result_line(), result_line(), tech))

    result = rig.nuclei().execute(REQUEST)

    assert len(result.findings) == 1
    assert result.findings[0].occurrences == 2
    assert [t.record.template_id for t in result.technologies] == ["nginx-detect"]


def test_resultado_conta_modelos_e_exclusoes_e_leva_as_versoes(tmp_path: Path) -> None:
    rig = _rig(tmp_path, profile_data_override=nuclei_profile_data(nuclei_login=False))

    result = rig.nuclei().execute(REQUEST)

    assert result.templates_selected == 1
    assert dict(result.excluded)["writes_not_allowed"] == 1
    assert result.status == "completed"
    assert result.stop_message is None
    assert result.exit_code == 0
    assert result.nuclei_version
    assert result.templates_version


def test_recusa_quando_nenhum_modelo_passa_pelas_permissoes(tmp_path: Path) -> None:
    rig = _rig(tmp_path)
    rig.manifest = rig.manifest.model_copy(
        update={"entries": tuple(e for e in rig.manifest.entries if e.path != READ_TEMPLATE)}
    )

    with pytest.raises(ConfigError, match="Nenhum modelo"):
        rig.nuclei().execute(REQUEST)

    assert rig.engine.specs == []


def test_reteste_limita_a_lista_aos_modelos_pedidos(tmp_path: Path) -> None:
    rig = _rig(tmp_path, profile_data_override=_writes_profile())

    result = rig.nuclei().execute(
        NucleiRequest(product="agenda", run_id=RUN_ID, only_templates=(WRITE_TEMPLATE,))
    )

    assert _templates(rig) == (WRITE_TEMPLATE,)
    assert result.templates_selected == 1


def test_reteste_nunca_traz_modelo_que_as_permissoes_nao_deixam(tmp_path: Path) -> None:
    rig = _rig(tmp_path, profile_data_override=nuclei_profile_data(nuclei_login=False))

    result = rig.nuclei().execute(
        NucleiRequest(
            product="agenda", run_id=RUN_ID, only_templates=(READ_TEMPLATE, WRITE_TEMPLATE)
        )
    )

    assert _templates(rig) == (READ_TEMPLATE,)
    assert result.templates_selected == 1


def test_reteste_sem_modelo_possivel_recusa_sem_rodar(tmp_path: Path) -> None:
    rig = _rig(tmp_path)

    with pytest.raises(ConfigError, match="Nenhum modelo"):
        rig.nuclei().execute(
            NucleiRequest(product="agenda", run_id=RUN_ID, only_templates=(UNSAFE_TEMPLATE,))
        )

    assert rig.engine.specs == []


class _CountingBudget(LoginBudget):
    def __init__(self, rig: NucleiRig) -> None:
        super().__init__(None, rig.clock, rig.clock)
        self.acquired = 0

    def acquire(self) -> None:
        self.acquired += 1


def _wiring(rig: NucleiRig) -> dict[str, Any]:
    return {
        "profiles": rig.profiles,
        "load_manifest": lambda: rig.manifest,
        "images": rig.images,
        "fence": rig.fence,
        "engine": rig.engine,
        "secrets_writer": rig.writer,
        "reader": NucleiJsonlReader(),
        "artifacts": rig.artifacts,
        "secrets": rig.secrets,
        "vault": rig.vault,
        "client": rig.target,
        "store": rig.store,
        "clock": rig.clock,
        "sleeper": rig.clock,
        "kill_switch": rig.kill,
    }
