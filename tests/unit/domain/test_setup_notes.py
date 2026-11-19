"""Destaques que a pessoa lê antes da aprovação no `hdast setup`."""

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.setup_notes import approval_notes
from tests.fakes.profile_data import valid_profile, valid_profile_data


def test_mostra_endereco_negacoes_validade_e_janelas_quando_declarados() -> None:
    data = valid_profile_data()
    data["scope"]["deny_paths"].append("/api/contas/*/excluir")
    data["scope"]["windows"] = ["seg-sex 08:30-18:00 America/Sao_Paulo", "sab 09:00-12:00 UTC"]
    profile = ProductProfile.from_data(data)

    notes = approval_notes(profile, ())

    assert notes[:5] == (
        "ENDEREÇO DO AMBIENTE",
        "  Ambiente: homolog, endereço https://api.hml.acme-teste.net.br",
        "CAMINHOS NEGADOS",
        "  - /api/admin/**",
        "  - /api/contas/*/excluir",
    )
    assert notes[-3:] == (
        "VALIDADE E JANELAS DE EXECUÇÃO",
        "  Autorização: CHG-4821, válida até 2999-12-31",
        "  Janelas de execução: seg,ter,qua,qui,sex 08:30-18:00 America/Sao_Paulo; "
        "sab 09:00-12:00 UTC",
    )


def test_exibe_as_capacidades_declaradas_quando_estao_ligadas() -> None:
    data = valid_profile_data()
    data["scan"] = {"include_outcomes": ["not_found"], "oast": True}
    data["extra_checks"] = {"experimental_rules": True}
    profile = ProductProfile.from_data(data)

    notes = approval_notes(profile, ())

    start = notes.index("CAPACIDADES ADICIONAIS LIGADAS")
    end = notes.index("OPERAÇÕES QUE PODEM GRAVAR NO AMBIENTE")
    assert notes[start + 1 : end] == (
        "  - scan.oast",
        "  - extra_checks.experimental_rules",
        "  - scan.include_outcomes = not_found",
    )


def test_distingue_metodos_e_permissoes_de_escrita_quando_o_escopo_aceita_post() -> None:
    profile = valid_profile()

    notes = approval_notes(profile, ())

    start = notes.index("OPERAÇÕES QUE PODEM GRAVAR NO AMBIENTE")
    end = notes.index("VALIDADE E JANELAS DE EXECUÇÃO")
    assert notes[start + 1 : end] == (
        "  - Métodos de escrita em scope.allow: POST",
        "  - Escrita entre contas (authz.allow_writes): não",
        "  - Escrita de valores inválidos (negative.allow_writes): não",
        "  - Varredura de envio de arquivos (scan.allow_upload_scan): não",
        "  - Limpeza configurada (cleanup): não",
    )
