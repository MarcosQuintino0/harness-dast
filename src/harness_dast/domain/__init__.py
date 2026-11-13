"""Regras e modelos puros do harness: erros, e futuramente escopo, perfil e achados.

Responsabilidade: concentrar toda decisão de negócio (escopo, unicidade, severidade,
fingerprint) em código sem I/O.
Não deve importar nenhum outro pacote do projeto, nem fazer I/O, rede, leitura de
ambiente ou uso de relógio global. Só biblioteca padrão e pydantic.
"""
