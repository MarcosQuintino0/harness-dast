"""Dígitos verificadores de CPF, CNPJ e CNS (números brasileiros), todos módulo 11.

Fontes dos algoritmos (conferidas por valores conhecidos nos testes):

- CPF: algoritmo de módulo 11 da Receita Federal, descrito no verbete "Cadastro de Pessoas
  Físicas" da Wikipédia em português. 9 dígitos-base; o 1º dígito usa pesos 10 a 2 e o 2º
  usa pesos 11 a 2 sobre os 10 primeiros. Exemplo clássico válido: 529.982.247-25.
- CNPJ: módulo 11 da Receita Federal (verbete "Cadastro Nacional da Pessoa Jurídica").
  12 dígitos-base (8 da raiz + 4 da filial); pesos 5,4,3,2,9,8,7,6,5,4,3,2 para o 1º dígito
  e 6,5,4,3,2,9,8,7,6,5,4,3,2 para o 2º. Exemplo válido: 11.222.333/0001-81. O CNPJ
  alfanumérico (a partir de julho de 2026) NÃO é gerado aqui, só o numérico.
- CNS (Cartão Nacional de Saúde): especificação do DATASUS. Definitivo (começa com 1 ou 2):
  11 dígitos do PIS + `000` + dígito, ou `001` quando o dígito calculado seria 10.
  Provisório (começa com 7, 8 ou 9): 15 dígitos cuja soma ponderada por 15..1 é múltiplo de
  11. Em ambos, a soma ponderada dos 15 dígitos por 15..1 é divisível por 11.

Todos os números são SINTÉTICOS: passam na validação, mas não foram emitidos a ninguém.
"""

_CPF_WEIGHTS_1 = (10, 9, 8, 7, 6, 5, 4, 3, 2)
_CNPJ_WEIGHTS_1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_CNPJ_WEIGHTS_2 = (6, *_CNPJ_WEIGHTS_1)
_CNS_LENGTH = 15


def _weighted_sum(digits: str, weights: tuple[int, ...]) -> int:
    return sum(int(digit) * weight for digit, weight in zip(digits, weights, strict=True))


def _mod11_digit(total: int) -> int:
    """Dígito de CPF/CNPJ: 11 - resto, com 10 e 11 virando 0."""
    digit = 11 - total % 11
    return 0 if digit >= 10 else digit


def cpf_check_digits(base: str) -> str:
    """Calcula os 2 dígitos verificadores de um CPF a partir dos 9 dígitos-base."""
    first = _mod11_digit(_weighted_sum(base, _CPF_WEIGHTS_1))
    second = _mod11_digit(_weighted_sum(base + str(first), (11, *_CPF_WEIGHTS_1)))
    return f"{first}{second}"


def cnpj_check_digits(base: str) -> str:
    """Calcula os 2 dígitos verificadores de um CNPJ a partir dos 12 dígitos-base."""
    first = _mod11_digit(_weighted_sum(base, _CNPJ_WEIGHTS_1))
    second = _mod11_digit(_weighted_sum(base + str(first), _CNPJ_WEIGHTS_2))
    return f"{first}{second}"


def cns_definitive(pis: str) -> str:
    """Monta um CNS definitivo (15 dígitos) a partir dos 11 dígitos iniciais (1 ou 2 na frente)."""
    weights = tuple(range(_CNS_LENGTH, _CNS_LENGTH - 11, -1))
    total = _weighted_sum(pis, weights)
    digit = (11 - total % 11) % 11
    if digit == 10:
        # Com "001" a soma cresce 2; o novo dígito nunca volta a ser 10.
        return f"{pis}001{(11 - (total + 2) % 11) % 11}"
    return f"{pis}000{digit}"


def cns_provisional(base: str) -> str:
    """Monta um CNS provisório (15 dígitos) a partir de 14 dígitos (7, 8 ou 9 na frente).

    O último dígito é o que zera a soma ponderada módulo 11. Se ele precisasse ser 10, o
    14º dígito-base sobe uma unidade (módulo 10): isso muda a soma em 2 (ou -18), o que
    sempre deixa um dígito possível, então uma única correção basta.
    """
    weights = tuple(range(_CNS_LENGTH, 1, -1))
    current = base
    digit = (-_weighted_sum(current, weights)) % 11
    if digit == 10:
        current = base[:-1] + str((int(base[-1]) + 1) % 10)
        digit = (-_weighted_sum(current, weights)) % 11
    return f"{current}{digit}"
