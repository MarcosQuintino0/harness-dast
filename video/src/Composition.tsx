import React from "react";
import { Composition, Series } from "remotion";
import {
  AttackScene,
  CloseScene,
  NucleiScene,
  ReportScene,
} from "./ScenesAttack";
import { HookScene, PlanScene, PromptScene } from "./ScenesIntro";

export const MyComposition = () => {
  return (
    <Composition
      id="Apresentacao"
      component={Apresentacao}
      durationInFrames={1320}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};

/** Vídeo de apresentação do hdast: sete cenas, 44 segundos. */
export const Apresentacao: React.FC = () => {
  return (
    <Series>
      <Series.Sequence name="1 Pergunta" durationInFrames={120}>
        <HookScene />
      </Series.Sequence>
      <Series.Sequence name="2 Pedido no Claude Code" durationInFrames={195}>
        <PromptScene />
      </Series.Sequence>
      <Series.Sequence name="3 Plano do agente" durationInFrames={210}>
        <PlanScene />
      </Series.Sequence>
      <Series.Sequence name="4 ZAP atacando" durationInFrames={315}>
        <AttackScene />
      </Series.Sequence>
      <Series.Sequence name="5 Nuclei" durationInFrames={150}>
        <NucleiScene />
      </Series.Sequence>
      <Series.Sequence name="6 Painel" durationInFrames={216}>
        <ReportScene />
      </Series.Sequence>
      <Series.Sequence name="7 Fechamento" durationInFrames={114}>
        <CloseScene />
      </Series.Sequence>
    </Series>
  );
};
