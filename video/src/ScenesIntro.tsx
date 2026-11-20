import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import {
  Caption,
  COLORS,
  FONT_MONO,
  riseIn,
  Scene,
  TerminalWindow,
  Typed,
} from "./ui";

const ENDPOINTS: ReadonlyArray<readonly [string, string]> = [
  ["GET", "/api/pacientes/busca"],
  ["POST", "/api/pacientes"],
  ["GET", "/api/medicos/{crm}"],
  ["GET", "/api/convenios/{codigo}"],
  ["POST", "/api/consultas"],
  ["GET", "/api/prontuarios/{id}"],
];

const METHOD_COLOR: Record<string, string> = {
  GET: COLORS.blue,
  POST: COLORS.green,
};

/** Cena 1: o Swagger e a pergunta. */
export const HookScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Scene>
      <AbsoluteFill
        style={{ flexDirection: "row", alignItems: "center", padding: "0 110px" }}
      >
        <div style={{ width: 780, fontFamily: FONT_MONO }}>
          <div
            style={{
              fontSize: 30,
              color: COLORS.muted,
              marginBottom: 26,
              ...riseIn(frame, 0),
            }}
          >
            openapi.json · Clínica Piloto
          </div>
          {ENDPOINTS.map(([method, path], index) => (
            <div
              key={path}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 22,
                padding: "18px 24px",
                marginBottom: 14,
                borderRadius: 14,
                border: `2px solid ${COLORS.border}`,
                backgroundColor: COLORS.surface,
                fontSize: 32,
                ...riseIn(frame, 4 + index * 5),
              }}
            >
              <span
                style={{
                  width: 96,
                  fontWeight: 700,
                  color: METHOD_COLOR[method],
                }}
              >
                {method}
              </span>
              <span>{path}</span>
            </div>
          ))}
        </div>
        <div style={{ flex: 1, paddingLeft: 100 }}>
          <div
            style={{
              fontSize: 104,
              fontWeight: 700,
              lineHeight: 1.08,
              letterSpacing: -2,
              ...riseIn(frame, 18),
            }}
          >
            Teste de segurança de API,
          </div>
          <div
            style={{
              fontSize: 104,
              fontWeight: 700,
              lineHeight: 1.08,
              letterSpacing: -2,
              marginTop: 24,
              color: COLORS.green,
              ...riseIn(frame, 50),
            }}
          >
            conduzido por um agente de IA.
          </div>
        </div>
      </AbsoluteFill>
    </Scene>
  );
};

const PROMPT =
  "/hdast:test-product teste a segurança da API da Clínica Piloto.\n" +
  "O Swagger está em ./openapi.json e as regras de negócio em ./regras.md";

/** Cena 2: o pedido no Claude Code. */
export const PromptScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Scene>
      <AbsoluteFill style={{ padding: "110px 130px 0" }}>
        <TerminalWindow title="claude code · plugin hdast">
          <div style={{ fontSize: 30, color: COLORS.muted, marginBottom: 30 }}>
            Ambiente de teste · dados sintéticos · escopo autorizado pelo dono
          </div>
          <div
            style={{
              border: `2px solid ${COLORS.blue}`,
              borderRadius: 14,
              padding: "30px 34px",
              fontSize: 40,
              lineHeight: 1.5,
              minHeight: 250,
            }}
          >
            <span style={{ color: COLORS.blue }}>{"> "}</span>
            <Typed text={PROMPT} start={14} charsPerFrame={1.15} />
          </div>
          <div
            style={{
              marginTop: 34,
              fontSize: 34,
              color: COLORS.green,
              ...riseIn(frame, 150, 12),
            }}
          >
            ● Carregando a skill test-product…
          </div>
        </TerminalWindow>
      </AbsoluteFill>
      <Caption start={20}>
        Sem decorar comando: você pede, o agente conduz.
      </Caption>
    </Scene>
  );
};

const AGENT_STEPS: ReadonlyArray<readonly [string, string]> = [
  ["Skill test-product", "ensina o passo a passo ao agente"],
  ["Swagger lido", "30 funções da API mapeadas"],
  ["Regras de negócio lidas", "quem pode ver e alterar o quê"],
  ["Plano de teste montado", "login, alcance, varredura e achados"],
];

/** Cena 3: o agente lê, planeja e espera a aprovação humana. */
export const PlanScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Scene>
      <AbsoluteFill
        style={{ flexDirection: "row", alignItems: "center", padding: "0 110px 150px" }}
      >
        <div style={{ width: 800 }}>
          <div
            style={{
              fontFamily: FONT_MONO,
              fontSize: 56,
              fontWeight: 700,
              color: COLORS.green,
              marginBottom: 18,
              ...riseIn(frame, 0),
            }}
          >
            hdast
          </div>
          <div
            style={{
              fontSize: 78,
              fontWeight: 700,
              lineHeight: 1.1,
              letterSpacing: -1.5,
              ...riseIn(frame, 4),
            }}
          >
            Uma CLI para agentes de IA operarem ferramentas de segurança.
          </div>
        </div>
        <div style={{ flex: 1, paddingLeft: 80 }}>
          {AGENT_STEPS.map(([title, detail], index) => (
            <div
              key={title}
              style={{
                display: "flex",
                gap: 24,
                alignItems: "flex-start",
                marginBottom: 30,
                ...riseIn(frame, 30 + index * 26),
              }}
            >
              <div
                style={{
                  marginTop: 16,
                  width: 22,
                  height: 22,
                  borderRadius: 11,
                  backgroundColor: COLORS.green,
                  flexShrink: 0,
                }}
              />
              <div>
                <div style={{ fontSize: 48, fontWeight: 600 }}>{title}</div>
                <div style={{ fontSize: 36, color: COLORS.muted, marginTop: 4 }}>
                  {detail}
                </div>
              </div>
            </div>
          ))}
          <div
            style={{
              marginTop: 10,
              padding: "22px 30px",
              borderRadius: 14,
              border: `2px solid ${COLORS.yellow}`,
              color: COLORS.yellow,
              fontSize: 40,
              fontWeight: 600,
              ...riseIn(frame, 140),
            }}
          >
            Aguardando você aprovar o escopo
          </div>
        </div>
      </AbsoluteFill>
      <Caption start={150}>
        O agente só age por comandos da CLI, depois que uma pessoa aprova.
      </Caption>
    </Scene>
  );
};
