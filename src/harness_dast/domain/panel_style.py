"""CSS embutido de toda página do painel da execução. Módulo puro.

Duas partes: os tokens (`panel_tokens`, cópia do `tokens.css` do desenho: cor, espaço, letra e
tema claro ou escuro conforme o aparelho) e as regras dos componentes, copiadas das telas do
desenho (`docs/design/execution-panel/screens/`). As telas usam nomes curtos para as cores
(`--s1`, `--ink`, `--run`...); aqui eles são apelidos dos tokens, então o tema vem só dos tokens.
Sem fonte nem imagem externa.
"""

from typing import Final

from harness_dast.domain.panel_tokens import TOKENS_CSS

COMPONENTS_CSS: Final = """
body{margin:0}
.tp{--bg:var(--color-bg);--s1:var(--color-surface);--s2:var(--color-surface-2);--ink:var(--color-text);--mu:var(--color-text-muted);--ln:var(--color-border);--run:var(--color-live);--runs:var(--color-live-soft);--ok:var(--color-ok);--oks:var(--color-ok-soft);--gr:var(--color-danger);--grs:var(--color-danger-soft);--am:var(--color-warn);--ams:var(--color-warn-soft);--term:var(--color-terminal);--sel:var(--color-selection)}
.tp{background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI",system-ui,-apple-system,Roboto,sans-serif;font-variant-numeric:tabular-nums;min-height:100vh}
.tp *{box-sizing:border-box}
.tp ::selection{background:var(--sel)}
.tp h1,.tp h2,.tp h3,.tp p,.tp ul,.tp ol,.tp pre{margin:0}
.tp ul,.tp ol{padding:0;list-style:none}
.tp a{color:var(--run);text-underline-offset:3px}
.tp a:hover{color:var(--ink)}
.tp a:focus-visible{outline:2px solid var(--run);outline-offset:3px;border-radius:4px}
.mu{color:var(--mu)}
.sm{font-size:13.5px}
.top{display:flex;flex-wrap:wrap;gap:8px 28px;align-items:center;padding:0 clamp(14px,2vw,28px);background:var(--s1);border-bottom:1px solid var(--ln)}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;padding:14px 0}
.brand i{width:22px;height:22px;border-radius:6px;background:var(--run);display:block;position:relative}
.brand i::after{content:"";position:absolute;inset:6px;border:2px solid var(--s1);border-radius:2px}
.brand a{color:var(--mu);text-decoration:none;font-weight:600}
.brand a:hover{color:var(--ink)}
.brand .here{color:var(--ink)}
.sep{color:var(--mu);font-weight:400}
.tbl{width:100%;border-collapse:collapse;font-size:14.5px}
.tbl th{text-align:left;font-size:13px;color:var(--mu);font-weight:600;padding:8px 14px 8px 0;border-bottom:1px solid var(--ln);white-space:nowrap}
.tbl td{padding:12px 14px 12px 0;border-bottom:1px solid var(--ln);vertical-align:middle}
.tbl tr.selrow td{background:var(--s2)}
.tbl td:first-child,.tbl th:first-child{padding-left:10px;white-space:nowrap}
.trend{display:flex;align-items:flex-end;gap:10px;height:96px;border-bottom:1px solid var(--ln)}
.trend div{flex:1 1 0;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:4px;font-size:13px;font-weight:700}
.trend i{display:block;width:100%;max-width:44px;background:var(--ink);border-radius:4px 4px 0 0;min-height:3px}
.trendx{display:flex;gap:10px;font-size:12px;color:var(--mu);margin-top:6px}
.trendx span{flex:1 1 0;text-align:center}
.tp a.prod{flex:1 1 360px;text-decoration:none;color:var(--ink)}
.tp a.prod:hover{border-color:var(--run)}
.prod b.nm{display:block;font-size:20px}
.stg{display:grid;grid-template-columns:44px minmax(0,1fr) auto;gap:6px 18px;padding:18px 0;border-top:1px solid var(--ln);align-items:start}
.stg .nb{width:34px;height:34px;border-radius:50%;background:var(--oks);color:var(--ok);font-weight:700;display:flex;align-items:center;justify-content:center}
.stg .tm{text-align:right;white-space:nowrap}
.stg .tm b{display:block;font-size:18px}
.tabs{display:flex;flex-wrap:wrap;gap:0 4px;align-self:stretch}
.tabs a{display:flex;align-items:center;gap:8px;padding:14px 14px 12px;text-decoration:none;color:var(--mu);font-weight:600;border-bottom:3px solid transparent}
.tabs a:hover{color:var(--ink)}
.tabs .on{color:var(--ink);border-bottom-color:var(--run)}
.cnt{font-size:12px;font-weight:700;padding:0 7px;border-radius:99px;background:var(--grs);color:var(--gr)}
.chip{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:700;padding:3px 11px;border-radius:99px;white-space:nowrap}
.chip i{width:8px;height:8px;border-radius:50%;background:currentColor;display:block}
.ch-run{background:var(--runs);color:var(--run)}
.ch-ok{background:var(--oks);color:var(--ok)}
.ch-gr{background:var(--grs);color:var(--gr)}
.ch-am{background:var(--ams);color:var(--am)}
.ch-mu{background:var(--s2);color:var(--mu)}
.pg{padding:clamp(14px,2vw,24px) clamp(14px,2vw,28px) 32px;display:flex;flex-direction:column;gap:16px;max-width:1440px;margin:0 auto}
.g{display:flex;flex-wrap:wrap;gap:16px;align-items:stretch}
.card{background:var(--s1);border:1px solid var(--ln);border-radius:12px;padding:20px 22px;min-width:0;display:flex;flex-direction:column;gap:12px}
.h{font-size:14px;font-weight:700;display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.h a,.h span{font-weight:400;font-size:13.5px}
.big{font-size:clamp(24px,3vw,34px);line-height:1.18;font-weight:650;letter-spacing:-.012em;text-wrap:balance;max-width:24ch}
.stats{display:flex;flex-wrap:wrap;gap:14px 34px}
.stat b{display:block;font-size:24px;line-height:1.15;font-weight:650}
.stat span{font-size:13px;color:var(--mu)}
.r{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--ln)}
.r>.end{margin-left:auto;white-space:nowrap;color:var(--mu);font-size:13.5px;padding-left:10px;text-align:right}
.dotk{flex:none;width:10px;height:10px;margin-top:6px;border-radius:50%;display:block}
.k-ok{background:var(--ok)}
.k-gr{background:var(--gr);border-radius:1px;transform:rotate(45deg) scale(.9)}
.k-am{border:2px solid var(--am)}
.k-run{border:3px solid var(--run)}
.k-no{border:1px solid var(--mu)}
.k-out{border:1px dashed var(--mu);border-radius:2px}
.bars{display:inline-flex;gap:3px;vertical-align:middle}
.bars i{display:block;width:16px;height:7px;border-radius:2px;border:1px solid var(--mu)}
.bars .f{background:var(--ink);border-color:var(--ink)}
.who{flex:none;width:96px;font-size:13px;font-weight:700;color:var(--run)}
.track{display:flex;gap:4px}
.seg{min-width:0;padding-top:10px;border-top:6px solid var(--ok);display:flex;flex-direction:column;gap:1px;overflow:hidden;border-radius:2px 2px 0 0}
.seg b{font-weight:600;white-space:nowrap;font-size:14px}
.seg span{font-size:12.5px;color:var(--mu);white-space:nowrap}
.seg-run{border-image:linear-gradient(90deg,var(--run) 0 42%,var(--ln) 42% 100%) 1}
.seg-run b{color:var(--run)}
.seg-no{border-top-color:var(--ln)}
.seg-no b{color:var(--mu)}
.prog{height:8px;background:var(--s2);border-radius:99px;overflow:hidden}
.prog i{display:block;height:8px;background:var(--run);border-radius:99px}
.term{background:var(--term);border:1px solid var(--ln);border-radius:8px;padding:14px 16px;font:13px/1.7 ui-monospace,"Cascadia Mono",Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}
.term .t,.term .o{color:var(--mu)}
.term .c{color:var(--ink);font-weight:600}
.term .rn{color:var(--run)}
.cur{display:inline-block;width:8px;height:15px;background:var(--run);vertical-align:-2px}
.hl{color:var(--gr);font-weight:700;background:var(--grs);padding:0 3px;border-radius:3px}
.ex{font-size:11.5px;font-weight:600;color:var(--mu);border:1px dashed var(--mu);border-radius:4px;padding:0 5px;white-space:nowrap}
.grid{display:flex;flex-wrap:wrap;gap:6px}
.grid i{width:30px;height:30px;display:block;border:1px solid var(--mu);border-radius:5px;background:transparent}
.grid .d{background:var(--ok);border-color:var(--ok)}
.grid .s{background:var(--gr);border-color:var(--gr);border-radius:50%}
.grid .n{border:3px solid var(--run);background:var(--runs)}
.lg{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;color:var(--mu)}
.lg span{display:flex;gap:7px;align-items:center}
.lg .dotk{margin:0}
.tp .pick{display:block;padding:12px 14px;border:1px solid var(--ln);border-radius:9px;text-decoration:none;color:var(--ink)}
.pick b{display:block;font-weight:600;margin-bottom:5px}
.pick-on{border-color:var(--run);background:var(--runs)}
.area{flex:1 1 190px;min-width:0}
.area h3{font-size:13.5px;font-weight:700;padding-bottom:6px;border-bottom:1px solid var(--ln);margin-bottom:6px;display:flex;justify-content:space-between}
.area h3 span{font-weight:400;color:var(--mu)}
.fn{display:block;position:relative;padding:3px 0 3px 20px;font-size:14px;line-height:1.4}
.fn .dotk{position:absolute;left:0;top:2px}
.stack{display:flex;height:16px;border-radius:99px;overflow:hidden;background:var(--s2)}
.stack i{display:block}
.cmd{display:grid;grid-template-columns:86px minmax(0,1.1fr) minmax(0,1.2fr) 74px 118px;gap:4px 18px;padding:10px 0;border-top:1px solid var(--ln);align-items:baseline}
.cmd code{font:13px/1.6 ui-monospace,"Cascadia Mono",Consolas,monospace;overflow-wrap:anywhere;font-weight:600}
.cmd .tm{font-size:13px;color:var(--mu);white-space:nowrap;text-align:right}
.cmd .hr{font:12.5px/1.6 ui-monospace,Consolas,monospace;color:var(--mu)}
.grp{display:flex;justify-content:space-between;gap:12px;font-size:13.5px;font-weight:700;padding:16px 0 8px}
.grp span{font-weight:400;color:var(--mu)}
.scroll{overflow-x:auto}
.tbl td,.tbl th{white-space:nowrap}
.copy{user-select:all}
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.tp a.gl{color:inherit;text-decoration:none;border-bottom:1px dotted var(--mu)}
.tp a.gl:hover{color:var(--run)}
.tp a.end,.tp .h a{display:inline-block;padding:5px 0}
.b-hatch{background:repeating-linear-gradient(135deg,var(--mu) 0 2px,transparent 2px 6px)}
.kvl{flex:none;width:112px;color:var(--mu);font-size:13.5px;padding-top:1px}
.mono{font:13px/1.6 ui-monospace,"Cascadia Mono",Consolas,monospace;overflow-wrap:anywhere}
.stepn{flex:none;width:26px;height:26px;border-radius:50%;background:var(--runs);color:var(--run);font-weight:700;font-size:13.5px;display:inline-flex;align-items:center;justify-content:center;margin-right:8px}
.sub{background:var(--s2);border-radius:10px;padding:16px 18px;display:flex;flex-direction:column;gap:6px;min-width:0}
.cost{display:grid;grid-template-columns:minmax(130px,200px) 1fr 1fr;gap:8px 22px;align-items:center;padding:10px 0;border-top:1px solid var(--ln)}
.cb{display:flex;align-items:center;gap:10px;font-size:13.5px;white-space:nowrap}
.cb i{display:block;height:10px;border-radius:99px;background:var(--ink);min-width:4px}
.cb .tk{background:var(--mu)}

.crumb{color:var(--mu);font-weight:600}
.foot{padding:8px clamp(14px,2vw,28px) 28px;max-width:1440px;margin:0 auto;font-size:13px;color:var(--mu)}
.seg-cut{border-top-color:var(--am)}
.seg-cut b{color:var(--am)}
.nb-cut{background:var(--ams);color:var(--am)}
.nb-no{background:var(--s2);color:var(--mu)}
.grid.sm i{width:20px;height:20px}
.tabs .off{display:flex;align-items:center;gap:8px;padding:14px 14px 12px;color:var(--mu);font-weight:600;border-bottom:3px solid transparent;opacity:.55}
"""

STYLE: Final = TOKENS_CSS + COMPONENTS_CSS
