"""Casos de uso e portas (`typing.Protocol`) consumidas por eles.

Responsabilidade: orquestrar o domínio por meio de portas declaradas em `ports.py`.
Não deve importar adaptadores, `cli`, `config` nem bibliotecas de I/O: depende
somente de `domain`.
"""
