"""Registro dos geradores e a fonte de valores (`ValueSource`) que o domínio consome.

A composição é por tabela: cada nome do catálogo aponta para uma função. Não há herança. Um
teste confere que os nomes daqui são exatamente os do catálogo do domínio.
"""

import random
from collections.abc import Callable
from datetime import datetime

from harness_dast.adapters.datagen import basic, brazil
from harness_dast.adapters.datagen.basic import Environment
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.request_builder import ValueRequest
from harness_dast.domain.window import ensure_aware

type Generator = Callable[[Environment, ValueRequest], JsonValue]


def build_registry() -> dict[str, Generator]:
    """Tabela nome -> função de todos os geradores implementados."""
    return {
        "numeric": basic.gen_numeric,
        "integer": basic.gen_integer,
        "number": basic.gen_number,
        "boolean": basic.gen_boolean,
        "alphanumeric": basic.gen_alphanumeric,
        "uuid": basic.gen_uuid,
        "email": basic.gen_email,
        "uri": basic.gen_uri,
        "date": basic.gen_date,
        "datetime": basic.gen_datetime,
        "choice": basic.gen_choice,
        "constant": basic.gen_constant,
        "sequence": basic.gen_sequence,
        "br.cpf": brazil.gen_cpf,
        "br.cnpj": brazil.gen_cnpj,
        "br.cns": brazil.gen_cns,
        "br.phone": brazil.gen_phone,
        "br.cep": brazil.gen_cep,
    }


class GeneratorCatalogue:
    """Fonte de valores determinística: mesma semente, relógio e pedidos dão os mesmos valores.

    Instâncias são chamáveis e servem como `ValueSource` do `RequestBuilder`.
    """

    def __init__(self, seed: int, now: datetime) -> None:
        """Cria o catálogo.

        Args:
            seed: Semente do gerador de números aleatórios.
            now: Instante de referência para datas (com fuso); o relógio real nunca é lido.

        Raises:
            ConfigError: `now` sem fuso.
        """
        ensure_aware(now)
        self._env = Environment(rng=random.Random(seed), now=now)  # noqa: S311  # dados sintéticos, não é criptografia
        self._registry = build_registry()

    def __call__(self, request: ValueRequest) -> JsonValue:
        """Produz o valor pedido.

        Raises:
            ConfigError: Gerador sem implementação ou argumentos que o esquema não comporta.
        """
        generator = self._registry.get(request.generator)
        if generator is None:
            raise ConfigError(
                "Gerador do catálogo sem implementação nesta versão.",
                hint="Atualize a CLI ou use outro gerador.",
            )
        return generator(self._env, request)
