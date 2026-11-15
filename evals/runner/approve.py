"""`approve`: o coordenador da rodada faz o papel da PESSOA que aprova o escopo (ADR 0037).

Na avaliacao cega o agente escreve o `target.yml` a partir da carta do caso. Como o `hdast
profile approve` exige uma pessoa num terminal, a rodada para no primeiro comando que toca o
alvo (`SCOPE_NOT_APPROVED`) ate o coordenador conferir o perfil e rodar este subcomando. Ele:

1. confere o perfil do workspace contra a carta do caso (as mesmas verificacoes de fidelidade do
   criterio (e)); se algum bloco de protecao alargou a carta, RECUSA e nao aprova nada;
2. grava a aprovacao na pasta de estado da rodada (`<out>/state`), a mesma `HDAST_STATE_DIR` que
   o ambiente do agente usa. Nao existe atalho dentro do `hdast`: este e codigo de avaliacao, roda
   fora do agente, e o `prepare` nega ao agente chamar este executor.

Rodar de novo depois de o agente editar um bloco de protecao aprova a versao nova (a pessoa
tambem faria isso), com a mesma conferencia contra a carta.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from evals.runner.cases import CASES_DIR, EvalError, RoundDirs, load_round_case
from evals.runner.checks_profile import WIDENING_IDS, profile_checks
from harness_dast.adapters.storage.approval_store import FileApprovalStore
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.domain.errors import HarnessError
from harness_dast.domain.scope_approval import create_approval
from harness_dast.domain.scope_approval_summary import describe_protection


@dataclass(frozen=True)
class ApproveResult:
    """O que o `approve` devolve."""

    product: str
    approved_at: str
    file: Path


def _case_name(dirs: RoundDirs) -> str:
    mode_file = dirs.sealed / "mode.json"
    if not mode_file.is_file():
        raise EvalError(f"{mode_file} nao existe: use a pasta `--out` de um `prepare`.")
    return str(json.loads(mode_file.read_text(encoding="utf-8"))["case"])


def approve(
    out: Path, *, cases_dir: Path = CASES_DIR, case_file: Path | None = None
) -> ApproveResult:
    """Confere o perfil do workspace contra a carta e grava a aprovacao da rodada.

    Raises:
        EvalError: Rodada sem `sealed/mode.json`, perfil ausente ou invalido, ou perfil que
            alarga a carta (nada e gravado).
    """
    dirs = RoundDirs(out)
    case = load_round_case(dirs, _case_name(dirs), cases_dir, case_file=case_file)
    products = dirs.workspace / "products"
    target = products / case.product / "target.yml"
    if not target.is_file():
        raise EvalError(f"{target} nao existe: o agente ainda nao cadastrou o produto.")
    loaded = yaml.safe_load(target.read_text(encoding="utf-8-sig"))
    if not isinstance(loaded, dict):
        raise EvalError(f"{target} nao e um perfil (esperava um mapa de campos).")
    widened = [
        check.id
        for check in profile_checks(loaded, case)
        if check.passed is False and check.id in WIDENING_IDS
    ]
    if widened:
        raise EvalError(
            "O perfil alarga ou inventa algo que a carta nao da (" + ", ".join(widened) + "): "
            "nada foi aprovado. Registre no relatorio da rodada e nao prossiga."
        )
    try:
        profile = FileProfileRepository(products).load(case.product)
    except HarnessError as error:
        raise EvalError(f"O perfil nao valida: {error.message}") from error
    approval = create_approval(profile, SystemClock().now(), describe_protection(profile))
    store = FileApprovalStore(dirs.state)
    store.write(approval)
    return ApproveResult(case.product, approval.approved_at, store.location(case.product))
