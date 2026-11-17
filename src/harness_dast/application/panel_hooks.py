"""Ganchos reais do painel: diário de comandos e catálogo de explicação (ADR 0032 e 0033).

`CatalogPanelHooks` implementa `PanelHooks` (`application/panel.py`) sem regra própria: lê o
trecho do diário que pertence ao teste (`load_journal_for_run`) e entrega, via domínio, os
comandos convertidos e as explicações do catálogo. Só leitura: nunca grava o diário nem fala com
o alvo.
"""

from collections.abc import Mapping

from harness_dast.application.command_journal import load_journal_for_run
from harness_dast.application.ports import CommandJournalStore
from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.panel.catalog import build_explanations
from harness_dast.domain.panel.journal import build_journal
from harness_dast.domain.panel.model import PanelExplanation, PanelJournal
from harness_dast.domain.report_model import FindingsReport


class CatalogPanelHooks:
    """Ganchos do painel apoiados no diário de comandos e no catálogo de explicação."""

    def __init__(self, journal: CommandJournalStore) -> None:
        """Cria os ganchos.

        Args:
            journal: Diário de comandos por produto (pasta de estado da pessoa usuária).
        """
        self._journal = journal

    def commands(self, product: str, run_id: str) -> PanelJournal | None:
        """Comandos do teste e quantas linhas corrompidas foram puladas.

        Returns:
            O diário do teste (com zero comandos quando o diário do produto existe mas não tem
            comando desta execução), ou `None` quando não há diário nenhum (teste anterior à
            versão 1.2, que não o gravava, ou rodado em outro computador).

        Raises:
            ConfigError: O arquivo do diário existe, mas não pôde ser lido.
        """
        loaded = load_journal_for_run(self._journal, product, run_id)
        return build_journal(loaded.entries, loaded.skipped_lines, has_diary=loaded.has_diary)

    def explanations(
        self, report: FindingsReport | None, authz: AuthzResult | None
    ) -> Mapping[str, PanelExplanation]:
        """Explicação do catálogo por `finding_id` (achados do ZAP e do teste entre contas)."""
        return build_explanations(report, authz)
