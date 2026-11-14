"""Guarda de escopo do modo amplo, usado SÓ pelo proxy de escopo. Módulo puro.

Por que é uma classe à parte: o modo amplo libera formas de caminho que o modo estrito recusa.
Isso só é seguro onde a requisição que será decidida é a mesma que vai ao fio. No proxy é: ele
vê os bytes que o ZAP enviou. Na CLI não é: o cliente HTTP normaliza a URL (resolve `..`,
re-codifica), então o que o guarda aprovasse poderia não ser o que sai. Por isso o `ScopeGuard`
(usado por `probe`, `preflight`, `target_client`, redirecionamentos e plano) NUNCA lê o modo
amplo, e esta classe é importada apenas por `adapters/scope_proxy` (há teste que prova isso).

O que garante:
- host, porta, esquema, credenciais, método e tamanho da URL são conferidos exatamente como no
  modo estrito (`split_request`);
- para PERMITIR, só vale a leitura literal do caminho (decodificada uma vez, barras cruas) contra
  `scope.allow` e o método da regra;
- para NEGAR, qualquer leitura (ver `widepath`) que case com `scope.deny_paths` recusa;
- segmento literal `.` ou `..`, controle e UTF-8 inválido continuam recusados.

RISCO ACEITO (ADR 0026): uma leitura que cai fora de `scope.allow` sem casar com `deny_paths` NÃO
recusa. O servidor pode então rotear o pedido para outro caminho do MESMO host (por exemplo
`/api/v1/..;/interno` chegando em `/api/interno`). Host e porta nunca mudam. O guarda apenas
avisa (`WideOutcome.leaves_allow`) para a auditoria contar.
"""

from dataclasses import dataclass

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.pathpattern import matches, parse_pattern
from harness_dast.domain.scope import OutboundRequest, Scope, ScopeGuard
from harness_dast.domain.scope_reason import ScopeReason
from harness_dast.domain.urlnorm import NormalizedRequest, RequestParts, split_request
from harness_dast.domain.widepath import interpretations, literal_segments


@dataclass(frozen=True, slots=True)
class WideOutcome:
    """Resultado de uma requisição liberada no modo amplo.

    Attributes:
        leaves_allow: `True` se alguma leitura alternativa do caminho cai fora de
            `scope.allow` (o risco aceito do modo amplo); a requisição foi liberada mesmo assim.
    """

    leaves_allow: bool


class WideScopeGuard:
    """Guarda do modo amplo. Sem estado mutável; a mesma instância serve a tudo."""

    def __init__(self, scope: Scope) -> None:
        """Compila o escopo.

        Args:
            scope: Escopo já validado (o mesmo que o `ScopeGuard` estrito receberia).
        """
        self._guard = ScopeGuard(scope)
        self._deny = tuple(parse_pattern(p) for p in scope.deny_paths)

    def ensure_allowed(self, request: OutboundRequest) -> WideOutcome:
        """Garante que a requisição está dentro do escopo, no modo amplo.

        Returns:
            O resultado, com a marca de leitura fora de `allow`.

        Raises:
            ScopeViolation: Se a URL for malformada nos itens que o modo amplo mantém
                estritos, se QUALQUER leitura do caminho casar com `deny_paths`, ou se a leitura
                literal não for coberta por `scope.allow` com o método pedido. Sempre com `reason`.
        """
        parts = split_request(request.method, request.url)
        literal = literal_segments(parts.raw_path)
        readings = interpretations(parts.raw_path)
        self._ensure_not_denied(literal, readings)
        self._guard.ensure_covered(_as_request(parts, literal))
        return WideOutcome(leaves_allow=self._any_reading_leaves_allow(parts, literal, readings))

    def ensure_origin_allowed(self, url: str) -> None:
        """Mesma conferência de origem do guarda estrito (host, esquema e porta)."""
        self._guard.ensure_origin_allowed(url)

    def _ensure_not_denied(
        self, literal: tuple[str, ...], readings: tuple[tuple[str, ...], ...]
    ) -> None:
        for segments in (literal, *readings):
            if any(matches(pattern, segments, fold=True) for pattern in self._deny):
                raise ScopeViolation(
                    "O caminho da requisição está em scope.deny_paths.",
                    hint="Caminhos negados nunca são enviados; remova o caso do plano.",
                    reason=ScopeReason.DENY_PATH,
                )

    def _any_reading_leaves_allow(
        self,
        parts: RequestParts,
        literal: tuple[str, ...],
        readings: tuple[tuple[str, ...], ...],
    ) -> bool:
        # A primeira leitura é o caminho cru; a literal já foi conferida.
        return any(
            not self._guard.covers_path(_as_request(parts, reading))
            for reading in readings[1:]
            if reading != literal
        )


def _as_request(parts: RequestParts, segments: tuple[str, ...]) -> NormalizedRequest:
    return NormalizedRequest(
        method=parts.method,
        scheme=parts.scheme,
        host=parts.host,
        port=parts.port,
        segments=segments,
    )
