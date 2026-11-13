"""Configuração da ferramenta, lida das variáveis de ambiente `HDAST_*`."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from harness_dast.domain.errors import ConfigError


class Settings(BaseSettings):
    """Configuração imutável da ferramenta.

    Attributes:
        zap_base_url: URL base da API do ZAP (http ou https, com host).
        zap_api_key: Chave da API do ZAP, quando habilitada.
        zap_proxy_url: URL do proxy do ZAP pelo qual o `probe` envia as requisições; sem valor,
            usa `zap_base_url` (o ZAP serve API e proxy na mesma porta).
        auth_proxy_url: Proxy da rota de login e token CSRF; sem valor, sai direto. Use quando
            o alvo só é alcançável por um proxy de saída, mas a senha não deve passar pelo ZAP.
        zap_ca_file: Certificado (PEM) da CA do ZAP, para alvos HTTPS pela rota do ZAP.
        runs_dir: Diretório onde cada execução grava seus arquivos.
        products_dir: Diretório com os perfis de produto.
        log_level: Nível mínimo de log.
    """

    model_config = SettingsConfigDict(env_prefix="HDAST_", frozen=True, extra="ignore")

    zap_base_url: str = "http://127.0.0.1:8080"
    zap_api_key: SecretStr | None = None
    zap_proxy_url: str | None = None
    auth_proxy_url: str | None = None
    zap_ca_file: Path | None = None
    runs_dir: Path = Path("runs")
    products_dir: Path = Path("products")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("zap_base_url", "zap_proxy_url", "auth_proxy_url")
    @classmethod
    def validate_http_url(cls, value: str | None) -> str | None:
        """Exige URL http(s) com host, para que `file://` e afins nunca cheguem ao cliente."""
        if value is None:
            return value
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("deve ser uma URL http ou https com host")
        return value

    @property
    def effective_zap_proxy_url(self) -> str:
        """Proxy do ZAP efetivo: `zap_proxy_url` ou, na falta dele, `zap_base_url`."""
        return self.zap_proxy_url or self.zap_base_url


def load_settings() -> Settings:
    """Lê e valida a configuração do ambiente.

    Returns:
        A configuração validada.

    Raises:
        ConfigError: Se alguma variável `HDAST_*` tiver valor inválido. A mensagem
            cita os nomes dos campos, nunca os valores.
    """
    try:
        return Settings()
    except ValidationError as exc:
        campos = ", ".join(
            sorted({f"HDAST_{'.'.join(str(p) for p in e['loc']).upper()}" for e in exc.errors()})
        )
    # Levantado fora do `except`: o ValidationError carrega o valor inválido (pode ser a
    # chave do ZAP) e não deve ficar nem como __cause__ nem como __context__.
    raise ConfigError(
        f"Configuração inválida nas variáveis: {campos}.",
        hint="Corrija os valores conforme o .env.example.",
    )
