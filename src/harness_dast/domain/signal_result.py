"""Resultado dos sinais de erro interno vistos pela cerca (`error-signals.json`, ADR 0049).

Os achados daqui NÃO são alertas do ZAP: nascem de reconhecer um sinal fixo numa resposta que o
proxy de escopo liberou, e levam a técnica que os produziu. Severidade e confiança vêm do
catálogo (`error_signal_catalog`), nunca do agente. Nenhum valor da resposta entra nestes
modelos: só categoria, método, modelo de caminho, códigos HTTP e NOMES de parâmetro de consulta.
Este módulo é puro.
"""

from typing import Final, Literal

from pydantic import Field

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.error_signal_catalog import SignalCategory
from harness_dast.domain.zap_alert import Confidence, Severity

SIGNAL_SCHEMA_VERSION: Final = 1
SIGNAL_FINGERPRINT_VERSION: Final = 1
MAX_SIGNAL_FINDINGS: Final = 500
MAX_STATUSES: Final = 5
MAX_QUERY_PARAMS: Final = 10

DISABLED_MESSAGE: Final = "a cerca não registrou respostas desta execução"

SIGNAL_NOTICE: Final = (
    "Achados de sinal vêm de reconhecer texto conhecido (erro de banco, rastreamento de exceção, "
    "página de depuração) em respostas que o proxy de escopo liberou; não são alertas do ZAP e "
    "não confirmam vulnerabilidade. Severidade proposta pelo catálogo do código; todo achado "
    "exige triagem humana. O ZAP pode ter o mesmo achado como alerta próprio (por exemplo "
    "'Application Error Disclosure'): os dois pedem uma triagem só. Não entram em --compare. "
    "Contagem zero NÃO prova ausência de erros: veja as respostas não lidas."
)

SIGNAL_DESCRIPTION: Final = (
    "A resposta do servidor trazia um texto que costuma indicar erro interno exposto ao cliente "
    "(detalhe de banco de dados, pilha de chamadas ou página de depuração). Isso ajuda um "
    "atacante a conhecer a tecnologia e a estrutura do sistema. É heurística: pode ser falso "
    "positivo, por exemplo documentação que cita um erro."
)
SIGNAL_SOLUTION: Final = (
    "Devolver ao cliente uma mensagem de erro genérica, registrar o detalhe só no servidor e "
    "desligar o modo de depuração fora do desenvolvimento."
)


class SignalWindow(ApiModel):
    """Intervalo da trilha da cerca que o relatório considerou.

    Attributes:
        start: Início (ISO 8601): começo do `probe`.
        end: Fim (ISO 8601): fim do último estágio gravado.
    """

    start: str
    end: str


class SignalFinding(ApiModel):
    """Achado de sinal de erro interno, de origem própria (a cerca).

    Attributes:
        finding_id: Identificador curto (`S-` e 8 hexadecimais do fingerprint).
        fingerprint: SHA-256 estável entre execuções (produto, método, modelo de caminho,
            categoria).
        fingerprint_version: Versão do algoritmo do fingerprint.
        origin: Sempre `proxy`.
        technique: Sempre `proxy_error_signal`.
        category: Categoria do catálogo.
        title: Título curto.
        proposed_severity: Severidade proposta pelo catálogo.
        proposed_confidence: Confiança proposta pelo catálogo.
        cwe: CWE da categoria.
        owasp_api_2023: Categoria do OWASP API Top 10 2023 (proposta).
        operation_id: Operação do `probe`, ou `None` quando o caminho não casou.
        method: Método HTTP.
        path_template: Modelo de caminho (nunca a URL concreta).
        occurrences: Respostas liberadas com este sinal nesta operação.
        statuses: Até 5 códigos HTTP distintos.
        query_params: Até 10 nomes de parâmetro de consulta, da primeira ocorrência.
        description: O que o sinal significa.
        solution: O que fazer a respeito.
        status: Sempre `needs_triage`.
    """

    finding_id: str
    fingerprint: str
    fingerprint_version: int = SIGNAL_FINGERPRINT_VERSION
    origin: Literal["proxy"] = "proxy"
    technique: Literal["proxy_error_signal"] = "proxy_error_signal"
    category: SignalCategory
    title: str
    proposed_severity: Severity
    proposed_confidence: Confidence
    cwe: int
    owasp_api_2023: str = "API8:2023 Security Misconfiguration"
    operation_id: str | None = None
    method: str
    path_template: str
    occurrences: int
    statuses: tuple[int, ...] = ()
    query_params: tuple[str, ...] = ()
    description: str = SIGNAL_DESCRIPTION
    solution: str = SIGNAL_SOLUTION
    status: Literal["needs_triage"] = "needs_triage"


class ProxySignals(ApiModel):
    """Sinais vistos pela cerca numa execução (`error-signals.json` e `proxy_signals`).

    Attributes:
        schema_version: Versão do formato (1).
        enabled: Se havia leitura da cerca para esta execução.
        message: Explicação quando `enabled` é falso.
        window: Intervalo da trilha considerado.
        responses_examined: Respostas liberadas que a cerca leu.
        responses_skipped: Respostas liberadas não lidas, por motivo (`type`, `encoding`,
            `empty`, `error`).
        responses_with_signal: Respostas lidas com ao menos um sinal.
        counts: Respostas com cada categoria (todas as categorias, com zero).
        findings: Achados de sinal (um por operação e categoria).
        findings_omitted: Achados que passaram do teto de `MAX_SIGNAL_FINDINGS` (as contagens
            acima continuam completas).
        notice: Aviso fixo sobre o que estes achados são e não são.
    """

    schema_version: int = SIGNAL_SCHEMA_VERSION
    enabled: bool
    message: str | None = None
    window: SignalWindow | None = None
    responses_examined: int = 0
    responses_skipped: dict[str, int] = Field(default_factory=dict)
    responses_with_signal: int = 0
    counts: dict[str, int] = Field(default_factory=dict)
    findings: tuple[SignalFinding, ...] = ()
    findings_omitted: int = 0
    notice: str = SIGNAL_NOTICE

    @property
    def responses_total(self) -> int:
        """Respostas liberadas com status na janela (lidas mais não lidas)."""
        return self.responses_examined + sum(self.responses_skipped.values())


def disabled_signals(message: str = DISABLED_MESSAGE) -> ProxySignals:
    """Resultado de quando a cerca não deixou registro desta execução."""
    return ProxySignals(enabled=False, message=message)
