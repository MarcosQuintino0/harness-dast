"""`curl` reproduzível: marcadores no lugar dos segredos e nada do alvo executável."""

import shlex

from harness_dast.domain.curl_repro import build_curl
from harness_dast.domain.finding import FindingEvidence
from harness_dast.domain.redaction import redact_header_block

AUTH = ("Authorization", "Bearer $TOKEN")


def evidence(**changes: object) -> FindingEvidence:
    base = {
        "message_id": 1,
        "request_header": (
            "GET http://alvo:5000/users/v1/%27?q=1 HTTP/1.1\n"
            "Host: alvo:5000\nAuthorization: ***\nX-XSRF-TOKEN: ***\n"
            "Content-Type: application/json"
        ),
        "request_body": "",
    }
    return FindingEvidence.model_validate({**base, **changes})


def test_secrets_become_placeholders_and_the_host_becomes_base_url() -> None:
    command = build_curl(evidence(), auth_header=AUTH, csrf_header="X-XSRF-TOKEN")

    assert command is not None
    assert command.startswith("curl -i -X GET \"$BASE_URL\"'/users/v1/%27?q=1'")
    assert '-H "Authorization: Bearer $TOKEN"' in command
    assert '-H "X-XSRF-TOKEN: $CSRF_TOKEN"' in command
    assert '-H "Content-Type: application/json"' in command
    assert "alvo:5000" not in command


def test_headers_absent_from_the_request_are_not_invented() -> None:
    command = build_curl(
        evidence(request_header="GET http://alvo/x HTTP/1.1\nHost: alvo"),
        auth_header=AUTH,
        csrf_header="X-XSRF-TOKEN",
    )

    assert command is not None
    assert "TOKEN" not in command.replace("$BASE_URL", "")


def test_hostile_path_and_body_are_quoted_so_the_shell_cannot_expand_them() -> None:
    hostile = "/x/$(rm${IFS}-rf${IFS}~);`id`'\"&&echo${IFS}pwned"
    command = build_curl(
        evidence(
            request_header=f"POST http://alvo{hostile} HTTP/1.1\nHost: alvo",
            request_body="$(reboot) `id` '; echo pwned #",
        ),
        auth_header=None,
        csrf_header=None,
    )

    assert command is not None
    tokens = shlex.split(command.replace(" \\\n  ", " "))
    assert tokens[-2] == "--data-raw"
    assert tokens[-1] == "$(reboot) `id` '; echo pwned #"
    assert tokens[:4] == ["curl", "-i", "-X", "POST"]
    assert tokens[4] == "$BASE_URL" + hostile


def test_unsafe_content_type_is_dropped() -> None:
    command = build_curl(
        evidence(request_header='GET http://a/x HTTP/1.1\nContent-Type: text/plain"; rm -rf /'),
        auth_header=None,
        csrf_header=None,
    )

    assert command is not None
    assert "Content-Type" not in command


def test_no_command_without_evidence_or_with_an_unreadable_request_line() -> None:
    assert build_curl(evidence(available=False), auth_header=None, csrf_header=None) is None
    assert build_curl(evidence(request_header=""), auth_header=None, csrf_header=None) is None
    assert build_curl(evidence(request_header="lixo"), auth_header=None, csrf_header=None) is None


def test_root_path_and_missing_path_default_to_slash() -> None:
    command = build_curl(
        evidence(request_header="GET http://alvo HTTP/1.1"), auth_header=None, csrf_header=None
    )

    assert command is not None
    assert shlex.split(command) == ["curl", "-i", "-X", "GET", "$BASE_URL/"]


def test_curl_keeps_path_and_query_of_a_redacted_long_url() -> None:
    header, _ = redact_header_block(
        "GET http://clinica-piloto:8080/api/medicos/busca-por-nome?nome=%27 HTTP/1.1", lambda t: t
    )

    command = build_curl(
        evidence(request_header=header), auth_header=AUTH, csrf_header="X-XSRF-TOKEN"
    )

    assert command is not None
    assert command.startswith("curl -i -X GET \"$BASE_URL\"'/api/medicos/busca-por-nome?nome=%27'")


def test_curl_survives_a_masked_query_value() -> None:
    header, _ = redact_header_block("GET http://h:8080/api/x?token=abc HTTP/1.1", lambda t: t)

    command = build_curl(
        evidence(request_header=header), auth_header=AUTH, csrf_header="X-XSRF-TOKEN"
    )

    assert command is not None
    assert "'/api/x?token=***'" in command
