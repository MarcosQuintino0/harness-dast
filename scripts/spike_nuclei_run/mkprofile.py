"""Spike: monta a pasta de produto de uma variante a partir do perfil estendido.

Uso: mkprofile.py PASTA_ORIGEM_DO_LAB PERFIL_ESTENDIDO DESTINO [--inventory] [--extra-rule YAML]
Copia os arquivos do perfil do laboratório, troca o target.yml pelo estendido e, com --inventory,
liga `extra_checks.inventory` (cópia do laboratório; em produto real só a carta liga).
"""

import shutil
import sys
from pathlib import Path

src, extended, dest = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
flags = sys.argv[4:]
if dest.exists():
    shutil.rmtree(dest)
shutil.copytree(src, dest)
text = extended.read_text(encoding="utf-8")
if "--extra-rule" in flags:
    rule = flags[flags.index("--extra-rule") + 1]
    marker = "\n  deny_paths:"
    assert text.count(marker) == 1
    text = text.replace(marker, "\n" + Path(rule).read_text(encoding="utf-8").rstrip("\n") + marker)
if "--inventory" in flags:
    assert "\nextra_checks:" not in text
    text = text.rstrip("\n") + "\n\nextra_checks:\n  inventory: true\n"
(dest / "target.yml").write_text(text, encoding="utf-8")
print("ok", dest)
