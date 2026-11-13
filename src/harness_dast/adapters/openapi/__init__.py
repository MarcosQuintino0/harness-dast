"""Adaptador de especificações OpenAPI: carrega, resolve referências locais e normaliza.

Não deve decidir escopo nem importar adaptadores irmãos ou `cli`.
"""

from harness_dast.adapters.openapi.loader import load_spec

__all__ = ["load_spec"]
