"""Camada de entrada: interpreta argumentos, monta as dependências e formata a saída.

Responsabilidade: traduzir a linha de comando em chamadas à camada `application` e
a resposta em envelope JSON ou texto humano, com o código de saída correspondente.
Não deve conter regra de negócio: escopo, severidade, unicidade e fingerprint
pertencem ao `domain`.
"""
