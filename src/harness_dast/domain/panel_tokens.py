"""Valores do `tokens.css` do desenho do painel (`docs/design/execution-panel/tokens.css`).

Cópia literal, embutida em toda página gerada. Um teste compara este texto com o arquivo do
desenho e falha se um divergir do outro: mudar um valor exige mudar os dois. Módulo puro.
"""

from typing import Final

TOKENS_CSS: Final = """/* Tokens do painel da execução (hdast). Fonte: docs/design/execution-panel/README.md.
   Um arquivo só, embutido em cada página gerada. Nenhuma tela escreve cor, espaço,
   canto, letra ou tempo direto: usa a variável. */

:root {
  /* espaço */
  --space-1: 4px;   --space-2: 6px;   --space-3: 8px;
  --space-4: 12px;  --space-5: 16px;  --space-6: 20px;
  --space-7: 22px;  --space-8: 28px;  --space-9: 48px;

  /* cantos */
  --radius-xs: 4px;  --radius-sm: 5px;  --radius-md: 8px;
  --radius-lg: 10px; --radius-xl: 12px; --radius-pill: 99px;

  /* letra */
  --font-sans: "Segoe UI", system-ui, -apple-system, Roboto, sans-serif;
  --font-mono: ui-monospace, "Cascadia Mono", Consolas, monospace;
  --text-title:   650 clamp(24px, 3vw, 34px)/1.18 var(--font-sans);
  --text-stat:    650 24px/1.15 var(--font-sans);
  --text-product: 700 20px/1.3 var(--font-sans);
  --text-section: 700 17px/1.4 var(--font-sans);
  --text-body:    400 15px/1.5 var(--font-sans);
  --text-panel:   700 14px/1.5 var(--font-sans);
  --text-support: 400 13.5px/1.5 var(--font-sans);
  --text-label:   700 13px/1.4 var(--font-sans);
  --text-example: 600 11.5px/1.4 var(--font-sans);
  --text-code:    400 13px/1.7 var(--font-mono);

  /* linhas e foco */
  --border-1: 1px;  --track-h: 6px;  --progress-h: 8px;  --stack-h: 16px;
  --focus-ring: 2px;  --focus-offset: 3px;

  /* movimento */
  --dur-fast: 120ms;  --dur-base: 400ms;  --dur-loop: 1.6s;  --dur-blink: 1s;
  --ease-out: cubic-bezier(.16, 1, .3, 1);

  /* tamanhos */
  --page-max: 1440px;  --hit-min: 44px;  --measure: 72ch;
}

/* Tema escuro: o principal. */
:root {
  color-scheme: dark;
  --color-bg: #0b0d10;
  --color-surface: #12161b;
  --color-surface-2: #1a2027;
  --color-terminal: #07090b;
  --color-border: #262d35;
  --color-text: #eceff2;
  --color-text-muted: #98a1ab;
  --color-live: #8fb8ff;
  --color-live-soft: #15233a;
  --color-ok: #6fd3a8;
  --color-ok-soft: #11281f;
  --color-danger: #ff8e7a;
  --color-danger-soft: #3a1c18;
  --color-warn: #e6b84a;
  --color-warn-soft: #33290f;
  --color-selection: #27405f;
}

/* Tema claro: segue o aparelho, a menos que a página force o escuro... */
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    color-scheme: light;
  --color-bg: #f1f3f6;
    --color-surface: #ffffff;
    --color-surface-2: #eef1f4;
    --color-terminal: #e6eaee;
    --color-border: #d5dbe1;
    --color-text: #14181c;
    --color-text-muted: #56606a;
    --color-live: #1d55b8;
    --color-live-soft: #e2ebfb;
    --color-ok: #0f6b47;
    --color-ok-soft: #dcf2e8;
    --color-danger: #b3261e;
    --color-danger-soft: #fbe6e3;
    --color-warn: #7a4b00;
    --color-warn-soft: #f8ecd2;
    --color-selection: #cfe0fb;
  }
}

/* ...ou é forçado por quem gera a página (data-theme="light" no <html>). */
:root[data-theme="light"] {
  color-scheme: light;
  --color-bg: #f1f3f6;
  --color-surface: #ffffff;
  --color-surface-2: #eef1f4;
  --color-terminal: #e6eaee;
  --color-border: #d5dbe1;
  --color-text: #14181c;
  --color-text-muted: #56606a;
  --color-live: #1d55b8;
  --color-live-soft: #e2ebfb;
  --color-ok: #0f6b47;
  --color-ok-soft: #dcf2e8;
  --color-danger: #b3261e;
  --color-danger-soft: #fbe6e3;
  --color-warn: #7a4b00;
  --color-warn-soft: #f8ecd2;
  --color-selection: #cfe0fb;
}

@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
"""
