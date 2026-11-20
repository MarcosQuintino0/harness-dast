import React from "react";
import { AbsoluteFill, interpolate, Sequence, useCurrentFrame } from "remotion";
import {
  Caption,
  COLORS,
  enter,
  FONT_MONO,
  PanelShot,
  riseIn,
  Scene,
  TerminalWindow,
  Typed,
} from "./ui";

const FINDINGS: ReadonlyArray<readonly [string, string]> = [
  ["Injeção de SQL", "alguém lê o seu banco de dados pela URL"],
  ["Acesso entre contas", "um usuário vê os dados de outro"],
  ["Token falsificado", "a API aceita um login adulterado"],
  ["SSRF", "seu servidor é usado para ver a rede interna"],
  ["Sem limite de consumo", "dá para derrubar ou raspar a API"],
];

const CARDS_START = 100;

const FindingCards: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ padding: "70px 150px 0" }}>
      <div
        style={{
          fontSize: 44,
          color: COLORS.muted,
          fontWeight: 500,
          marginBottom: 28,
          ...riseIn(frame, 0),
        }}
      >
        O que o ZAP e o hdast procuram
      </div>
      {FINDINGS.map(([name, plain], index) => (
        <div
          key={name}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 30,
            padding: "24px 34px",
            marginBottom: 18,
            borderRadius: 18,
            border: `2px solid ${COLORS.border}`,
            backgroundColor: COLORS.surface,
            ...riseIn(frame, 10 + index * 30),
          }}
        >
          <div
            style={{
              width: 22,
              height: 22,
              transform: "rotate(45deg)",
              backgroundColor: COLORS.salmon,
              flexShrink: 0,
            }}
          />
          <div style={{ fontSize: 50, fontWeight: 700, width: 560 }}>{name}</div>
          <div style={{ fontSize: 40, color: COLORS.muted, flex: 1 }}>{plain}</div>
        </div>
      ))}
    </AbsoluteFill>
  );
};

/** Cena 4: a varredura ao vivo e o que ela procura. */
export const AttackScene: React.FC = () => {
  const frame = useCurrentFrame();
  const dim = interpolate(frame, [CARDS_START - 12, CARDS_START + 6], [1, 0.14], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <Scene>
      <PanelShot
        file="painel/live.png"
        zoomTo={1.48}
        shiftX={330}
        shiftY={-70}
        duration={CARDS_START}
        dim={dim}
      />
      <Caption start={12} end={CARDS_START - 6}>
        O <b style={{ color: COLORS.blue }}>ZAP</b> ataca cada função da API,
        sem sair do escopo aprovado.
      </Caption>
      <Sequence from={CARDS_START} layout="none">
        <FindingCards />
      </Sequence>
    </Scene>
  );
};

/** Cena 5: o Nuclei. */
export const NucleiScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Scene>
      <AbsoluteFill style={{ padding: "210px 150px 0" }}>
        <TerminalWindow title="hdast">
          <div style={{ fontSize: 44 }}>
            <span style={{ color: COLORS.green }}>$ </span>
            <Typed text="hdast nuclei clinica-piloto" start={8} charsPerFrame={0.9} />
          </div>
        </TerminalWindow>
        <div
          style={{
            marginTop: 70,
            fontSize: 84,
            fontWeight: 700,
            lineHeight: 1.12,
            letterSpacing: -1.5,
            ...riseIn(frame, 40),
          }}
        >
          E o <span style={{ color: COLORS.blue }}>Nuclei</span> completa:
          procura falhas já conhecidas e configurações expostas.
        </div>
        <div
          style={{
            marginTop: 30,
            fontSize: 44,
            color: COLORS.muted,
            ...riseIn(frame, 66),
          }}
        >
          Versões vulneráveis, arquivos e painéis esquecidos no ar.
        </div>
      </AbsoluteFill>
    </Scene>
  );
};

const REPORT_CUT = 96;

/** Cena 6: o painel com o resumo e a prova de uma falha. */
export const ReportScene: React.FC = () => {
  return (
    <Scene>
      <Sequence durationInFrames={REPORT_CUT} layout="none">
        <PanelShot
          file="real/summary.png"
          zoomTo={1.3}
          shiftX={110}
          shiftY={0}
          duration={REPORT_CUT}
        />
      </Sequence>
      <Sequence from={REPORT_CUT} layout="none">
        <PanelShot
          file="real/findings.png"
          zoomTo={1.42}
          shiftX={-150}
          shiftY={-30}
          duration={120}
        />
      </Sequence>
      <Caption start={10} end={REPORT_CUT}>
        No fim, o painel mostra o que foi testado e o que foi encontrado.
      </Caption>
      <Sequence from={REPORT_CUT} layout="none">
        <Caption start={8}>
          Cada falha vem com a prova e o passo a passo para repetir.
        </Caption>
      </Sequence>
    </Scene>
  );
};

/** Cena 7: fechamento. */
export const CloseScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Scene>
      <AbsoluteFill
        style={{ justifyContent: "center", alignItems: "center", textAlign: "center" }}
      >
        <div
          style={{
            fontFamily: FONT_MONO,
            fontSize: 170,
            fontWeight: 700,
            letterSpacing: -5,
            ...riseIn(frame, 0),
          }}
        >
          hdast
        </div>
        <div
          style={{
            marginTop: 20,
            fontSize: 58,
            fontWeight: 600,
            color: COLORS.green,
            ...riseIn(frame, 14),
          }}
        >
          Código aberto · Python, ZAP e Nuclei
        </div>
        <div
          style={{
            marginTop: 40,
            fontSize: 42,
            color: COLORS.muted,
            maxWidth: 1300,
            lineHeight: 1.35,
            ...riseIn(frame, 28),
          }}
        >
          Só em ambiente de teste, com autorização do dono do produto e dados
          sintéticos.
        </div>
        <div
          style={{
            marginTop: 54,
            fontFamily: FONT_MONO,
            fontSize: 40,
            opacity: enter(frame, 44),
          }}
        >
          github.com/MarcosQuintino0/harness-dast
        </div>
      </AbsoluteFill>
    </Scene>
  );
};
