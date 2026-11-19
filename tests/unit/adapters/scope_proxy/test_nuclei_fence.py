"""`FileNucleiFence`: lê a política que o `stack up` gravou na pasta da segunda cerca (ADR 0122)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from harness_dast.adapters.scope_proxy.generate import (
    POLICY_FILE_NAME,
    build_deny_all_policy,
    build_nuclei_policy,
)
from harness_dast.adapters.scope_proxy.nuclei_fence import FileNucleiFence
from harness_dast.adapters.scope_proxy.policy import ApprovalBinding, ProxyPolicy
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.nuclei_scope import nuclei_scope_for
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.run import RunId
from tests.fakes.nuclei import RUN_ID
from tests.fakes.profile_data import valid_profile_data

NOT_AFTER = datetime(2999, 1, 1, tzinfo=UTC)


def _profile(**extra_checks: Any) -> ProductProfile:
    data = valid_profile_data("demo")
    data["extra_checks"] = {"nuclei": True, **extra_checks}
    return ProductProfile.from_data(data)


def _bound(policy: ProxyPolicy, profile: ProductProfile) -> ProxyPolicy:
    binding = ApprovalBinding(
        product=profile.product,
        approval_sha256="a" * 64,
        profile_sha256="b" * 64,
        authorization=profile.scope.authorization,
        windows=profile.scope.windows,
    )
    return policy.model_copy(update={"binding": binding})


def _write(directory: Path, policy: ProxyPolicy) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / POLICY_FILE_NAME).write_text(policy.model_dump_json(indent=2), encoding="utf-8")


def _nuclei_policy(profile: ProductProfile) -> ProxyPolicy:
    return build_nuclei_policy(profile, RunId(value=RUN_ID), NOT_AFTER, nuclei_scope_for(profile))


def test_devolve_a_politica_do_perfil_quando_ela_esta_publicada(tmp_path: Path) -> None:
    profile = _profile()
    _write(tmp_path, _bound(_nuclei_policy(profile), profile))

    published = FileNucleiFence(tmp_path).published_scope()

    assert published == nuclei_scope_for(profile)


def test_politica_de_outro_perfil_nao_e_igual_a_esperada(tmp_path: Path) -> None:
    published_profile = _profile()
    other = _profile(nuclei_wide_paths=True)
    _write(tmp_path, _bound(_nuclei_policy(published_profile), published_profile))

    published = FileNucleiFence(tmp_path).published_scope()

    assert published != nuclei_scope_for(other)


def test_sem_pasta_de_politica_no_estado_devolve_none() -> None:
    assert FileNucleiFence(None).published_scope() is None


def test_sem_arquivo_de_politica_devolve_none(tmp_path: Path) -> None:
    assert FileNucleiFence(tmp_path).published_scope() is None


def test_politica_que_nega_tudo_devolve_none(tmp_path: Path) -> None:
    profile = _profile()
    _write(tmp_path, build_deny_all_policy(profile, RunId(value=RUN_ID)))

    assert FileNucleiFence(tmp_path).published_scope() is None


def test_politica_sem_vinculo_nunca_e_igual_a_esperada(tmp_path: Path) -> None:
    profile = _profile()
    _write(tmp_path, _nuclei_policy(profile))

    published = FileNucleiFence(tmp_path).published_scope()

    assert published is not None
    assert published.windows == ()
    assert published != nuclei_scope_for(profile)


def test_arquivo_ilegivel_levanta_erro_de_configuracao(tmp_path: Path) -> None:
    (tmp_path / POLICY_FILE_NAME).write_text("{não é json", encoding="utf-8")

    with pytest.raises(ConfigError, match="não é JSON válido"):
        FileNucleiFence(tmp_path).published_scope()


def test_politica_com_campo_desconhecido_levanta_erro_de_configuracao(tmp_path: Path) -> None:
    (tmp_path / POLICY_FILE_NAME).write_text('{"extra": 1}', encoding="utf-8")

    with pytest.raises(ConfigError, match="inválida"):
        FileNucleiFence(tmp_path).published_scope()
