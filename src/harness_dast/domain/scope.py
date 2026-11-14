"""Escopo autorizado e o `ScopeGuard`, que o impõe falhando fechado.

O que garante: uma requisição de saída só passa se, depois de normalizada (ver `urlnorm`),
casar com ao menos uma regra de `allow` (host, esquema, porta, caminho e método) E não casar
com nenhum `deny_paths`. Tudo que não é explicitamente permitido é recusado.
O que não faz: não resolve DNS, não envia nada e não decide janela ou autorização (ver
`window`). Este módulo é puro.

Construir uma regra ou um escopo inválido levanta `pydantic.ValidationError`; a conversão
para `ConfigError` acontece em `ProductProfile.from_data`.
"""

from dataclasses import dataclass
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.host import ParsedHost, parse_host
from harness_dast.domain.pathpattern import format_pattern, matches, parse_pattern
from harness_dast.domain.scope_reason import ScopeReason
from harness_dast.domain.urlnorm import (
    KNOWN_METHODS,
    NormalizedRequest,
    default_port,
    normalize_request,
    resolve_location,
)

_MAX_RULES = 100
_MAX_PATTERNS = 200
_HOST_FORBIDDEN_CHARS = frozenset("*/@?#\\% ")
_SCOPE_HINT = "Verifique scope.allow em target.yml. Flags não ampliam o escopo."


class ScopeRule(BaseModel):
    """Uma regra de permissão: onde (host/esquema/porta), o quê (caminhos) e como (métodos).

    Attributes:
        host: Nome DNS exato, sem curinga, esquema, usuário, porta ou caminho. Guardado em
            forma canônica (minúsculas, punycode). IPv6 entre colchetes.
        paths: Padrões de caminho (ver `pathpattern`), ao menos um.
        methods: Métodos HTTP em maiúsculas, ao menos um.
        scheme: `https` por padrão; `http` precisa ser escrito de propósito.
        port: Porta exigida; `None` significa "a porta padrão do esquema" (443/80). Porta
            diferente da padrão só passa se estiver escrita aqui.
        allow_local: Opt-in explícito para o laboratório local. O laboratório roda em
            `localhost`, IP privado ou nome de contêiner Docker (rótulo único), que de
            outra forma são recusados por serem o caminho clássico de SSRF contra a rede
            interna. Padrão `false`. Só vale para hosts locais (e é erro marcá-lo num host
            público); IP literal exige `allow_local` e precisa ser loopback ou privado;
            link-local e metadados da nuvem são recusados sempre.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str
    paths: tuple[str, ...] = Field(min_length=1, max_length=_MAX_PATTERNS)
    methods: tuple[str, ...] = Field(min_length=1, max_length=len(KNOWN_METHODS))
    scheme: Literal["http", "https"] = "https"
    port: StrictInt | None = Field(default=None, ge=1, le=65535)
    allow_local: StrictBool = False

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        """Recusa host com curinga ou partes de URL e o converte para a forma canônica."""
        if not value.strip():
            raise ValueError("host vazio")
        if "*" in value:
            raise ValueError("host com curinga não é permitido; liste cada host explicitamente")
        is_ipv6 = value.startswith("[") and value.endswith("]")
        has_port_or_scheme = ":" in value and not is_ipv6
        if has_port_or_scheme or any(c in _HOST_FORBIDDEN_CHARS for c in value):
            raise ValueError("host deve conter só o nome (sem esquema, usuário, porta ou caminho)")
        try:
            return parse_host(value).text
        except ScopeViolation as error:
            raise ValueError(error.message) from None

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Valida cada padrão e o guarda em forma canônica, sem repetições."""
        return _canonical_patterns(value)

    @field_validator("methods")
    @classmethod
    def validate_methods(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Aceita só métodos conhecidos, em maiúsculas; guarda ordenados e sem repetição."""
        unknown = sorted(set(value) - KNOWN_METHODS)
        if unknown:
            raise ValueError(
                "método HTTP desconhecido ou fora de maiúsculas; use um de "
                + ", ".join(sorted(KNOWN_METHODS))
            )
        return tuple(sorted(set(value)))

    @model_validator(mode="after")
    def validate_local_policy(self) -> Self:
        """Aplica a política de hosts locais e de IP literal descrita na classe."""
        host = parse_host(self.host)
        if host.ip is not None and not host.is_lab_address:
            raise ValueError("IP público literal não é aceito; use o nome DNS do host")
        if host.is_local and not self.allow_local:
            raise ValueError(
                "este host conta como local e exige allow_local: true nesta regra. Contam como "
                "local: IP literal, localhost, nome sem ponto (como vampi ou clinica-piloto, "
                "nomes de contêiner do laboratório), .local e .internal. No laboratório, "
                "acrescente allow_local: true; em ambiente real de teste, use o nome DNS "
                "completo, com ponto"
            )
        if self.allow_local and not host.is_local:
            raise ValueError("allow_local só se aplica a host local; remova-o deste host")
        return self


class Scope(BaseModel):
    """Conjunto de regras de permissão mais as negações globais.

    Attributes:
        allow: Regras de permissão, ao menos uma.
        deny_paths: Padrões de caminho negados em QUALQUER host; a negação vence a
            permissão e ignora diferença de maiúsculas/minúsculas.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    allow: tuple[ScopeRule, ...] = Field(min_length=1, max_length=_MAX_RULES)
    deny_paths: tuple[str, ...] = Field(default=(), max_length=_MAX_PATTERNS)

    @field_validator("deny_paths")
    @classmethod
    def validate_deny_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Valida cada padrão de negação e o guarda em forma canônica."""
        return _canonical_patterns(value)


def _canonical_patterns(values: tuple[str, ...]) -> tuple[str, ...]:
    canonical = tuple(dict.fromkeys(format_pattern(parse_pattern(v)) for v in values))
    return canonical


class OutboundRequest(BaseModel):
    """Descrição de uma requisição que o harness pretende enviar ao alvo.

    Attributes:
        method: Método HTTP em maiúsculas.
        url: URL absoluta. Não é validada aqui; quem valida é o `ScopeGuard`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    method: str
    url: str


PathMode = Literal["strict", "wide"]
"""Modo de leitura do caminho no proxy de escopo. `strict` (padrão) recusa todo caminho ambíguo;
`wide` libera mais formas e, em troca, nega se QUALQUER leitura do caminho casar com
`deny_paths` (ver ADR 0026 e `wide_guard`). Só o proxy de escopo lê este valor."""

ScopeVerdict = Literal["allowed", "denied_path", "outside_scope"]
"""Resultado de `ScopeGuard.evaluate`: permitida, negada por `deny_paths` ou fora do escopo."""


class ScopeDecision(BaseModel):
    """Decisão do guarda como dado, para quem precisa saber POR QUE uma requisição não passa.

    Attributes:
        verdict: `allowed`, `denied_path` (casou `deny_paths`) ou `outside_scope` (qualquer
            outra recusa: host, porta, caminho, método ou URL malformada).
        reason: Mensagem da recusa (sem caminho nem consulta); `None` quando permitida.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: ScopeVerdict
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class _CompiledRule:
    host: ParsedHost
    scheme: str
    port: int | None
    paths: tuple[tuple[str, ...], ...]
    methods: frozenset[str]

    def matches_origin(self, request: NormalizedRequest) -> bool:
        expected_port = default_port(self.scheme) if self.port is None else self.port
        return (
            request.host == self.host
            and request.scheme == self.scheme
            and request.port == expected_port
        )

    def matches_path(self, request: NormalizedRequest) -> bool:
        return any(
            matches(pattern, request.segments, wildcard_matches_empty=False)
            for pattern in self.paths
        )


class ScopeGuard:
    """Guarda de escopo: valida cada requisição de saída e falha fechado.

    Uso: chame `ensure_allowed` imediatamente antes de enviar qualquer requisição, e
    `ensure_redirect_allowed` para cada redirecionamento seguido (um redirecionamento é
    uma requisição nova e é conferido exatamente como uma).

    O guarda não mantém estado mutável: a mesma instância pode ser usada à vontade.
    """

    def __init__(self, scope: Scope) -> None:
        """Compila as regras do escopo.

        Args:
            scope: Escopo já validado.
        """
        self._rules = tuple(
            _CompiledRule(
                host=parse_host(rule.host),
                scheme=rule.scheme,
                port=rule.port,
                paths=tuple(parse_pattern(p) for p in rule.paths),
                methods=frozenset(rule.methods),
            )
            for rule in scope.allow
        )
        self._deny = tuple(parse_pattern(p) for p in scope.deny_paths)

    def ensure_allowed(self, request: OutboundRequest) -> None:
        """Garante que a requisição está dentro do escopo.

        Returns:
            Nada. O retorno normal significa "permitida".

        Raises:
            ScopeViolation: Se a URL for ambígua ou malformada, se o caminho casar com
                `deny_paths`, ou se nenhuma regra permitir host, esquema, porta, caminho
                e método ao mesmo tempo. A mensagem nunca repete caminho nem consulta (podem
                carregar tokens); só host, esquema, porta e método.
        """
        normalized = normalize_request(request.method, request.url)
        self._ensure_not_denied(normalized)
        self.ensure_covered(normalized)

    def evaluate(self, request: OutboundRequest) -> ScopeDecision:
        """Decide como `ensure_allowed`, mas devolve a decisão em vez de levantar.

        Serve ao planejamento (o agente precisa saber se uma operação nunca será enviada e
        por quê). Não substitui `ensure_allowed` antes de um envio: quem envia continua
        chamando `ensure_allowed` (via `approve`).
        """
        try:
            normalized = normalize_request(request.method, request.url)
        except ScopeViolation as error:
            return ScopeDecision(verdict="outside_scope", reason=error.message)
        try:
            self._ensure_not_denied(normalized)
        except ScopeViolation as error:
            return ScopeDecision(verdict="denied_path", reason=error.message)
        try:
            self.ensure_covered(normalized)
        except ScopeViolation as error:
            return ScopeDecision(verdict="outside_scope", reason=error.message)
        return ScopeDecision(verdict="allowed")

    def ensure_redirect_allowed(
        self, *, request: OutboundRequest, location: str, method: str
    ) -> None:
        """Confere o destino de um redirecionamento como se fosse uma requisição nova.

        Args:
            request: A requisição que recebeu o redirecionamento.
            location: Valor do cabeçalho `Location`.
            method: Método que o cliente usará no destino (um 303 troca POST por GET; passe
                o método que realmente será enviado).

        Raises:
            ScopeViolation: Como em `ensure_allowed`; também para `Location` relativo sem
                barra inicial.
        """
        target = resolve_location(base_url=request.url, location=location)
        self.ensure_allowed(OutboundRequest(method=method, url=target))

    def ensure_origin_allowed(self, url: str) -> None:
        """Garante que host, esquema e porta da URL são cobertos por alguma regra.

        Não olha caminho nem método. Serve para validar a `base_url` do ambiente.

        Raises:
            ScopeViolation: Se nenhuma regra cobrir a origem.
        """
        self._ensure_origin(normalize_request("GET", url))

    def _ensure_not_denied(self, request: NormalizedRequest) -> None:
        # A negação é conferida primeiro e sem diferença de caixa/composição Unicode:
        # o servidor pode tratar '/API/Conta' como '/api/conta'.
        if any(matches(pattern, request.segments, fold=True) for pattern in self._deny):
            raise ScopeViolation(
                "O caminho da requisição está em scope.deny_paths.",
                hint="Caminhos negados nunca são enviados; remova o caso do plano.",
                reason=ScopeReason.DENY_PATH,
            )

    def _ensure_origin(self, request: NormalizedRequest) -> list[_CompiledRule]:
        origin_rules = [rule for rule in self._rules if rule.matches_origin(request)]
        if origin_rules:
            return origin_rules
        if any(rule.host == request.host for rule in self._rules):
            raise ScopeViolation(
                f"Esquema ou porta de {request.origin} não são os permitidos para este host.",
                hint="A porta deve ser a padrão do esquema, salvo se a regra declarar `port`.",
                reason=ScopeReason.ORIGIN_NOT_ALLOWED,
            )
        raise ScopeViolation(
            f"O host {request.host.text} não está em scope.allow.",
            hint=_SCOPE_HINT,
            reason=ScopeReason.HOST_NOT_ALLOWED,
        )

    def covers_path(self, request: NormalizedRequest) -> bool:
        """Diz se origem e caminho (não o método) estão cobertos por alguma regra de `allow`.

        Nunca levanta. Serve ao modo amplo do proxy para marcar leituras do caminho que
        saem de `allow`; a decisão de liberar continua sendo de `ensure_covered`.
        """
        origin_rules = [rule for rule in self._rules if rule.matches_origin(request)]
        return any(rule.matches_path(request) for rule in origin_rules)

    def ensure_covered(self, request: NormalizedRequest) -> None:
        """Garante que origem, caminho e método estão cobertos por uma regra de `allow`.

        Não confere `deny_paths`. Recebe a requisição já normalizada (estrita) ou montada pelo
        modo amplo com a leitura literal do caminho.

        Raises:
            ScopeViolation: Se nenhuma regra cobrir origem, caminho e método (com `reason`).
        """
        origin_rules = self._ensure_origin(request)
        path_rules = [rule for rule in origin_rules if rule.matches_path(request)]
        if not path_rules:
            raise ScopeViolation(
                f"O caminho da requisição não está coberto por scope.allow em {request.host.text}.",
                hint=_SCOPE_HINT,
                reason=ScopeReason.PATH_NOT_ALLOWED,
            )
        if not any(request.method in rule.methods for rule in path_rules):
            raise ScopeViolation(
                f"O método {request.method} não é permitido para este caminho em "
                f"{request.host.text}.",
                hint=_SCOPE_HINT,
                reason=ScopeReason.METHOD_NOT_ALLOWED,
            )
