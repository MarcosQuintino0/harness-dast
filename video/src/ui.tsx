import React from "react";
import { loadFont as loadSans } from "@remotion/google-fonts/IBMPlexSans";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";

const sans = loadSans("normal", {
  weights: ["400", "500", "600", "700"],
  subsets: ["latin"],
});
const mono = loadMono("normal", {
  weights: ["400", "700"],
  subsets: ["latin"],
});

export const FONT_SANS = sans.fontFamily;
export const FONT_MONO = mono.fontFamily;

// Cores tiradas do painel do próprio hdast, para o vídeo parecer o produto.
export const COLORS = {
  background: "#0c0e13",
  surface: "#14171d",
  border: "#262b35",
  text: "#f2f4f8",
  muted: "#9aa3b2",
  green: "#6dd4a8",
  blue: "#8ab4ff",
  salmon: "#ff8a75",
  yellow: "#f2c66d",
};

const EASE_OUT = Easing.bezier(0.16, 1, 0.3, 1);

/** Progresso de 0 a 1 a partir de `start`, com desaceleração no fim. */
export const enter = (frame: number, start: number, duration = 18): number =>
  interpolate(frame, [start, start + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT,
  });

/** Estilo de entrada: aparece subindo alguns pixels. */
export const riseIn = (
  frame: number,
  start: number,
  distance = 28,
): React.CSSProperties => {
  const progress = enter(frame, start);
  return {
    opacity: progress,
    transform: `translateY(${(1 - progress) * distance}px)`,
  };
};

/**
 * Fundo da cena, com um corte suave no começo. A primeira cena usa
 * `fade={false}` para o quadro inicial do vídeo (a miniatura) não sair preto.
 */
export const Scene: React.FC<{
  readonly fade?: boolean;
  readonly children: React.ReactNode;
}> = ({ fade = true, children }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.background,
        color: COLORS.text,
        fontFamily: FONT_SANS,
        opacity: fade ? enter(frame, 0, 10) : 1,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

/** Legenda na base da tela. */
export const Caption: React.FC<{
  readonly start?: number;
  readonly end?: number;
  readonly children: React.ReactNode;
}> = ({ start = 0, end, children }) => {
  const frame = useCurrentFrame();
  const fadeOut =
    end === undefined
      ? 1
      : interpolate(frame, [end - 8, end], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
  const progress = enter(frame, start, 14);
  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 70,
      }}
    >
      <div
        style={{
          opacity: progress * fadeOut,
          transform: `translateY(${(1 - progress) * 20}px)`,
          backgroundColor: "rgba(12, 14, 19, 0.94)",
          border: `2px solid ${COLORS.border}`,
          borderRadius: 18,
          padding: "24px 44px",
          fontSize: 54,
          fontWeight: 500,
          lineHeight: 1.25,
          textAlign: "center",
          maxWidth: 1640,
        }}
      >
        {children}
      </div>
    </AbsoluteFill>
  );
};

/** Texto digitado caractere a caractere, com cursor. */
export const Typed: React.FC<{
  readonly text: string;
  readonly start: number;
  readonly charsPerFrame?: number;
  readonly cursorColor?: string;
}> = ({ text, start, charsPerFrame = 1, cursorColor = COLORS.text }) => {
  const frame = useCurrentFrame();
  const count = Math.max(
    0,
    Math.min(text.length, Math.floor((frame - start) * charsPerFrame)),
  );
  const done = count >= text.length;
  const cursorOn = !done || Math.floor(frame / 15) % 2 === 0;
  return (
    <span style={{ whiteSpace: "pre-wrap" }}>
      {text.slice(0, count)}
      <span
        style={{
          display: "inline-block",
          width: "0.55em",
          height: "1.05em",
          marginLeft: 2,
          verticalAlign: "text-bottom",
          backgroundColor: cursorOn && frame >= start ? cursorColor : "transparent",
        }}
      />
    </span>
  );
};

/** Janela de terminal simples. */
export const TerminalWindow: React.FC<{
  readonly title: string;
  readonly style?: React.CSSProperties;
  readonly children: React.ReactNode;
}> = ({ title, style, children }) => (
  <div
    style={{
      backgroundColor: COLORS.surface,
      border: `2px solid ${COLORS.border}`,
      borderRadius: 20,
      overflow: "hidden",
      fontFamily: FONT_MONO,
      ...style,
    }}
  >
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "18px 26px",
        borderBottom: `2px solid ${COLORS.border}`,
        color: COLORS.muted,
        fontSize: 26,
      }}
    >
      {[COLORS.salmon, COLORS.yellow, COLORS.green].map((color) => (
        <div
          key={color}
          style={{
            width: 16,
            height: 16,
            borderRadius: 8,
            backgroundColor: color,
            opacity: 0.8,
          }}
        />
      ))}
      <span style={{ marginLeft: 14 }}>{title}</span>
    </div>
    <div style={{ padding: "34px 40px" }}>{children}</div>
  </div>
);

/**
 * Tela do painel (1920x900 úteis) ocupando o quadro inteiro, com zoom lento
 * até o ponto de interesse. `shiftX`/`shiftY` são o deslocamento final em px.
 */
export const PanelShot: React.FC<{
  readonly file: string;
  readonly zoomTo: number;
  readonly shiftX: number;
  readonly shiftY: number;
  readonly duration: number;
  readonly dim?: number;
}> = ({ file, zoomTo, shiftX, shiftY, duration, dim = 1 }) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [0, duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.45, 0, 0.55, 1),
  });
  const scale = 1.2 + (zoomTo - 1.2) * progress;
  return (
    <AbsoluteFill style={{ opacity: dim }}>
      <div
        style={{
          width: 1920,
          height: 900,
          overflow: "hidden",
          transformOrigin: "50% 0%",
          transform: `translate(${shiftX * progress}px, ${shiftY * progress}px) scale(${scale})`,
        }}
      >
        <Img src={staticFile(file)} style={{ width: 1920, height: 1080 }} />
      </div>
    </AbsoluteFill>
  );
};
