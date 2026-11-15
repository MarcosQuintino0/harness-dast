"""Do diário de comandos (ADR 0033) para o gancho `commands` do painel. Módulo puro.

Cada `JournalEntry` vira um `PanelCommand`: a hora, o comando cru (como a pessoa o digitou), a
frase que o traduz (tabela fixa em `command_translation`), a etapa, o estado e o resumo da
resposta. Regras, todas aqui e testadas:

- a etapa de cada comando sai de uma tabela fixa (`_STAGE_OF`), nunca do agente: `run` conta
  como varredura e `panel` como organização dos achados; comando de preparação (`doctor`,
  `init`, `profile validate`, `spec inspect`, `stack up`...) fica sem etapa;
- o diário já guarda só nomes de flags, valores sem segredo e um resumo de contagens; aqui nada
  de novo é lido do alvo, e a página ainda escapa e redige tudo de novo;
- a resposta mostrada é o código de saída, o código do erro com a frase que o explica e o
  resumo (`chave: valor`). A mensagem de erro por extenso NÃO está no diário (ele nunca guarda
  texto livre do alvo), então a aba mostra o código e o que ele quer dizer.
"""

import json
from collections.abc import Sequence
from typing import Final

from harness_dast.domain.command_journal import CommandState, JournalEntry
from harness_dast.domain.command_translation import translate_command
from harness_dast.domain.panel_model import CommandStatus, PanelCommand, PanelJournal, StageKey

_STAGE_OF: Final[dict[str, StageKey]] = {
    "preflight": "preflight",
    "probe": "probe",
    "scan": "scan",
    "run": "scan",
    "authz": "authz",
    "negative": "negative",
    "report": "report",
    "panel": "report",
}
_STATUS_OF: Final[dict[CommandState, CommandStatus]] = {
    "ok": "ok",
    "parcial": "partial",
    "erro": "error",
}
_ERROR_MEANING: Final[dict[str, str]] = {
    "CONFIG_ERROR": "Algo no pedido, no perfil ou na configuração está errado: corrija e rode "
    "de novo.",
    "SCOPE_VIOLATION": "A cerca barrou o pedido: ele ficaria fora do que a carta permite.",
    "SCOPE_NOT_APPROVED": "Uma pessoa ainda não aprovou o escopo, ou ele mudou depois da "
    "aprovação: a ferramenta não toca o sistema testado até lá.",
    "PREFLIGHT_FAILED": "As contas de teste não conseguiram entrar.",
    "SECRET_BACKEND_ERROR": "O cofre de credenciais do sistema não respondeu.",
    "EXTERNAL_TOOL_ERROR": "Uma ferramenta de apoio (ZAP ou Docker) falhou.",
    "TARGET_ERROR": "O sistema testado respondeu de um jeito que a ferramenta não aceita.",
    "TARGET_TIMEOUT": "O sistema testado não respondeu a tempo.",
    "TARGET_UNREACHABLE": "A ferramenta não conseguiu falar com o sistema testado.",
    "CLEANUP_FAILED": "A limpeza dos dados do teste não terminou.",
    "INTERRUPTED": "Uma pessoa interrompeu o comando.",
    "INTERNAL": "Erro interno da ferramenta: avise quem mantém o hdast.",
}
_NO_MEANING: Final = "Erro sem explicação cadastrada: veja o código ao lado."


def stage_of_command(command: str) -> StageKey | None:
    """Etapa do teste a que o comando pertence, ou `None` para comando de preparação."""
    return _STAGE_OF.get(command)


def _quote(value: str) -> str:
    return f'"{value}"' if not value or any(char.isspace() for char in value) else value


def command_line(entry: JournalEntry) -> str:
    """O comando como foi digitado: `hdast probe clinica-piloto --seed 7`.

    Os valores das flags já vêm redigidos e cortados do diário.
    """
    parts = ["hdast", *entry.command.split()]
    if entry.product is not None:
        parts.append(entry.product)
    parts.extend(_quote(item) for item in entry.args)
    for flag in entry.flags:
        parts.append(flag.name)
        if flag.value is not None:
            parts.append(_quote(flag.value))
    return " ".join(parts)


def response_text(entry: JournalEntry) -> str:
    """Resumo da resposta em linhas `chave: valor` (texto cru; a página escapa)."""
    lines = [f"código de saída: {entry.exit_code}"]
    if entry.error_code:
        meaning = _ERROR_MEANING.get(entry.error_code, _NO_MEANING)
        lines.append(f"erro: {entry.error_code}")
        lines.append(meaning)
    lines.extend(
        f"{name}: {json.dumps(value, ensure_ascii=False)}" for name, value in entry.summary.items()
    )
    return "\n".join(lines)


def to_panel_command(entry: JournalEntry) -> PanelCommand:
    """Converte uma linha do diário no comando que a aba Terminal desenha."""
    return PanelCommand(
        at=entry.started_at,
        stage=stage_of_command(entry.command),
        command=command_line(entry),
        translation=translate_command(entry.command),
        status=_STATUS_OF[entry.state],
        seconds=round((entry.finished_at - entry.started_at).total_seconds(), 3),
        output=response_text(entry),
    )


def build_journal(
    entries: Sequence[JournalEntry], skipped_lines: int, *, has_diary: bool
) -> PanelJournal | None:
    """O diário do teste para o painel, ou `None` quando não há diário nenhum.

    Diário que existe mas não tem comando deste teste vira um diário com zero comandos: o painel
    diz isso, em vez de afirmar que o teste é anterior à versão 1.2.

    Args:
        entries: Trecho do diário que pertence ao teste, em ordem cronológica.
        skipped_lines: Linhas corrompidas que a leitura pulou.
        has_diary: Se o diário do produto tem alguma linha, de qualquer teste.
    """
    if not entries and not has_diary:
        return None
    return PanelJournal(
        commands=tuple(to_panel_command(item) for item in entries), skipped_lines=skipped_lines
    )
