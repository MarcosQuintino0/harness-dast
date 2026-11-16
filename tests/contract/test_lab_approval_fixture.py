"""O suporte do laboratório não simula revogação ao repetir aprovação idêntica."""

from pathlib import Path

from harness_dast.adapters.storage.approval_store import FileApprovalStore
from tests.integration.lab_support import VAMPI_OPENAPI, VAMPI_PROFILE, LabCli


def test_aprovacao_identica_preserva_arquivo_observado_pelo_proxy(tmp_path: Path) -> None:
    cli = LabCli(tmp_path, {})
    cli.install_product("vampi", VAMPI_PROFILE, (VAMPI_OPENAPI,))
    cli.approve_installed_products()
    path = FileApprovalStore(cli.state).location("vampi")
    before = path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns

    cli.approve_installed_products()

    assert (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns) == before
