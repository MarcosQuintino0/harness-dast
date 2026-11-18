"""Diferencial cerca x servidor: o que o servidor real roteia está entre as leituras do modelo?

Para cada forma de caminho (`;x`, `%2f`, `%252f`, `//`, ponto e espaço finais, maiúsculas, sufixo
`.json`, barra final...) o teste pergunta ao servidor de verdade (Spring na Clínica Piloto, Flask no
VAmPI) se a forma chega ao mesmo recurso que o caminho base. Toda forma que chega tem de estar entre
as leituras que `domain/widepath.interpretations` gera: caso contrário um `deny_paths` escrito
para o caminho base não cobriria um caminho que o servidor atende (divergência grave).

O envio é direto ao alvo local (porta publicada do piloto em 127.0.0.1; o VAmPI não publica porta
e é alcançado por dentro do próprio contêiner). Exige Docker. Marcador `lab_fast`.
"""

import json
import shutil
import subprocess
import textwrap
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.widepath import interpretations, literal_segments
from tests.integration.lab_support import (
    PILOT_PROFILE,
    VAMPI_OPENAPI,
    VAMPI_PROFILE,
    LabCli,
    require_docker,
)
from tests.integration.path_support import artifacts_dir, direct, pilot_state, pilot_token
from tests.integration.run_support import throwaway_pilot_env

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

# Coerção do TIPO do parâmetro (Long no Spring): mesmo recurso por texto que o modelo não relaciona.
NUMERIC_COERCION = {
    "zero a esquerda": "/api/convenios/01",
    "sinal +": "/api/convenios/+1",
    "sinal + codificado": "/api/convenios/%2b1",
    "espaco a esquerda": "/api/convenios/%201",
    "digito arabe-indico": "/api/convenios/%D9%A1",
    "tab final": "/api/convenios/1%09",
    "hexadecimal": "/api/convenios/0x1",
}


@dataclass(frozen=True)
class Resource:
    """Recurso de referência: segmentos do caminho base e quantos deles formam a testemunha."""

    name: str
    segments: tuple[str, ...]
    witness_len: int  # `**` casa o resto: basta o prefixo literal


def forms_for(segments: tuple[str, ...]) -> dict[str, str]:
    """Formas de caminho derivadas dos segmentos do caminho base."""
    forms: dict[str, str] = {"base": "/" + "/".join(segments)}
    for i, seg in enumerate(segments):
        parts = list(segments)
        parts[i] = seg + ";x=1"
        forms[f"; no segmento {i}"] = "/" + "/".join(parts)
        parts[i] = "".join(f"%{ord(c):02x}" if j == 0 else c for j, c in enumerate(seg))
        forms[f"1a letra codificada no segmento {i}"] = "/" + "/".join(parts)
        parts[i] = "".join(f"%25{ord(c):02x}" if j == 0 else c for j, c in enumerate(seg))
        forms[f"1a letra com dupla codificacao no segmento {i}"] = "/" + "/".join(parts)
    for i in range(1, len(segments)):
        head, tail = "/".join(segments[:i]), "/".join(segments[i:])
        for label, glue in {
            "%2f": "%2f",
            "%2F": "%2F",
            "%252f": "%252f",
            "//": "//",
            "%5c": "%5c",
            "/./": "/./",
            "/x/../": "/x/../",
            "/%2e/": "/%2e/",
            "/x/%2e%2e/": "/x/%2e%2e/",
        }.items():
            forms[f"{label} no separador {i}"] = "/" + head + glue + tail
    base = forms["base"]
    for label, suffix in {
        "ponto final": ".",
        "espaco final": "%20",
        "tab final": "%09",
        "barra final": "/",
        "sufixo .json": ".json",
        "sufixo .html": ".html",
        "; final": ";x",
        "barra final dupla": "//",
    }.items():
        forms[label] = base + suffix
    forms["MAIUSCULAS"] = base.upper()
    forms["Capitalizado"] = "/" + "/".join(s.capitalize() for s in segments)
    return forms


def covered(form: str, resource: Resource) -> bool:
    """A testemunha do recurso está entre as leituras do modelo? (recusa conta como coberta)

    Segue o fluxo do guarda amplo: primeiro a leitura literal (que recusa controle, UTF-8 inválido e
    `.`/`..` crus), depois o conjunto de leituras comparado com `deny_paths`.
    """
    try:
        literal_segments(form)
        readings = interpretations(form)
    except ScopeViolation:
        return True
    want = tuple(s.casefold() for s in resource.segments[: resource.witness_len])
    return any(tuple(s.casefold() for s in r[: resource.witness_len]) == want for r in readings)


def _write_artifact(name: str, payload: object) -> None:
    folder = artifacts_dir()
    if folder is not None:
        (folder / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


@pytest.fixture(scope="module", params=["vulnerable", "secure"])
def pilot(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[tuple[str, str]]:
    """Clínica Piloto no ar (modo vulnerável ou corrigido); devolve (modo, token)."""
    require_docker()
    mode = str(request.param)
    cli = LabCli(tmp_path_factory.mktemp(f"diff-pilot-{mode}"), throwaway_pilot_env())
    cli.install_product("clinica-piloto", PILOT_PROFILE)
    args = ["stack", "up", "clinica-piloto"] + (["--secure"] if mode == "secure" else [])
    try:
        assert cli.run(*args, timeout=600).code == 0
        yield mode, pilot_token(cli.env)
    finally:
        cli.stack_down()


def test_pilot_every_route_spring_reaches_is_among_the_model_readings(
    pilot: tuple[str, str],
) -> None:
    mode, token = pilot
    report: list[dict[str, object]] = []
    gaps: list[str] = []
    resources = [
        (Resource("convenio", ("api", "convenios", "1"), 3), "/api/convenios/1"),
        (Resource("saude", ("api", "saude"), 2), "/api/saude"),
    ]
    for resource, base in resources:
        base_reply = direct(base, token)
        assert base_reply.status == 200
        for label, form in forms_for(resource.segments).items():
            reply = direct(form, token)
            reached = reply.status == 200 and reply.body == base_reply.body
            ok = covered(form, resource)
            report.append(
                {
                    "recurso": resource.name,
                    "forma": label,
                    "caminho": form,
                    "status": reply.status,
                    "chega_ao_recurso": reached,
                    "no_modelo": ok,
                }
            )
            if reached and not ok:
                gaps.append(f"{resource.name}: {label}: {form}")
    isca = Resource("isca", ("api", "isca", "x"), 2)
    for label, form in forms_for(isca.segments).items():
        before = int(str(pilot_state()["isca_calls"]))
        reply = direct(form, token)
        reached = int(str(pilot_state()["isca_calls"])) > before
        ok = covered(form, isca)
        report.append(
            {
                "recurso": "isca",
                "forma": label,
                "caminho": form,
                "status": reply.status,
                "chega_ao_recurso": reached,
                "no_modelo": ok,
            }
        )
        if reached and not ok:
            gaps.append(f"isca: {label}: {form}")
    _write_artifact(f"diferencial-piloto-{mode}.json", report)
    assert not gaps, "o servidor alcança o recurso por formas que o modelo não gera: " + "; ".join(
        gaps
    )


def test_pilot_numeric_coercion_reaches_the_resource_outside_the_model_known_gap(
    pilot: tuple[str, str],
) -> None:
    """Achado grave documentado: a coerção de tipo do parâmetro (Long) não está nas leituras.

    `deny_paths: /api/convenios/1` não cobre `/api/convenios/01` nem `/api/convenios/+1`, e o Spring
    entrega o mesmo convênio. Vale nos DOIS modos do proxy (são caminhos limpos). Este teste fixa o
    que o laboratório mediu; quando o modelo passar a cobrir, ele falha e deve ser atualizado.
    """
    mode, token = pilot
    base = direct("/api/convenios/1", token)
    resource = Resource("convenio", ("api", "convenios", "1"), 3)
    rows = []
    for label, form in NUMERIC_COERCION.items():
        reply = direct(form, token)
        rows.append(
            {
                "forma": label,
                "caminho": form,
                "status": reply.status,
                "chega_ao_recurso": reply.status == 200 and reply.body == base.body,
                "no_modelo": covered(form, resource),
            }
        )
    _write_artifact(f"diferencial-piloto-coercao-{mode}.json", rows)
    reached_uncovered = {
        str(r["forma"]) for r in rows if r["chega_ao_recurso"] and not r["no_modelo"]
    }
    assert reached_uncovered, (
        "o modelo passou a cobrir a coerção numérica: atualize este teste e o ADR"
    )


VAMPI_DRIVER = textwrap.dedent(
    """
    import json, socket, sys
    forms = json.load(sys.stdin)
    def raw(path):
        s = socket.create_connection(("127.0.0.1", 5000), timeout=20)
        req = "GET " + path + " HTTP/1.1\\r\\nHost: vampi:5000\\r\\nConnection: close\\r\\n\\r\\n"
        s.sendall(req.encode("latin-1"))
        data = b""
        while True:
            c = s.recv(65536)
            if not c:
                break
            data += c
        head, _, body = data.partition(b"\\r\\n\\r\\n")
        return int(head.split(b" ", 2)[1]), body.decode("utf-8", "replace")
    raw("/createdb")
    print(json.dumps({k: raw(v) for k, v in forms.items()}))
    """
)


def test_vampi_every_route_flask_reaches_is_among_the_model_readings(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    require_docker()
    cli = LabCli(
        tmp_path_factory.mktemp("diff-vampi"),
        {
            "VAMPI_USER_A_USERNAME": "name1",
            "VAMPI_USER_A_PASSWORD": "pass1",
            "VAMPI_USER_B_USERNAME": "name2",
            "VAMPI_USER_B_PASSWORD": "pass2",
            "VAMPI_ADMIN_USERNAME": "admin",
            "VAMPI_ADMIN_PASSWORD": "pass1",
        },
    )
    cli.install_product("vampi", VAMPI_PROFILE, (VAMPI_OPENAPI,))
    gaps: list[str] = []
    report: list[dict[str, object]] = []
    try:
        assert cli.stack_up("vampi", timeout=600).code == 0
        for resource in (
            Resource("usuarios", ("users", "v1"), 2),
            Resource("livros", ("books", "v1"), 2),
            Resource("depuracao", ("users", "v1", "_debug"), 3),
        ):
            forms = forms_for(resource.segments)
            done = subprocess.run(  # noqa: S603 - docker do próprio laboratório
                [
                    shutil.which("docker") or "docker",
                    "exec",
                    "-i",
                    "hdast-vampi-1",
                    "python",
                    "-c",
                    VAMPI_DRIVER,
                ],
                input=json.dumps(forms),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
                check=True,
            )
            replies = json.loads(done.stdout)
            base_status, base_body = replies["base"]
            assert base_status == 200, replies["base"]
            for label, form in forms.items():
                status, body = replies[label]
                reached = status == 200 and body == base_body
                ok = covered(form, resource)
                report.append(
                    {
                        "recurso": resource.name,
                        "forma": label,
                        "caminho": form,
                        "status": status,
                        "chega_ao_recurso": reached,
                        "no_modelo": ok,
                    }
                )
                if reached and not ok:
                    gaps.append(f"{resource.name}: {label}: {form}")
    finally:
        cli.stack_down()
    _write_artifact("diferencial-vampi.json", report)
    assert not gaps, "o servidor alcança o recurso por formas que o modelo não gera: " + "; ".join(
        gaps
    )
