"""Tradução de cada comando do `hdast` para português simples (aba "Terminal" do painel).

A tabela é fixa e escrita no código: o texto nunca vem do alvo nem do agente. Um teste percorre
a árvore de comandos da CLI e falha se existir comando sem tradução aqui. As frases contam o
que o comando FEZ (passado) sem prometer resultado. Este módulo é puro.
"""

from typing import Final

UNKNOWN_COMMAND_TEXT: Final = "Comando sem tradução cadastrada; veja o nome técnico ao lado."

_TRANSLATIONS: Final[dict[str, str]] = {
    "version": "Mostrou qual versão da ferramenta está instalada.",
    "doctor": "Conferiu se estava tudo pronto para começar.",
    "init": "Criou a pasta do produto com os arquivos de perfil para preencher.",
    "profile validate": "Conferiu se o que foi copiado da carta está completo e coerente.",
    "profile approve": "Pediu a uma pessoa que revisasse e aprovasse a cerca e os limites.",
    "profile approval": "Conferiu se uma pessoa já aprovou a cerca e os limites do perfil.",
    "finding acknowledge": "Pediu a uma pessoa que registrasse o que viu em um achado.",
    "strategy validate": "Conferiu a estratégia e seus arquivos locais, sem tocar o alvo.",
    "strategy diff": "Comparou a estratégia com o comportamento anterior, sem tocar o alvo.",
    "strategy migrate": "Criou uma cópia de estratégia para revisão, sem mudar a aprovação.",
    "strategy capture": "Capturou uma cópia da estratégia, sem tocar o alvo nem ativá-la.",
    "knowledge validate": "Conferiu o conhecimento e suas fontes locais.",
    "knowledge diff": "Comparou as fontes do conhecimento com as atuais.",
    "knowledge capture": "Criou copia do conhecimento sem ativar nem tocar o alvo.",
    "plan": "Mostrou uma prévia do trabalho previsto, sem tocar o alvo.",
    "spec inspect": "Leu o Swagger e contou as funções do sistema.",
    "preflight": "Conferiu se as contas de teste conseguem entrar.",
    "probe": "Tentou fazer cada função do sistema responder de verdade.",
    "scan": "Atacou as funções que responderam, com o ZAP, sempre dentro da cerca.",
    "authz": "Comparou o que cada conta enxerga e altera, para achar acesso indevido.",
    "negative": "Enviou valores que o contrato proíbe, um campo por vez, para ver se caem.",
    "report": "Montou o relatório com as falhas encontradas.",
    "run": "Fez o teste inteiro em sequência: alcance, ataque e relatório.",
    "wait": "Aguardou uma execução e consultou seu estado, sem tocar o alvo.",
    "cleanup": "Limpou os dados criados pelo teste, com a confirmação de uma pessoa.",
    "secret set": "Pediu a uma pessoa que guardasse uma credencial no cofre do sistema.",
    "secret list": "Listou os nomes das credenciais guardadas, sem mostrar os valores.",
    "secret delete": "Pediu a uma pessoa que removesse uma credencial do cofre do sistema.",
    "stack up": "Subiu o ambiente de ataque (ZAP e cerca) para este teste.",
    "stack down": "Desligou o ambiente de ataque.",
    "stack status": "Conferiu se o ambiente de ataque está no ar.",
    "stop": "Mandou parar o teste em andamento.",
    "panel": "Montou as páginas do painel deste teste.",
}


def translate_command(command: str) -> str:
    """Frase em português simples que conta o que o comando fez.

    Args:
        command: Subcomando por extenso, como `probe` ou `stack up`.

    Returns:
        A tradução fixa; para comando fora da tabela, uma frase honesta dizendo que não há
        tradução (nunca um texto inventado).
    """
    return _TRANSLATIONS.get(command, UNKNOWN_COMMAND_TEXT)


def translated_commands() -> frozenset[str]:
    """Comandos que têm tradução."""
    return frozenset(_TRANSLATIONS)
