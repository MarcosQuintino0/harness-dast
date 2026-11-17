"""Portas consumidas pela capacidade probe; assinaturas e docstrings preservadas."""

from typing import Protocol

from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.knowledge_receipts import KnowledgeRuleUse
from harness_dast.domain.profile import ProductProfile


class KnowledgeRecipeReader(Protocol):
    """Seleciona receitas comprovadas aplicáveis aos documentos atuais."""

    def validate(
        self,
        product: str,
        profile: ProductProfile,
        spec: ApiSpec,
        rules: DataRules,
        flows: FlowSpec | None,
    ) -> tuple[KnowledgeRuleUse, ...]:
        """Devolve regras validadas sem alterar perfil, fluxos ou autorização."""
        ...
