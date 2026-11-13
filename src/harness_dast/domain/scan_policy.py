"""Política e limites da varredura ativa: o que o ZAP recebe ANTES da primeira varredura.

O ZAP parte de padrões agressivos (32 threads por host, sem duração máxima, sem atraso). Aqui
os limites do perfil viram opções explícitas do ZAP e a política de regras é fixada, com as
regras destrutivas ou pesadas por natureza desligadas. Este módulo é puro.

Os ids das regras vêm da documentação do ZAP (add-on `ascanrules` 84, ZAP 2.17) e precisam ser
conferidos contra o ZAP real (`ascan/view/scanners`): o adaptador recusa a política se uma
regra desligada continuar ligada depois de aplicada.
"""

import math
from typing import Final

from pydantic import BaseModel, ConfigDict

from harness_dast.domain.run import RunLimits
from harness_dast.domain.scan_config import Level, ScanConfig

POLICY_NAME: Final = "hdast-scan"
"""Nome da política no ZAP. Fixo: a política persiste na configuração do ZAP entre sessões
(spike, Q7), então é removida e recriada a cada varredura em vez de acumular."""

BASE_INJECTABLE_MASK: Final = 35
"""Padrão do ZAP para `TargetParamsInjectable` (consulta, corpo e JSON; medido no spike)."""

URL_PATH_INJECTABLE_BIT: Final = 16
"""Bit que liga a injeção em segmentos de caminho (spike: 35 + 16 = 51)."""

POLL_SECONDS: Final = 2.0
"""Intervalo entre consultas ao andamento de uma varredura."""


class DisabledRule(BaseModel):
    """Regra de varredura ativa desligada por padrão.

    Attributes:
        plugin_id: Identificador da regra no ZAP.
        name: Nome da regra.
        reason: Por que está desligada.
    """

    model_config = ConfigDict(frozen=True)

    plugin_id: int
    name: str
    reason: str


DEFAULT_DISABLED_RULES: Final[tuple[DisabledRule, ...]] = (
    DisabledRule(
        plugin_id=40044,
        name="Exponential Entity Expansion (Billion Laughs)",
        reason="Ataque de negação de serviço por desenho: pode derrubar o alvo de teste.",
    ),
    DisabledRule(
        plugin_id=30001,
        name="Buffer Overflow",
        reason="Envia cargas enormes para travar o processo; destrutiva e sem valor em API REST.",
    ),
    DisabledRule(
        plugin_id=30002,
        name="Format String Error",
        reason="Cargas de formatação que podem derrubar o processo; sem valor em API REST.",
    ),
    DisabledRule(
        plugin_id=10104,
        name="User Agent Fuzzer",
        reason="Repete cada requisição com dezenas de User-Agent: carga sem achado útil.",
    ),
    DisabledRule(
        plugin_id=40043,
        name="Log4Shell",
        reason="Depende de retorno externo (OAST), que o proxy de escopo nega; só gera carga.",
    ),
    DisabledRule(
        plugin_id=90034,
        name="Cloud Metadata Potentially Exposed",
        reason="Pede endereços de metadados de nuvem: fora do escopo por desenho (ADR 0008).",
    ),
    DisabledRule(
        plugin_id=40035,
        name="Hidden File Finder",
        reason="Adivinha centenas de caminhos novos no host; carga alta e fora do escopo.",
    ),
    DisabledRule(
        plugin_id=40032,
        name=".htaccess Information Leak",
        reason="Adivinhação de caminho fora das requisições aprendidas.",
    ),
    DisabledRule(
        plugin_id=40034,
        name=".env Information Leak",
        reason="Adivinhação de caminho fora das requisições aprendidas.",
    ),
)


class ScanPolicy(BaseModel):
    """Política aplicada à varredura.

    Attributes:
        name: Nome da política no ZAP.
        strength: Força de ataque.
        threshold: Limiar de alerta.
        url_path_injection: Se a injeção em segmentos de caminho está ligada.
        disabled_rules: Ids das regras desligadas (padrão do harness mais as do perfil).
    """

    model_config = ConfigDict(frozen=True)

    name: str
    strength: Level
    threshold: Level
    url_path_injection: bool
    disabled_rules: tuple[int, ...]

    @property
    def injectable_mask(self) -> int:
        """Valor de `TargetParamsInjectable` que o ZAP recebe."""
        extra = URL_PATH_INJECTABLE_BIT if self.url_path_injection else 0
        return BASE_INJECTABLE_MASK + extra


class ScanLimits(BaseModel):
    """Limites que o ZAP recebe, derivados do perfil.

    Attributes:
        threads_per_host: Threads por host.
        delay_ms: Atraso entre requisições, por host (aproxima `requests_per_second`).
        max_scan_minutes: Teto de cada varredura.
        max_rule_minutes: Teto de cada regra.
    """

    model_config = ConfigDict(frozen=True)

    threads_per_host: int
    delay_ms: int
    max_scan_minutes: int
    max_rule_minutes: int


def build_policy(config: ScanConfig) -> ScanPolicy:
    """Monta a política: a do perfil mais as regras desligadas (as do perfil só acrescentam)."""
    disabled = [rule.plugin_id for rule in DEFAULT_DISABLED_RULES]
    disabled.extend(config.disable_rules)
    return ScanPolicy(
        name=POLICY_NAME,
        strength=config.strength,
        threshold=config.threshold,
        url_path_injection=config.url_path_injection,
        disabled_rules=tuple(sorted(dict.fromkeys(disabled))),
    )


def delay_ms_for(requests_per_second: float) -> int:
    """Atraso por host que limita a taxa: `ceil(1000 / req/s)`; o atraso do ZAP é por host."""
    return max(1, math.ceil(1000.0 / requests_per_second))


def build_limits(limits: RunLimits, config: ScanConfig) -> ScanLimits:
    """Traduz os limites do perfil em opções do ZAP."""
    return ScanLimits(
        threads_per_host=limits.zap_threads_per_host,
        delay_ms=delay_ms_for(limits.requests_per_second),
        max_scan_minutes=min(config.max_scan_minutes, limits.max_duration_minutes),
        max_rule_minutes=min(
            config.max_rule_minutes, config.max_scan_minutes, limits.max_duration_minutes
        ),
    )


def scan_cap_minutes(limits: ScanLimits, remaining_seconds: float) -> int:
    """Teto da próxima varredura em minutos: o menor entre o do perfil e o prazo que resta.

    O ZAP só aceita minutos inteiros; o prazo exato é imposto pelo laço do `scan`, que para a
    varredura quando o prazo acaba. Nunca devolve menos de 1.
    """
    remaining = max(1, math.ceil(remaining_seconds / 60.0))
    return max(1, min(limits.max_scan_minutes, remaining))
