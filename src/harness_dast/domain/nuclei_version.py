"""Versões fixas do Nuclei e do catálogo de modelos (ADR 0122).

O que garante: uma fonte única para as versões que a imagem `docker/nuclei` instala e que a
aprovação humana fixa. Trocar qualquer valor exige rebuild da imagem, novo manifesto e nova
aprovação dos perfis com o Nuclei ligado. O que não faz: não baixa nem confere arquivos; a
conferência do SHA-256 acontece no build da imagem.
"""

from typing import Final

NUCLEI_VERSION: Final = "3.11.1"
"""Release oficial do Nuclei usada pela imagem (publicada em 2026-08-08)."""

TEMPLATES_VERSION: Final = "10.5.1"
"""Tag do `nuclei-templates` usada pela imagem (publicada em 2026-10-23)."""

TEMPLATES_ARCHIVE_SHA256: Final = "00184ad496302cd1dd3cf4b0b1c3aa45d6b35057f7bdf17e932318185ba0ac50"
"""SHA-256 do ZIP da release do catálogo, conferido contra o arquivo de checksums dela."""
