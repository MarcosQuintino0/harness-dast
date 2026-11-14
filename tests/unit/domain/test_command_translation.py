from harness_dast.domain.command_translation import (
    UNKNOWN_COMMAND_TEXT,
    translate_command,
    translated_commands,
)


def test_translate_command_devolve_a_frase_fixa_do_probe() -> None:
    assert translate_command("probe") == "Tentou fazer cada função do sistema responder de verdade."


def test_translate_command_de_comando_desconhecido_diz_que_nao_ha_traducao() -> None:
    assert translate_command("comando-que-nao-existe") == UNKNOWN_COMMAND_TEXT


def test_toda_traducao_tem_texto_nao_vazio_e_sem_promessa_de_seguranca() -> None:
    for command in translated_commands():
        text = translate_command(command).lower()
        assert text.strip()
        assert "seguro" not in text
        assert "aprovado" not in text
