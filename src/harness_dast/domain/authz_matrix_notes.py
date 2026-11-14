"""Mensagens de "não testado" da tabela "quem pode o quê" (ADR 0041), em português. Módulo puro."""

from typing import Final

NOT_REACHED: Final = (
    "O probe não obteve sucesso nesta operação, então não há pedido provado para repetir. "
    "Faça o probe alcançá-la (fix-reachability) e rode de novo."
)
DELETE_NEVER: Final = "O teste nunca envia DELETE; esta proibição não foi testada."
WRITES_BLOCKED: Final = (
    "O método escreve no alvo e o perfil não tem authz.allow_writes (a carta não autoriza "
    "escrita); nada foi enviado."
)
NO_ACCOUNT: Final = (
    "Nenhuma conta de auth.accounts tem este papel; cadastre uma para testar a proibição."
)
NOT_RUN: Final = "O teste parou antes de enviar o pedido desta célula."
NOTHING_TO_DENY: Final = (
    "A regra não lista nenhum papel em deny: ela só documenta quem pode e não há o que testar."
)
