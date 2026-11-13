"""Entrega do token ao ZAP: instala, renova e remove as regras do Replacer.

A CLI é dona do segredo: faz o login (mesma sessão do `probe`), monta as regras (nome com o
prefixo `hdast-`, limitadas à origem do alvo) e as instala no ZAP, que só vê o token. A
renovação instala a geração nova ANTES de remover a antiga (não existe `setRule`, e assim
nenhuma requisição sai sem regra). `remove_all` apaga tudo, mesmo depois de erro: a regra
persiste na configuração do ZAP e carregaria o token para a próxima sessão.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

import structlog

from harness_dast.application.ports import Clock, ZapControl
from harness_dast.application.scan_ports import ScanControl
from harness_dast.domain.auth import CsrfConfig
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.scan_tokens import (
    ReplacerRule,
    build_token_rules,
    jwt_expiry,
    refresh_due,
)
from harness_dast.domain.zap_scope import REPLACER_RULE_PREFIX

_log = structlog.get_logger()


class TokenSession(Protocol):
    """O que a entrega precisa da sessão da conta (`AccountSession` a satisfaz)."""

    def relogin(self) -> None:
        """Refaz o login (e o token CSRF, se houver)."""
        ...

    def request_headers(self, method: str) -> tuple[tuple[str, str], ...]:
        """Cabeçalhos de autenticação e, se o método exigir, o de CSRF."""
        ...


class TokenDelivery:
    """Mantém o token atual instalado no Replacer do ZAP."""

    def __init__(
        self,
        *,
        label: str,
        session: TokenSession,
        scanner: ScanControl,
        csrf: CsrfConfig | None,
        url_regex: str,
        clock: Clock,
        refresh_seconds: int,
    ) -> None:
        """Cria a entrega (sem tocar o ZAP).

        Args:
            label: Apelido da conta (entra no nome das regras).
            session: Sessão da conta, já aberta.
            scanner: Porta do ZAP (instala e remove regras).
            csrf: Configuração de CSRF do perfil, ou `None`.
            url_regex: Restrição de URL das regras (só a origem do alvo).
            clock: Relógio injetado.
            refresh_seconds: Idade máxima do token antes de renovar.
        """
        self._label = label
        self._session = session
        self._scanner = scanner
        self._csrf = csrf
        self._url_regex = url_regex
        self._clock = clock
        self._refresh_seconds = refresh_seconds
        self._generation = 0
        self._active: tuple[ReplacerRule, ...] = ()
        self._issued_at: datetime = clock.now()
        self._expires_at: datetime | None = None

    @property
    def generation(self) -> int:
        """Quantas gerações de regras já foram instaladas (1 após `install`)."""
        return self._generation

    def install(self) -> None:
        """Instala a primeira geração de regras com o token atual da sessão.

        Raises:
            ExternalToolError: O ZAP recusou uma regra (por exemplo, add-on ausente).
        """
        self._swap()

    def refresh_if_due(self) -> bool:
        """Renova o token e as regras se estiver na hora. Devolve se renovou.

        Raises:
            PreflightError: O novo login foi recusado.
            ScopeViolation: Janela fechada ou prazo esgotado durante o login.
            ExternalToolError: O ZAP recusou as regras novas.
        """
        due = refresh_due(
            issued_at=self._issued_at,
            now=self._clock.now(),
            interval_seconds=self._refresh_seconds,
            expires_at=self._expires_at,
        )
        if not due:
            return False
        self._session.relogin()
        self._swap()
        return True

    def release(self) -> None:
        """Remove do ZAP as regras desta entrega pelo nome.

        Falha de remoção é registrada no log (sem valores); a varredura final por prefixo, em
        `AccountTokens.remove_all`, é quem garante que nada ficou no ZAP.
        """
        for rule in self._active:
            try:
                self._scanner.remove_replacer_rule(rule.description)
            except ExternalToolError as error:
                _log.error("replacer_remove_failed", rule=rule.description, reason=error.message)
        self._active = ()

    def _swap(self) -> None:
        headers = self._session.request_headers(self._csrf.methods[0] if self._csrf else "POST")
        csrf_name = self._csrf.header_name.lower() if self._csrf else None
        auth = tuple(item for item in headers if item[0].lower() != csrf_name)
        csrf_value = next((value for name, value in headers if name.lower() == csrf_name), None)
        self._generation += 1
        rules = build_token_rules(
            label=self._label,
            generation=self._generation,
            auth_headers=auth,
            csrf=self._csrf,
            csrf_value=csrf_value,
            url_regex=self._url_regex,
        )
        previous = self._active
        for rule in rules:
            self._scanner.add_replacer_rule(rule)
        self._active = rules
        for old in previous:
            self._scanner.remove_replacer_rule(old.description)
        self._issued_at = self._clock.now()
        self._expires_at = next((jwt_expiry(value) for _, value in auth if value), None)


class AccountTokens:
    """Uma entrega de token por conta, com UMA conta ativa por vez no ZAP.

    Cada requisição aprendida é varrida com o token da conta que a enviou no `probe`. Trocar de
    conta remove as regras da anterior ANTES de instalar as da nova: o Replacer nunca tem dois
    tokens de contas diferentes ao mesmo tempo.
    """

    def __init__(self, factory: Callable[[str], TokenDelivery], zap: ZapControl) -> None:
        """Cria o conjunto.

        Args:
            factory: Cria a entrega de uma conta (abre a sessão e faz o login), ainda sem regras.
            zap: Porta de controle do ZAP (varre as regras `hdast-` ao fim).
        """
        self._factory = factory
        self._zap = zap
        self._deliveries: dict[str, TokenDelivery] = {}
        self._active: str | None = None

    def activate(self, account: str) -> None:
        """Deixa instaladas as regras da conta, trocando as da conta anterior.

        Raises:
            PreflightError: Login da conta recusado ou segredo ausente.
            ScopeViolation: Janela fechada ou prazo esgotado durante o login.
            ExternalToolError: O ZAP recusou as regras.
        """
        if self._active == account:
            return
        if self._active is not None:
            self._deliveries[self._active].release()
            self._active = None
        delivery = self._deliveries.get(account)
        if delivery is None:
            delivery = self._factory(account)
            self._deliveries[account] = delivery
        delivery.install()
        self._active = account

    def refresh_if_due(self) -> bool:
        """Renova o token da conta ativa, se estiver na hora."""
        if self._active is None:
            return False
        return self._deliveries[self._active].refresh_if_due()

    def remove_all(self) -> bool:
        """Remove TODAS as regras `hdast-` do ZAP; `False` se a varredura final falhou.

        Primeiro cada entrega remove as suas pelo nome; depois uma varredura por prefixo pega
        qualquer sobra (inclusive de uma instalação que falhou no meio). Falhas vão ao log.
        """
        for delivery in self._deliveries.values():
            delivery.release()
        self._active = None
        try:
            self._zap.remove_stale_rules(REPLACER_RULE_PREFIX)
        except ExternalToolError as error:
            _log.error("replacer_sweep_failed", reason=error.message)
            return False
        return True
