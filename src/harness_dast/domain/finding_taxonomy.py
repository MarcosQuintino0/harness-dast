"""Classificação do achado: CWE e categoria do OWASP API Security Top 10 (2023).

A tabela é pequena de propósito e só tem CWE que a lista oficial de 2023 associa a UMA única
categoria (CWE em mais de uma categoria, como 285 e 319, ficam de fora: seria adivinhar).
Fonte: páginas das categorias em https://owasp.org/API-Security/editions/2023/en/. A tabela
foi escrita de memória das páginas e NÃO foi conferida contra elas nesta rodada (sem rede):
conferir antes de tratar a categoria como contrato. Vários riscos do Top 10 (BOLA, BFLA,
atribuição em massa, fluxos de negócio) estão fora do alcance de uma varredura ativa do ZAP.
Este módulo é puro.
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
