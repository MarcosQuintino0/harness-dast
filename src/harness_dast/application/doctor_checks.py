"""Conferências do `doctor` que olham só o perfil já carregado (sem rede, sem Docker).

São avisos (`warn`), nunca reprovações: o perfil continua válido. Cada aviso diz o que pode dar
errado e o que fazer, sem sugerir ampliar escopo, limite ou janela.
"""

from collections import Counter

from harness_dast.application.doctor_report import DoctorCheck
from harness_dast.domain.profile import ProductProfile


def wide_mode_checks(profile: ProductProfile) -> list[DoctorCheck]:
    """Avisa quando o perfil usa `scope.path_mode: wide` (ADR 0026).

    O modo amplo deixa passar formas ambíguas de caminho; só é tão seguro quanto `deny_paths`.
    Sem aviso no modo estrito (o padrão).
    """
    if profile.scope.path_mode != "wide":
        return []
    listed = len(profile.scope.deny_paths)
    detail = (
        "O perfil usa scope.path_mode: wide (modo amplo do ADR 0026). Esse modo só é seguro "
        f"com deny_paths COMPLETO ({listed} caminho(s) listado(s)): um pedido liberado pode "
        "chegar a um caminho do mesmo host que scope.allow não lista. Confira com o dono do "
        "produto que a carta autoriza o modo amplo e que deny_paths cobre tudo o que não pode "
        "ser tocado."
    )
    return [DoctorCheck(id="path_mode", status="warn", detail=detail, kind="scope")]


def authz_peer_checks(profile: ProductProfile) -> list[DoctorCheck]:
    """Avisa quando nenhum papel tem duas contas: o `authz` horizontal não poderá testar.

    O teste horizontal (BOLA) compara duas contas do MESMO papel. Sem elas, a verificação vai
    para `not_tested`. Só é aviso: o `run` roda o `authz` por padrão (ADR 0038), mas segue sem
    ele (`--no-authz`) e sem conta par.
    """
    roles = Counter(account.role for account in profile.auth.accounts)
    if any(count >= 2 for count in roles.values()):
        return []
    detail = (
        "O perfil não tem duas contas do mesmo papel (auth.accounts): o teste de autorização "
        "horizontal (hdast run, que o roda por padrão, ou hdast authz) não poderá comparar "
        "contas e vai listar a verificação como não testada. Se quiser esse teste, peça ao "
        "dono do produto uma segunda conta do mesmo papel; sem ela, o run segue normalmente."
    )
    return [DoctorCheck(id="authz_peers", status="warn", detail=detail, kind="config")]
