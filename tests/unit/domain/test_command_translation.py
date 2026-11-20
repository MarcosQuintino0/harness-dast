import pytest

from harness_dast.domain.command_translation import (
    UNKNOWN_COMMAND_TEXT,
    translate_command,
    translated_commands,
)


def test_translate_command_devolve_a_frase_fixa_do_probe() -> None:
    assert translate_command("probe") == "Tentou fazer cada função do sistema responder de verdade."


def test_translate_command_de_comando_desconhecido_diz_que_nao_ha_traducao() -> None:
    assert translate_command("comando-que-nao-existe") == UNKNOWN_COMMAND_TEXT


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("strategy validate", "Conferiu a estratégia e seus arquivos locais, sem tocar o alvo."),
        ("strategy diff", "Comparou a estratégia com o comportamento anterior, sem tocar o alvo."),
        ("strategy migrate", "Criou uma cópia de estratégia para revisão, sem mudar a aprovação."),
        ("plan", "Mostrou uma prévia do trabalho previsto, sem tocar o alvo."),
    ],
)
def test_traducao_descreve_operacao_local(command: str, expected: str) -> None:
    assert translate_command(command) == expected


def test_toda_traducao_tem_texto_nao_vazio_e_sem_promessa_de_seguranca() -> None:
    for command in translated_commands():
        text = translate_command(command).lower()
        assert text.strip()
        assert "seguro" not in text
        assert "aprovado" not in text
