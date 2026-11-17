"""Sessão de uma conta de teste: segredos, login (ou chave fixa) e token CSRF.

O `AccountSession` é o único lugar que lê o valor dos segredos de uma conta. Todo valor
(usuário, senha, chave, token e token CSRF) é registrado no `SecretVault` assim que existe,
para ser mascarado em log, mensagem e trecho de resposta. O token nunca é impresso nem
gravado. Os passos `resolve_secrets`, `login` e `fetch_csrf` são públicos para que o
`preflight` reporte cada um separadamente; `open` os encadeia para o `probe`.
"""

from dataclasses import dataclass, field
from typing import Literal

from harness_dast.application.common_ports import SecretProvider, SecretVault, TargetClient
from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.auth import (
    Account,
    ApiKeyAccount,
    ApiKeyAuth,
    AuthConfig,
    CsrfConfig,
    LoginAccount,
    PasswordLoginAuth,
)
from harness_dast.domain.errors import PreflightError, TargetError
from harness_dast.domain.flow import extract_value
from harness_dast.domain.http_messages import HttpResponse
from harness_dast.domain.login_hint import login_refused_hint
from harness_dast.domain.outcome import parse_json_body
from harness_dast.domain.request_encoding import (
    CSRF_OPERATION_ID,
    build_get_request,
    build_login_request,
)
from harness_dast.domain.secret_ref import SecretRef


def account_secret_fields(account: Account) -> tuple[tuple[str, SecretRef], ...]:
    """Campos secretos de uma conta como (nome do campo, referência)."""
    if isinstance(account, LoginAccount):
        return (("username", account.username), ("password", account.password))
    if isinstance(account, ApiKeyAccount):
        return (("api_key", account.api_key),)
    return ()


@dataclass(frozen=True)
class AuthCredential:
    """Credencial que a sessão envia: onde vai e o valor (sensível).

    Attributes:
        header: Nome do cabeçalho (`Authorization`, `X-API-Key`...).
        scheme: Esquema (`Bearer`); vazio em chave de API.
        value: Token ou chave. Fica fora do `repr`: só o teste "token adulterado" o lê.
        kind: `token` (veio do login) ou `api_key`.
    """

    header: str
    scheme: str
    value: str = field(repr=False)
    kind: Literal["token", "api_key"] = "token"

    def header_value(self, value: str | None = None) -> str:
        """Texto do cabeçalho com `value` (ou o valor real), no formato que a sessão envia."""
        text = self.value if value is None else value
        return f"{self.scheme} {text}".strip() if self.scheme else text


class TokenCache:
    """Tokens de login por apelido de conta, em memória do processo."""

    def __init__(self) -> None:
        """Cria o cache vazio."""
        self._tokens: dict[str, str] = {}

    def get(self, alias: str) -> str | None:
        """Token guardado para a conta, ou `None`."""
        return self._tokens.get(alias)

    def put(self, alias: str, token: str) -> None:
        """Guarda (ou troca) o token da conta."""
        self._tokens[alias] = token


class AccountSession:
    """Estado de autenticação de uma conta durante uma execução."""

    def __init__(
        self,
        *,
        account: Account,
        auth: AuthConfig,
        base_url: str,
        secrets: SecretProvider,
        vault: SecretVault,
        client: TargetClient,
        dispatcher: OperationDispatcher,
        token_cache: TokenCache | None = None,
    ) -> None:
        """Cria a sessão (sem tocar o alvo nem ler segredos).

        Args:
            account: Conta do perfil.
            auth: Bloco `auth` do perfil.
            base_url: URL base do ambiente.
            secrets: Provedor de segredos.
            vault: Registro de segredos a mascarar.
            client: Cliente do alvo (cookies por conta, para o token CSRF).
            dispatcher: Despachante usado para o login e a busca do token CSRF.
            token_cache: Cache de tokens do processo; com ele, a conta que já fez login em outro
                caso de uso do mesmo processo não faz outro.
        """
        self._account = account
        self._auth = auth
        self._base_url = base_url
        self._secrets = secrets
        self._vault = vault
        self._client = client
        self._dispatcher = dispatcher
        self._token_cache = token_cache
        self._values: dict[str, str] = {}
        self._token: str | None = None

    @property
    def alias(self) -> str:
        """Apelido da conta."""
        return self._account.alias

    @property
    def uses_login(self) -> bool:
        """Se a conta obtém token por login (`login_password`); chave de API não faz login."""
        return isinstance(self._auth, PasswordLoginAuth)

    @property
    def csrf(self) -> CsrfConfig | None:
        """Configuração de CSRF do perfil."""
        return self._auth.csrf

    def secret_fields(self) -> tuple[tuple[str, SecretRef], ...]:
        """Campos secretos da conta como (nome do campo, referência)."""
        return account_secret_fields(self._account)

    def resolve_secrets(self) -> None:
        """Lê os segredos da conta e os registra para mascaramento.

        Raises:
            PreflightError: Algum segredo está ausente ou vazio. A mensagem cita o apelido e
                o campo, nunca o valor.
        """
        for name, ref in self.secret_fields():
            value = self._secrets.resolve(ref)
            if not value:
                raise PreflightError(
                    f"O segredo {self.alias}.{name} não está definido ou está vazio.",
                    hint=(
                        f"Defina o segredo indicado em secret_ref de auth.accounts "
                        f"({self.alias}.{name}): variável de ambiente (env:) ou, no cofre "
                        "(keyring:), peça à pessoa para rodar hdast secret set. Faça isso "
                        "antes de executar."
                    ),
                )
            self._vault.register(value)
            self._values[name] = value

    def login(self, *, force: bool = False) -> None:
        """Faz o login (tipo `login_password`) e guarda o token; em `api_key` não faz nada.

        Se o cache do processo já tem o token da conta, usa-o sem enviar nada (a menos que
        `force`, usado quando o alvo diz que o token venceu).

        Raises:
            PreflightError: O login foi recusado, a resposta não é JSON ou não traz o token.
            ScopeViolation: Login fora do escopo, janela fechada ou prazo esgotado.
        """
        auth = self._auth
        if not isinstance(auth, PasswordLoginAuth):
            return
        cached = None if force or self._token_cache is None else self._token_cache.get(self.alias)
        if cached is not None:
            self._token = cached
            self._vault.register(cached)
            return
        request = build_login_request(
            auth,
            base_url=self._base_url,
            account=self.alias,
            username=self._values["username"],
            password=self._values["password"],
            extra_headers=self._csrf_headers("POST"),
        )
        outcome = self._dispatcher.send(request, None)
        response = outcome.response
        if response is None:
            raise PreflightError(
                f"O login da conta {self.alias} não obteve resposta do alvo.",
                hint="Confira se o alvo está no ar e acessível (preflight, target_health).",
            )
        self._token = self._token_from(response)
        self._vault.register(self._token)
        if self._token_cache is not None:
            self._token_cache.put(self.alias, self._token)

    def fetch_csrf(self) -> None:
        """Faz o GET que emite o cookie CSRF e registra o valor para mascaramento.

        Raises:
            PreflightError: O alvo não respondeu, recusou o GET ou não emitiu o cookie.
        """
        csrf = self.csrf
        if csrf is None:
            return
        request = build_get_request(
            base_url=self._base_url,
            path=csrf.fetch_path,
            operation_id=CSRF_OPERATION_ID,
            account=self.alias,
            route="auth",
        )
        headers = request.headers + self._auth_headers()
        outcome = self._dispatcher.send(request.model_copy(update={"headers": headers}), None)
        response = outcome.response
        cookie = self._client.cookie_value(self.alias, csrf.cookie_name)
        if response is None or response.status >= 400 or not cookie:
            raise PreflightError(
                f"Não foi possível obter o token CSRF da conta {self.alias}.",
                hint="Confira auth.csrf.fetch_path e auth.csrf.cookie_name no target.yml.",
            )
        self._vault.register(cookie)

    def open(self) -> None:
        """Prepara a conta para o `probe`: segredos, token CSRF, login e novo token CSRF.

        O login também exige o token CSRF em alvos protegidos, e o Spring o troca depois da
        autenticação; por isso a busca vem antes e depois.

        Raises:
            PreflightError: Qualquer passo falhou (veja cada passo).
            ScopeViolation: Fora do escopo, janela fechada ou prazo esgotado.
        """
        self.resolve_secrets()
        self.fetch_csrf()
        self.login()
        if isinstance(self._auth, PasswordLoginAuth):
            self.fetch_csrf()

    def relogin(self) -> None:
        """Refaz o login depois de um 401 de token vencido (e o token CSRF, se houver)."""
        self.login(force=True)
        if isinstance(self._auth, PasswordLoginAuth):
            self.fetch_csrf()

    def refresh_csrf(self) -> None:
        """Busca o token CSRF de novo (403 que parece rejeição de CSRF)."""
        self.fetch_csrf()

    def request_headers(self, method: str) -> tuple[tuple[str, str], ...]:
        """Cabeçalhos de autenticação e, se o método exigir, o de CSRF."""
        return self._auth_headers() + self._csrf_headers(method)

    def credential(self) -> AuthCredential | None:
        """Credencial já obtida (nenhum login novo), ou `None` se a conta ainda não tem uma.

        É o único ponto que entrega o VALOR do token ou da chave a outro código (o teste
        "token adulterado"); quem o recebe não pode gravá-lo nem imprimi-lo.
        """
        auth = self._auth
        if isinstance(auth, ApiKeyAuth):
            return AuthCredential(auth.header_name, "", self._values["api_key"], "api_key")
        if self._token is None:
            return None
        return AuthCredential(auth.token_header, auth.token_scheme, self._token)

    def _auth_headers(self) -> tuple[tuple[str, str], ...]:
        credential = self.credential()
        return () if credential is None else ((credential.header, credential.header_value()),)

    def _csrf_headers(self, method: str) -> tuple[tuple[str, str], ...]:
        csrf = self.csrf
        if csrf is None or method not in csrf.methods:
            return ()
        cookie = self._client.cookie_value(self.alias, csrf.cookie_name)
        return ((csrf.header_name, cookie),) if cookie else ()

    def _token_from(self, response: HttpResponse) -> str:
        auth = self._auth
        if not isinstance(auth, PasswordLoginAuth) or response.status >= 400:
            raise PreflightError(
                f"O login da conta {self.alias} foi recusado pelo alvo (HTTP {response.status}).",
                hint=login_refused_hint(
                    response.status,
                    auth.request_encoding if isinstance(auth, PasswordLoginAuth) else None,
                ),
            )
        body: JsonValue = parse_json_body(response)
        try:
            token = extract_value(body, auth.token_response_field)
        except TargetError:
            raise PreflightError(
                f"A resposta do login da conta {self.alias} não traz o token esperado.",
                hint=(
                    "Confira auth.token_response_field e request_encoding no target.yml. Se o "
                    "alvo responde 2xx sem token, a conta pode não existir ainda: se a carta "
                    "autoriza um GET idempotente que recria os dados de exemplo, declare-o em "
                    "probe.setup_path (o preflight e o run o chamam antes dos logins)."
                ),
            ) from None
        if isinstance(token, int) or not token:
            raise PreflightError(
                f"O token do login da conta {self.alias} não é um texto.",
                hint="Confira auth.token_response_field no target.yml.",
            )
        return token
