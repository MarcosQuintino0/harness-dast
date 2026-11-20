"""CSS embutido de `report.html` (claro e escuro, sem fonte nem recurso externo). Módulo puro."""

from typing import Final

STYLE: Final = """
:root {
  --bg: #f7f7f4; --card: #ffffff; --ink: #1c1f23; --muted: #555b63; --line: #d9dbd6;
  --code-bg: #f0f0ec; --accent: #1b5fa8;
  --high: #a4161a; --high-bg: #fde8e8; --medium: #8a4b00; --medium-bg: #fdf0d8;
  --low: #1d5d8a; --low-bg: #e3f0fa; --info: #4a5058; --info-bg: #ececea;
  --unknown: #6a2c91; --unknown-bg: #f1e6f8; --warn-bg: #fff4d6; --warn-line: #c9962b;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14171a; --card: #1e2227; --ink: #e8eaec; --muted: #a2a9b1; --line: #343a41;
    --code-bg: #14171a; --accent: #7db4ee;
    --high: #ff9a9a; --high-bg: #3d1a1c; --medium: #f4c27a; --medium-bg: #3a2a10;
    --low: #8cc4ef; --low-bg: #14293a; --info: #b4bac1; --info-bg: #2a2f35;
    --unknown: #d8b0f2; --unknown-bg: #2f1d3b; --warn-bg: #3a3110; --warn-line: #b38a1f;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 62rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
h1 { font-size: 1.7rem; margin: 0 0 .25rem; }
h2 { font-size: 1.3rem; margin: 2.2rem 0 .8rem; padding-top: .8rem;
  border-top: 1px solid var(--line); }
h3 { font-size: 1.1rem; margin: 1.4rem 0 .6rem; }
p, li { max-width: 70ch; }
.muted { color: var(--muted); font-size: .92rem; }
.banner { background: var(--warn-bg); border-left: 4px solid var(--warn-line);
  padding: .7rem 1rem; margin: 1rem 0; border-radius: 4px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr)); gap: .6rem; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 8px;
  padding: .7rem .9rem; }
.card b { display: block; font-size: 1.8rem; line-height: 1.1; }
.sev-high { color: var(--high); } .sev-medium { color: var(--medium); }
.sev-low { color: var(--low); } .sev-informational { color: var(--info); }
.sev-unknown { color: var(--unknown); }
.group { background: var(--card); border: 1px solid var(--line); border-radius: 8px;
  padding: .9rem 1.1rem; margin: .8rem 0; border-left-width: 5px; }
.group.high { border-left-color: var(--high); } .group.medium { border-left-color: var(--medium); }
.group.low { border-left-color: var(--low); }
.group.informational { border-left-color: var(--info); }
.group.unknown { border-left-color: var(--unknown); }
.group h4 { margin: 0 0 .3rem; font-size: 1.05rem; }
.badge { display: inline-block; font-size: .8rem; padding: .05rem .5rem; border-radius: 99px;
  background: var(--info-bg); color: var(--info); margin-left: .35rem; vertical-align: middle; }
.badge.high { background: var(--high-bg); color: var(--high); }
.badge.medium { background: var(--medium-bg); color: var(--medium); }
.badge.low { background: var(--low-bg); color: var(--low); }
.badge.unknown { background: var(--unknown-bg); color: var(--unknown); }
.note { background: var(--info-bg); border-radius: 6px; padding: .5rem .8rem; margin: .6rem 0; }
code, pre { font: .86rem/1.45 ui-monospace, SFMono-Regular, Consolas, monospace; }
code { background: var(--code-bg); padding: .05rem .3rem; border-radius: 4px; }
pre { background: var(--code-bg); border: 1px solid var(--line); border-radius: 6px;
  padding: .7rem .9rem; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
details { margin: .5rem 0; } summary { cursor: pointer; color: var(--accent); }
table { border-collapse: collapse; width: 100%; font-size: .92rem; display: block;
  overflow-x: auto; }
th, td { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid var(--line);
  vertical-align: top; }
ol.steps li { margin: .35rem 0; }
@media (max-width: 40rem) { main { padding: 1rem .75rem 3rem; } h1 { font-size: 1.4rem; } }
@media print { body { background: #fff; color: #000; } details > * { display: block; } }
"""
