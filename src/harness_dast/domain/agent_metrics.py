"""Medição do agente (`agent-metrics.json`) como o painel a lê: modelo mínimo e tolerante.

A CLI não mede tokens; quem grava esse arquivo é a avaliação cega (`evals/runner`), que o põe na
pasta da execução. O domínio não importa de `evals/`, então este é um espelho só do que o painel
usa: o modelo e os tokens do teste todo e de cada etapa do agente. É tolerante: campo
desconhecido é ignorado e campo ausente é `None`, nunca zero. O que NÃO é tolerado (número
negativo ou de tipo errado) o adaptador trata como "arquivo não usável", e o painel mostra
"não medido". Módulo puro.
"""

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

AGENT_METRICS_SCHEMA_VERSION: Final = 1
MAX_MODEL_NAME: Final = 80


class _Loose(BaseModel):
    """Entrada externa: congelada, e campo desconhecido é ignorado."""

    model_config = ConfigDict(frozen=True, extra="ignore")


class AgentTokens(_Loose):
    """Tokens somados de um trecho do trabalho do agente.

    Attributes:
        input: Entrada (sem cache).
        output: Saída.
        cache_creation: Entrada gravada no cache.
        cache_read: Entrada relida do cache (o contexto repetido a cada passo).
    """

    input: int = Field(default=0, ge=0)
    output: int = Field(default=0, ge=0)
    cache_creation: int = Field(default=0, ge=0)
    cache_read: int = Field(default=0, ge=0)

    @property
    def counted(self) -> int:
        """O que o painel soma como "tokens": entrada, saída e cache gravado.

        O cache relido fica de fora: é o mesmo contexto lido de novo a cada passo, e somá-lo
        faria o número crescer com a quantidade de passos, não com o trabalho.
        """
        return self.input + self.output + self.cache_creation


class AgentStageMetrics(_Loose):
    """Uma etapa do agente (`leitura`, `cadastro`, `alcance`, `varredura`, `triagem`, `outro`).

    Attributes:
        tokens: Tokens da etapa, ou `None` se o arquivo não os trouxe.
    """

    tokens: AgentTokens | None = None


class AgentTotals(_Loose):
    """Totais da rodada do agente.

    Attributes:
        tokens: Tokens do teste todo, ou `None` se o arquivo não os trouxe.
    """

    tokens: AgentTokens | None = None


class AgentMetrics(_Loose):
    """Conteúdo de `agent-metrics.json` (só o que o painel usa).

    Attributes:
        schema_version: Versão do formato (só a 1 é lida).
        model: Modelo de linguagem do agente, ou `None`.
        totals: Totais, ou `None`.
        stages: Etapas do agente por nome; vazio se o arquivo não as trouxe.
    """

    schema_version: int
    model: str | None = Field(default=None, max_length=MAX_MODEL_NAME)
    totals: AgentTotals | None = None
    stages: dict[str, AgentStageMetrics] = Field(default_factory=dict)
