"""Spike: religa, por variável de ambiente, regras do ZAP desligadas por padrão (só nesta branch)."""

from pathlib import Path

path = Path("/workspaces/n-spike/src/harness_dast/domain/scan_policy.py")
text = path.read_text(encoding="utf-8")
if "SPIKE_ZAP_REENABLE" not in text:
    text = text.replace(
        "import math\nfrom typing import Final\n",
        "import math\nimport os\nfrom typing import Final\n",
        1,
    )
    old = "    disabled = [rule.plugin_id for rule in DEFAULT_DISABLED_RULES if rule.plugin_id not in oast_ids]\n"
    new = (
        "    # SPIKE (branch spike/nuclei, nunca na main): religa regras pelo ambiente, p.ex. 40034,40035.\n"
        '    reenabled = {int(x) for x in os.environ.get("SPIKE_ZAP_REENABLE", "").split(",") if x}\n'
        "    disabled = [\n"
        "        rule.plugin_id\n"
        "        for rule in DEFAULT_DISABLED_RULES\n"
        "        if rule.plugin_id not in oast_ids and rule.plugin_id not in reenabled\n"
        "    ]\n"
    )
    assert old in text
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
print("ok")
