"""Classificação do achado: CWE e categoria do OWASP API Security Top 10 (2023).

A tabela é pequena de propósito e só tem CWE que a lista oficial de 2023 associa a UMA única
categoria (CWE em mais de uma categoria, como 285 e 319, ficam de fora: seria adivinhar).
Todos os CWE da tabela e os títulos das categorias foram conferidos em 2026-11-13 contra a
seção "References > External" das páginas oficiais do OWASP API Security Top 10 2023 (o
owasp.org redireciona para api-security.owasp.org):
https://api-security.owasp.org/editions/2023/en/0x11-t10 (lista das categorias) e as páginas
0xa1-broken-object-level-authorization, 0xa2-broken-authentication,
0xa3-broken-object-property-level-authorization, 0xa4-unrestricted-resource-consumption,
0xa7-server-side-request-forgery e 0xa8-security-misconfiguration, no mesmo prefixo.
Ficam de fora, de propósito, os CWE que a lista oficial cita em mais de uma categoria (285 em
API1 e API5; 319 em API8 e API10) e as categorias sem CWE próprio (API6 não lista nenhum). Os
títulos ficam em inglês, como no original. Não há aproximação própria do projeto: toda
entrada é mapeamento oficial. Vários riscos do Top 10 (BOLA, BFLA, atribuição em massa, fluxos
de negócio) estão fora do alcance de uma varredura ativa do ZAP. Este módulo é puro.
"""

from typing import Final

OWASP_API_2023: Final[dict[int, str]] = {
    639: "API1:2023 Broken Object Level Authorization",
    204: "API2:2023 Broken Authentication",
    307: "API2:2023 Broken Authentication",
    213: "API3:2023 Broken Object Property Level Authorization",
    915: "API3:2023 Broken Object Property Level Authorization",
    400: "API4:2023 Unrestricted Resource Consumption",
    770: "API4:2023 Unrestricted Resource Consumption",
    799: "API4:2023 Unrestricted Resource Consumption",
    918: "API7:2023 Server Side Request Forgery",
    2: "API8:2023 Security Misconfiguration",
    16: "API8:2023 Security Misconfiguration",
    209: "API8:2023 Security Misconfiguration",
    388: "API8:2023 Security Misconfiguration",
    444: "API8:2023 Security Misconfiguration",
    942: "API8:2023 Security Misconfiguration",
}


def owasp_api_category(cwe: int | None) -> str | None:
    """Categoria do OWASP API Top 10 2023 para o CWE, ou `None` se não houver mapeamento seguro."""
    return None if cwe is None else OWASP_API_2023.get(cwe)
