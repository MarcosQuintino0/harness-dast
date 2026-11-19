"""Caso de uso `retestar`: repete a varredura só nas operações de achados já relatados.

Não cria caminho novo de tráfego. Monta um `RunRequest` com `only` (as operações dos achados
escolhidos) e `compare` (a execução anterior) e entrega ao MESMO `RunPipeline` do `run`, que
aplica aprovação do escopo, pilha atual, janela, prazo, limite por segundo, trava da pilha e
mutação pendente. Os estágios `authz` e `negative` ficam desligados (redução): o reteste
classifica só os achados do varredor, que são os que `findings.json` lista em `findings`.

Nuclei (ADR 0122): se o `nuclei.json` da execução anterior tem achados abertos (`U-...`), o
estágio `nuclei` roda de novo só com os modelos dos achados escolhidos
(`RunRequest.nuclei_templates`); sem achados do Nuclei ele fica desligado. `--finding` aceita a
impressão digital de um achado do Nuclei. Sem nenhum achado elegível do ZAP, mas com achados
abertos do Nuclei, o reteste roda SÓ o Nuclei (`RunRequest.nuclei_only`): não há `probe`, `scan`
nem `findings.json`, e a pasta é a do `preflight`. O `retest.json` traz uma entrada por achado do
Nuclei (`origin: nuclei`), classificada pela impressão digital.

Honestidade: o resultado nunca diz "corrigido". `not_reproduced` significa que a operação foi
testada nesta execução e o fingerprint não apareceu; o aviso `COMPARISON_NOTICE` acompanha.
Código de saída: o do `run` se ele falhou; senão `1` se algum achado reproduzido tem severidade
no limiar de falha do perfil; senão `0`.
"""

from dataclasses import dataclass

from harness_dast.application.common_ports import Clock, ProfileRepository
from harness_dast.application.retest_ports import RetestArtifacts, RunStage
from harness_dast.application.run import RunRequest, RunResult
from harness_dast.domain.errors import ExitCode, HarnessError
from harness_dast.domain.finding import Finding
from harness_dast.domain.finding_diff import ensure_comparable
from harness_dast.domain.nuclei_findings import NucleiFinding
from harness_dast.domain.nuclei_result import NucleiResult
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.retest import (
    DEFAULT_MAX_FINDINGS,
    RetestEntry,
    RetestReport,
    build_retest_report,
    operations_of,
    reproduced_at_threshold,
)
from harness_dast.domain.retest_nuclei import nuclei_retest_entries, select_retest_targets
from harness_dast.domain.run_ref import require_run_id
from harness_dast.domain.scan_config import FailOn, effective_fail_on


@dataclass(frozen=True)
class RetestRequest:
    """Pedido de reteste.

    Attributes:
        product: Produto.
        previous_run_id: Execução anterior, de onde vêm os achados.
        findings: Fingerprints escolhidos; vazio escolhe os de severidade alta e média.
        max_findings: Teto de achados (1 a 30).
        fail_on: Limiar de falha; só endurece o do perfil.
        max_minutes: Reduz o prazo da execução; nunca amplia o do perfil.
    """

    product: str
    previous_run_id: str
    findings: tuple[str, ...] = ()
    max_findings: int = DEFAULT_MAX_FINDINGS
    fail_on: FailOn | None = None
    max_minutes: int | None = None


@dataclass(frozen=True)
class RetestOutcome:
    """Resultado do reteste.

    Attributes:
        run: O que o `run` devolveu (`run.json` e o erro que o parou, se houve).
        report: O `retest.json`, ou `None` se o `run` parou antes de gerar `findings.json`.
        exit_code: Código de saída do processo.
        error: Erro que encerrou o `run`, ou `None`.
    """

    run: RunResult
    report: RetestReport | None
    exit_code: int
    error: HarnessError | None


class RetestUseCase:
    """Orquestra o reteste (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        artifacts: RetestArtifacts,
        run: RunStage,
        clock: Clock,
    ) -> None:
        """Cria o caso de uso.

        Args:
            profiles: Repositório de perfis (limiar de falha).
            artifacts: Leitura de `findings.json` e escrita de `retest.json`.
            run: Pipeline do `run`, com todos os controles.
            clock: Relógio injetado.
        """
        self._profiles = profiles
        self._artifacts = artifacts
        self._run = run
        self._clock = clock

    def execute(self, request: RetestRequest) -> RetestOutcome:
        """Seleciona os achados, roda o pipeline reduzido e classifica cada um.

        Raises:
            ConfigError: Execução anterior inexistente, de outro produto ou de outra versão
                de fingerprint; achado inexistente; nenhum achado a retestar; `--max` fora do
                intervalo. Nada é enviado ao alvo nesses casos.
        """
        # O perfil entra primeiro: sem aprovação vigente do escopo (ou com a pilha desatualizada)
        # nada mais acontece, nem a leitura dos achados.
        threshold = effective_fail_on(
            self._profiles.load(request.product).scan.fail_on, request.fail_on
        )
        previous_id = require_run_id(request.previous_run_id)
        baseline = self._artifacts.read_findings(previous_id)
        ensure_comparable(baseline, request.product)
        previous_nuclei = self._artifacts.read_nuclei(previous_id)
        selected, opened = select_retest_targets(
            baseline.findings,
            previous_nuclei.findings if previous_nuclei else (),
            request.findings,
            request.max_findings,
        )
        templates = _templates_of(opened)
        result = self._run.execute(
            RunRequest(
                product=request.product,
                nuclei=bool(templates),
                nuclei_templates=templates,
                nuclei_only=not selected,
                authz=False,
                negative=False,
                fail_on=request.fail_on,
                compare=previous_id,
                max_minutes=request.max_minutes,
                only=operations_of(selected) if selected else (),
            )
        )
        summary = result.summary
        needed = "findings.json" if selected else "nuclei.json"
        if needed not in summary.artifacts:
            return RetestOutcome(result, None, summary.exit_code, result.error)
        current = self._artifacts.read_findings(summary.run_id) if selected else None
        report = build_retest_report(
            product=request.product,
            previous_run_id=previous_id,
            run_id=summary.run_id,
            generated_at=self._clock.now().isoformat(),
            selected=selected,
            current=current.findings if current else (),
            scanned_operations=_scanned(selected, current) if current else frozenset(),
            nuclei_entries=self._nuclei_entries(opened, summary.run_id),
        )
        self._artifacts.write_retest(summary.run_id, report)
        return RetestOutcome(result, report, _exit_code(result, report, threshold), result.error)

    def _nuclei_entries(
        self, opened: tuple[NucleiFinding, ...], run_id: str
    ) -> tuple[RetestEntry, ...]:
        """Entradas do `retest.json` para os achados do Nuclei escolhidos."""
        if not opened:
            return ()
        current: NucleiResult | None = self._artifacts.read_nuclei(run_id)
        return nuclei_retest_entries(opened, current)


def _templates_of(opened: tuple[NucleiFinding, ...]) -> tuple[str, ...]:
    """Caminhos dos modelos dos achados do Nuclei escolhidos, sem repetição e em ordem."""
    return tuple(sorted({item.record.template_path for item in opened}))


def _scanned(selected: tuple[Finding, ...], current: FindingsReport) -> frozenset[str]:
    """Operações dos achados escolhidos que a execução nova varreu.

    A comparação do `report` já sabe, para cada achado ausente, se a operação foi varrida
    (`operation_scanned_now`); aqui só se traduz isso em operações, sem repetir a regra.
    """
    seen = {item.fingerprint for item in current.not_observed if item.operation_scanned_now}
    return frozenset(
        item.operation_id for item in selected if item.fingerprint in seen and item.operation_id
    )


def _exit_code(result: RunResult, report: RetestReport, threshold: FailOn) -> int:
    if result.error is not None:
        return result.summary.exit_code
    return (
        int(ExitCode.FINDINGS) if reproduced_at_threshold(report, threshold) else int(ExitCode.OK)
    )
