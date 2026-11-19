"""Pergunta única: há uma pessoa diante de um terminal interativo?

Usada pelos comandos que só uma pessoa pode confirmar, como `cleanup`, `profile approve`
e `demo`. Sem terminal (entrada ou saída de diagnóstico redirecionada), a resposta é
não: foi assim que um agente de IA, que roda comandos sem terminal, é barrado.
"""

import sys


def is_interactive() -> bool:
    """`True` só se a entrada padrão e a saída de diagnóstico (stderr) são terminais."""
    return sys.stdin.isatty() and sys.stderr.isatty()
