"""Exemplos já declarados, sem envio ou eco dos valores."""

from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.spec_examples import inspect_examples
from tests.fakes.rig import operation


def test_nested_examples_are_checked_without_revealing_values() -> None:
    schema = Schema(
        type="object",
        required=("id",),
        properties={"nome": Schema(type="string", min_length=5)},
        declared_examples=({"nome": "xyz"},),
    )
    spec = ApiSpec(
        title="T",
        version="1",
        operations=(operation("criar", "post", "/api", body={"dados": schema}),),
    )

    result = inspect_examples(spec)

    assert [code for _, code in result] == ["required", "length"]
    assert "xyz" not in str(result)


def test_example_issue_count_is_bounded() -> None:
    schema = Schema(type="integer", declared_examples=tuple("x" for _ in range(101)))
    spec = ApiSpec(
        title="T",
        version="1",
        operations=(operation("criar", "post", "/api", body={"dados": schema}),),
    )

    result = inspect_examples(spec)

    assert len(result) == 101
    assert result[-1][1] == "truncated"
