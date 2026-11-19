"""Conferência da carta estruturada e geração dos blocos do `target.yml` (ADR 0036).

`review_letter` é determinística e sem relógio (o dia de hoje entra por parâmetro): a mesma
carta no mesmo dia dá o mesmo texto, qualquer que seja a ordem das chaves no arquivo. Falha
fechada em duas etapas: (1) os portões (ambiente de teste, dados sintéticos, autorização
vigente, dono do produto): um "não" ou "desconhecido" recusa tudo e nenhum outro campo é lido;
(2) cada campo obrigatório, com origem e valor. Só sem nenhuma pendência o perfil é montado, e
ele ainda passa por `ProductProfile.from_data`: o que o perfil recusa, a carta recusa.
Autorização com validade vencida é pendência. Avisos (`warnings`) não recusam nem mudam o
perfil. Resposta `desconhecido` nos quatro campos da tabela `MINIMUM_DEFAULTS` vira o padrão
mínimo da CLI, com aviso (ADR 0114). Na carta `kind: request` (ADR 0120) a CLI antes completa o
que a pessoa não respondeu com a tabela de `request_defaults`, e os portões passam a incluir o
endereço do ambiente. Este módulo é puro.
"""

from collections.abc import Mapping
from datetime import date
from typing import Final

from pydantic import BaseModel, ConfigDict, JsonValue

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.extra_checks_config import NUCLEI_FIELDS
from harness_dast.domain.letter import Gates, Letter
from harness_dast.domain.letter_attack import AttackFlags, read_attack_flags
from harness_dast.domain.letter_collect import (
    GATE_DENIED,
    INVALID_VALUE,
    PRODUCT_MISMATCH,
    PROFILE_REJECTED,
    Collector,
    LetterIssue,
)
from harness_dast.domain.letter_defaults import MinimumDefault, default_notes
from harness_dast.domain.letter_negative import read_allow_invalid_writes
from harness_dast.domain.letter_outcomes import read_include_outcomes
from harness_dast.domain.letter_sections import (
    Block,
    read_auth,
    read_authorization,
    read_environment,
    read_example_data,
    read_limits,
    read_scope,
    read_strength,
)
from harness_dast.domain.letter_shared_roles import read_shared_roles
from harness_dast.domain.letter_technology import read_technologies
from harness_dast.domain.letter_upload import read_allow_upload_scan
from harness_dast.domain.letter_warnings import (
    default_warning,
    expired_issue,
    letter_warnings,
    request_warning,
)
from harness_dast.domain.letter_writes import read_allow_writes
from harness_dast.domain.letter_yaml import render_yaml
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.request_defaults import RequestDefault, request_notes
from harness_dast.domain.request_letter import (
    RequestInputs,
    check_base_url_gate,
    fill_request_letter,
    letter_kind,
    reject_request_only_keys,
)

GENERATED_BLOCKS: Final = (
    "environment",
    "technologies",
    "openapi",
    "scope",
    "limits",
    "auth",
    "scan.strength",
    "scan.include_outcomes",
    "scan.allow_upload_scan",
    "scan.pacing",
    "scan.inject_headers",
    "scan.oast",
    "extra_checks",
    "authz.allow_writes",
    "authz.shared_roles",
    "negative.allow_writes",
)
"""Blocos do `target.yml` que a CLI escreve a partir da carta.

`scan.strength` só se informada; `scan.include_outcomes` só com lista não vazia (ADR 0050);
`scan.allow_upload_scan` só quando a carta o autoriza (ADR 0052);
`scan.pacing` só se `proxy`, `scan.inject_headers`, `scan.oast` e `extra_checks` só quando a
carta os liga (ADR 0096);
`authz.allow_writes` só quando a carta o autoriza (ADR 0038); `negative.allow_writes`, idem
(ADR 0051).
"""

_GATE_DENIED_TEXT = (
    "Respondido 'não'. Sem esta condição o teste não pode ser feito: nada foi gerado. "
    "Fale com o dono do produto; o agente não muda a resposta."
)
_HEADER = (
    "# Gerado por: hdast init <produto> --from-letter <carta.yml> (ADR 0036).\n"
    "# Blocos gerados da carta (o agente não os escreve nem os altera): "
    "environment, openapi, scope, limits, auth, scan.strength.\n"
    "# Para mudar algum deles, a pessoa muda a carta e o perfil é gerado de novo.\n"
)
_HEADER_OUTCOMES = "# Também gerado da carta (ADR 0050): scan.include_outcomes.\n"
_HEADER_UPLOAD = (
    "# Também gerado da carta (ADR 0052): scan.allow_upload_scan, que só a carta autoriza.\n"
)
_HEADER_WRITES = (
    "# Também gerado da carta (ADR 0038): authz.allow_writes, que só a carta autoriza.\n"
)
_HEADER_NEGATIVE = (
    "# Também gerado da carta (ADR 0051): negative.allow_writes, que só a carta autoriza.\n"
)


_HEADER_ATTACK = (
    "# Também gerado da carta (ADR 0096): scan.pacing, scan.inject_headers, scan.oast e "
    "extra_checks, que só a carta liga.\n"
)
_HEADER_REQUEST = (
    "# Modo pedido mínimo (ADR 0120): a pessoa respondeu só às quatro perguntas; a CLI aplicou "
    "os padrões listados abaixo.\n"
    "# Cada padrão está escrito explícito neste arquivo e só vale depois da aprovação humana "
    "(hdast setup). Para mudar um, a pessoa responde na carta e o perfil é gerado de novo.\n"
)


class LetterReview(BaseModel):
    """Resultado da conferência da carta.

    Attributes:
        issues: Pendências, campo a campo; vazio quando a carta está pronta.
        profile_text: O `target.yml` gerado, só quando não há pendência.
        blocks: Blocos do perfil que o texto gerado contém, na ordem em que aparecem.
        example_data: Dados de exemplo da carta, como informação para o agente.
        warnings: Avisos (não bloqueiam e não mudam o perfil gerado) para o agente mostrar à
            pessoa na entrevista; só há avisos com a carta pronta.
    """

    model_config = ConfigDict(frozen=True)

    issues: tuple[LetterIssue, ...]
    profile_text: str | None = None
    blocks: tuple[str, ...] = ()
    example_data: tuple[dict[str, JsonValue], ...] = ()
    warnings: tuple[LetterIssue, ...] = ()

    @property
    def ready(self) -> bool:
        """Se a carta está pronta para gerar o perfil."""
        return not self.issues and self.profile_text is not None


def _check_gates(c: Collector, gates: Gates) -> None:
    answers = (
        ("test_environment", gates.test_environment),
        ("synthetic_data", gates.synthetic_data),
        ("authorization_in_force", gates.authorization_in_force),
    )
    for name, answer in answers:
        field = f"gates.{name}"
        value = c.take(field, answer)
        if value is False:
            c.add(field, GATE_DENIED, _GATE_DENIED_TEXT)
        elif value is not None and value is not True:
            c.add(field, INVALID_VALUE, "Responda true (sim) ou false (não).")
    c.take_text("gates.product_owner", gates.product_owner)


def _profile_data(
    letter: Letter, c: Collector, today: date
) -> tuple[dict[str, object], tuple[dict[str, JsonValue], ...]] | None:
    environment = read_environment(c, letter.environment)
    scope = read_scope(c, letter.scope)
    authorization = read_authorization(c, letter.authorization)
    if authorization is not None:
        valid_until = authorization[0]["valid_until"]
        expired = expired_issue(valid_until, today) if isinstance(valid_until, date) else None
        if expired is not None:
            c.issues.append(expired)
    limits = read_limits(c, letter.limits)
    auth = read_auth(c, letter.auth)
    technologies = read_technologies(c, letter.attack.technologies)
    strength = read_strength(c, letter.attack.strength)
    allow_writes = read_allow_writes(c, letter.attack.allow_authz_writes)
    shared_roles = read_shared_roles(c, letter.attack.authz_shared_roles)
    negative_writes = read_allow_invalid_writes(c, letter.attack.allow_invalid_input_writes)
    outcomes = read_include_outcomes(c, letter.attack.include_outcomes)
    upload_scan = read_allow_upload_scan(c, letter.attack.allow_upload_scan)
    flags = read_attack_flags(c, letter.attack)
    examples = read_example_data(c, letter.example_data)
    if (
        c.issues
        or environment is None
        or scope is None
        or authorization is None
        or limits is None
        or auth is None
    ):
        return None
    scope_block: Block = {
        "allow": scope["allow"],
        "deny_paths": scope["deny_paths"],
        "authorization": authorization[0],
        "path_mode": scope["path_mode"],
        "windows": authorization[1],
    }
    data: dict[str, object] = {
        "schema_version": 1,
        "product": letter.product,
        "environment": environment[0],
        "openapi": environment[1],
        "scope": scope_block,
        "limits": limits,
        "auth": auth,
    }
    data.update(
        {} if technologies is None else {"technologies": technologies.model_dump(mode="json")}
    )
    scan = _scan_data(strength, outcomes, upload_scan, flags)
    if scan:
        data["scan"] = scan
    extra_checks = _extra_checks_data(flags)
    if extra_checks:
        data["extra_checks"] = extra_checks
    authz = _authz_data(allow_writes, shared_roles)
    if authz:
        data["authz"] = authz
    if negative_writes:
        data["negative"] = {"allow_writes": True}
    return data, examples


def _scan_data(
    strength: str | None, outcomes: tuple[str, ...], upload_scan: bool, flags: AttackFlags
) -> Block:
    """Bloco `scan` gerado: só as chaves que a carta informou ou ligou."""
    scan: Block = {}
    if strength is not None:
        scan["strength"] = strength
    if outcomes:
        scan["include_outcomes"] = list(outcomes)
    if upload_scan:
        scan["allow_upload_scan"] = True
    scan.update(_scan_flags(flags))
    return scan


def _scan_flags(flags: AttackFlags) -> Block:
    """Chaves da V1.12 que moram em `scan`; só as ligadas (ou o ritmo `proxy`)."""
    scan: Block = {}
    if flags.pacing != "legacy":
        scan["pacing"] = flags.pacing
    if flags.inject_headers:
        scan["inject_headers"] = True
    if flags.oast:
        scan["oast"] = True
    return scan


def _extra_checks_data(flags: AttackFlags) -> Block:
    fields = ("allow_rate_tests", "experimental_rules", "inventory", *NUCLEI_FIELDS)
    return {name: True for name in fields if getattr(flags, name)}


def _authz_data(allow_writes: bool, shared_roles: tuple[str, ...]) -> dict[str, object]:
    data: dict[str, object] = {}
    if allow_writes:
        data["allow_writes"] = True
    if shared_roles:
        data["shared_roles"] = list(shared_roles)
    return data


def _has_attack_keys(profile: ProductProfile) -> bool:
    scan = profile.scan
    return (
        scan.pacing != "legacy"
        or scan.inject_headers
        or scan.oast
        or not profile.extra_checks.is_default()
    )


def _has_block(data: Mapping[str, object], name: str) -> bool:
    """Se o bloco (caminho pontilhado completo, como `scan.strength`) está no perfil gerado."""
    node: object = data
    for part in name.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return False
        node = node[part]
    return True


def _letter_text(profile: ProductProfile, defaults: tuple[MinimumDefault, ...]) -> str:
    """Cabeçalho da carta assinada (`kind: letter`); inalterado desde o ADR 0114."""
    return (
        _HEADER
        + (_HEADER_OUTCOMES if profile.scan.include_outcomes else "")
        + (_HEADER_UPLOAD if profile.scan.allow_upload_scan else "")
        + (_HEADER_WRITES if profile.authz.allow_writes else "")
        + (_HEADER_NEGATIVE if profile.negative.allow_writes else "")
        + (_HEADER_ATTACK if _has_attack_keys(profile) else "")
        + default_notes(defaults)
    )


def review_letter(
    letter: Letter,
    expected_product: str,
    today: date,
    request: RequestInputs | None = None,
) -> LetterReview:
    """Confere a carta e, se estiver completa, gera o texto do `target.yml`.

    Args:
        letter: Carta já lida e com a forma validada (`Letter.from_data`).
        expected_product: Produto pedido em `hdast init`; a carta precisa ser dele.
        today: Dia de hoje em UTC (entra por parâmetro: o domínio não lê relógio). Autorização
            que venceu antes dele é pendência; a validade longa demais vira aviso.
        request: Só na carta `kind: request` (ADR 0120): os caminhos do OpenAPI e o fuso das
            janelas. Sem eles, o pedido mínimo não gera o escopo e a carta fica pendente.

    Returns:
        A conferência: pendências campo a campo ou o texto gerado.
    """
    c = Collector()
    kind = letter_kind(letter)
    if kind is None:
        c.add(
            "kind",
            INVALID_VALUE,
            "Use kind: letter (carta assinada) ou kind: request (pedido mínimo); ausente vale "
            "letter.",
        )
    if letter.product != expected_product:
        c.add(
            "product",
            PRODUCT_MISMATCH,
            "A carta é de outro produto; use a carta deste produto ou corrija o nome.",
        )
    is_request = kind == "request"
    if not is_request:
        reject_request_only_keys(c, letter)
    _check_gates(c, letter.gates)
    if is_request:
        check_base_url_gate(c, letter)
    if c.issues:
        return LetterReview(issues=tuple(c.issues))
    source = letter
    applied: tuple[RequestDefault, ...] = ()
    if is_request:
        source, applied = fill_request_letter(letter, c, request or RequestInputs(), today)
        if c.issues:
            return LetterReview(issues=tuple(c.issues))
    built = _profile_data(source, c, today)
    if built is None:
        return LetterReview(issues=tuple(c.issues))
    data, examples = built
    try:
        profile = ProductProfile.from_data(data)
    except ConfigError as error:
        c.add("(perfil gerado)", PROFILE_REJECTED, f"{error.message} {error.hint or ''}".strip())
        return LetterReview(issues=tuple(c.issues))
    header = (
        _HEADER + _HEADER_REQUEST + request_notes(applied)
        if is_request
        else _letter_text(profile, tuple(c.defaults))
    )
    return LetterReview(
        issues=(),
        profile_text=header + render_yaml(data),
        blocks=tuple(name for name in GENERATED_BLOCKS if _has_block(data, name)),
        example_data=examples,
        warnings=(
            *(default_warning(default) for default in c.defaults),
            *(request_warning(default) for default in applied),
            *letter_warnings(profile, today),
        ),
    )
