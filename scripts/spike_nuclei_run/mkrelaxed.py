"""Spike: perfil estendido do alvo com a lista (b) mais os caminhos relaxados de Spring Boot, em blocos de 200."""

import json
import sys
from pathlib import Path

base_profile, base_paths, relaxed_paths, redir_rule, dest = (Path(p) for p in sys.argv[1:6])
paths = sorted(set(base_paths.read_text().split()) | set(relaxed_paths.read_text().split()))
text = base_profile.read_text(encoding="utf-8")
marker = "\n  deny_paths:"
assert text.count(marker) == 1
block = "".join(
    "\n    - host: alvo-pilha\n      scheme: http\n      port: 8080\n      allow_local: true\n"
    f"      paths: {json.dumps(paths[i : i + 200])}\n      methods: [GET]"
    for i in range(0, len(paths), 200)
)
block += "\n" + redir_rule.read_text(encoding="utf-8").rstrip("\n")
text = text.replace(marker, block + marker)
text = text.rstrip("\n") + "\n\nextra_checks:\n  inventory: true\n"
dest.mkdir(parents=True, exist_ok=True)
(dest / "target.yml").write_text(text, encoding="utf-8")
print("caminhos", len(paths))
