"""Resultado limpo da etapa `nuclei`, o conteúdo de `nuclei.json` (ADR 0122).

O que garante: só carrega o que a projeção por lista branca deixou passar (`NucleiFinding` e
`TechnologyDetected`, que vêm de `NucleiResultRecord`), mais contagens e o estado do fim. Nenhum
campo guarda requisição, resposta, `curl-command`, valor extraído nem credencial.
O que não faz: não decide gravidade, escopo nem parada; isso é do domínio das regras e do caso
de uso.
"""

from typing import Literal

from pydantic import StrictBool, StrictInt

from harness_dast.domain.nuclei_findings import NucleiFinding, TechnologyDetected
from harness_dast.domain.secret_ref import ProfileModel

__all__ = ["NucleiResult", "NucleiStatus"]

NucleiStatus = Literal["completed", "stopped_kill", "stopped_window", "stopped_deadline"]


class NucleiResult(ProfileModel):
    """Conteúdo de `nuclei.json`.

    Attributes:
        run_id: Execução à qual o resultado pertence.
        product: Produto.
        status: `completed` ou o motivo da parada antecipada (a saída parcial é mantida).
        stop_message: Texto da parada, sem dado do alvo; `None` ao completar.
        started_at: Início (ISO 8601).
        finished_at: Fim (ISO 8601).
        nuclei_version: Versão do binário fixada na imagem.
        templates_version: Versão do catálogo de modelos fixada na imagem.
        logged_in: Se a execução usou o token de uma conta (só modelos de leitura rodam).
        account: Apelido da conta que fez login, ou `None` sem login.
        templates_selected: Quantos modelos o domínio escolheu.
        excluded: Pares (motivo, contagem) da escolha, em ordem alfabética do motivo.
        exit_code: Código de saída do contêiner, como veio.
        malformed_lines: Linhas do JSONL que não puderam ser projetadas (contadas, nunca lidas).
        findings: Achados agrupados por impressão digital.
        technologies: Tecnologias identificadas (não são achados).
    """

    run_id: str
    product: str
    status: NucleiStatus
    stop_message: str | None = None
    started_at: str
    finished_at: str
    nuclei_version: str
    templates_version: str
    logged_in: StrictBool  # noqa: F841, RUF100
    account: str | None = None
    templates_selected: StrictInt  # noqa: F841, RUF100
    excluded: tuple[tuple[str, int], ...]
    exit_code: StrictInt
    malformed_lines: StrictInt
    findings: tuple[NucleiFinding, ...]
    technologies: tuple[TechnologyDetected, ...]
