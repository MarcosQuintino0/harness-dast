"""Leitor do script de limpeza: só lê, dentro da pasta do produto, com teto de bytes."""

from pathlib import Path

import pytest

from harness_dast.adapters.cleanup.script_reader import FileCleanupScripts
from harness_dast.adapters.cleanup.tokens import SecretsTokenSource
from harness_dast.domain.cleanup_gate import MAX_SCRIPT_BYTES
from harness_dast.domain.errors import ConfigError
from tests.fakes.cleanup_rig import cleanup_profile
from tests.fakes.profile_data import valid_profile


def reader(tmp_path: Path) -> FileCleanupScripts:
    return FileCleanupScripts(lambda product, relative: tmp_path / relative)


def test_reads_the_script_bytes_without_changing_them(tmp_path: Path) -> None:
    (tmp_path / "cleanup").mkdir()
    content = b"\xef\xbb\xbfDELETE FROM T WHERE X = :run_id;\r\n"
    (tmp_path / "cleanup" / "cleanup.sql").write_bytes(content)

    assert reader(tmp_path).read("demo", cleanup_profile()) == content


def test_reads_at_most_one_byte_more_than_the_cap_so_the_gate_can_refuse(tmp_path: Path) -> None:
    (tmp_path / "cleanup").mkdir()
    (tmp_path / "cleanup" / "cleanup.sql").write_bytes(b"x" * (MAX_SCRIPT_BYTES * 3))

    assert len(reader(tmp_path).read("demo", cleanup_profile())) == MAX_SCRIPT_BYTES + 1


def test_missing_script_says_a_person_must_write_it(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        reader(tmp_path).read("demo", cleanup_profile())

    assert "não o cria" in (caught.value.hint or "")


def test_profile_without_cleanup_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="bloco cleanup"):
        reader(tmp_path).read("demo", valid_profile())


def test_the_reader_never_creates_or_writes_files(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        reader(tmp_path).read("demo", cleanup_profile())

    assert list(tmp_path.iterdir()) == []


def test_tokens_are_prefixed_long_and_different_each_time() -> None:
    source = SecretsTokenSource()

    tokens = {source.new_token() for _ in range(50)}

    assert len(tokens) == 50
    assert all(token.startswith("hdc-") and len(token) >= 36 for token in tokens)
