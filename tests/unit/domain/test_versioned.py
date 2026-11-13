from pathlib import Path

import pytest
import yaml

from harness_dast.domain.datagen import DataRules
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.flow import FlowSpec

TEMPLATES = Path(__file__).parents[3] / "products" / "_template"


def load(name: str) -> object:
    return yaml.safe_load((TEMPLATES / name).read_text(encoding="utf-8"))


def test_template_data_rules_yml_is_accepted_by_the_domain_model_as_is() -> None:
    rules = DataRules.from_data(load("data-rules.yml"))

    assert [rule.generator for rule in rules.rules] == ["br.cpf", "numeric", "email"]
    assert all(rule.unique for rule in rules.rules)


def test_template_flows_yml_is_accepted_by_the_domain_model_as_is() -> None:
    flows = FlowSpec.from_data(load("flows.yml"))

    assert flows.bindings[0].produces.operation == "criarPaciente"
    assert len(flows.bindings[0].consumed_by) == 2


def test_error_messages_name_the_file_not_the_profile() -> None:
    with pytest.raises(ConfigError) as caught:
        FlowSpec.from_data({"schema_version": 1, "bindings": [{"produces": 1}]})

    assert caught.value.message.startswith("Arquivo flows.yml inválido")
    assert "Perfil" not in caught.value.message


def test_version_error_never_echoes_a_non_integer_version() -> None:
    with pytest.raises(ConfigError) as caught:
        DataRules.from_data({"schema_version": "SEGREDO"})

    assert "SEGREDO" not in caught.value.message
