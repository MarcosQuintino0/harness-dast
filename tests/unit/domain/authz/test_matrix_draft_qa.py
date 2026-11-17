"""QA independente da V1.4: o rascunho da tabela é YAML seguro para qualquer nome de operação."""

import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_dast.domain.authz.matrix_draft import DraftItem, render_draft

HOSTILE = st.text(
    alphabet=st.characters(exclude_categories=["Cs"], max_codepoint=0xFFFF),
    min_size=1,
    max_size=40,
) | st.sampled_from(
    [
        "a\nb: c",
        "x" + chr(0x2028) + "y",
        "x\u0085y",
        '"; deny: [admin] #',
        "- a",
        "&anchor *x !!python/object:os.system",
        "﻿x",
        "a: b\r\nauthz:\r\n  allow_writes: true",
    ]
)


@given(name=HOSTILE, path=HOSTILE, role=HOSTILE)
@settings(max_examples=300, deadline=None)
def test_draft_round_trips_and_never_fills_deny_when_names_are_hostile(
    name: str, path: str, role: str
) -> None:
    text = render_draft("demo", [DraftItem(name, "GET", path, (role,))], with_run=True)

    loaded = yaml.safe_load(text)

    rules = loaded["authz"]["access_matrix"]
    assert len(rules) == 1
    assert rules[0]["operation"] == name
    assert rules[0]["path"] == path
    assert rules[0]["allow"] == [role]
    assert rules[0]["deny"] == []
    assert set(loaded) == {"authz"}
    assert set(loaded["authz"]) == {"access_matrix"}


def test_draft_keeps_an_operation_name_outside_the_bmp() -> None:
    text = render_draft("demo", [DraftItem("ler😀", "GET", "/x", ())], with_run=False)

    assert yaml.safe_load(text)["authz"]["access_matrix"][0]["operation"] == "ler😀"
