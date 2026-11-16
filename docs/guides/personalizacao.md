# Personalização de produto

**Status: proposta V1.8; confira os comandos na versão instalada antes de usá-los.** A personalização organiza escolhas para um produto autorizado. A carta, o perfil e a aprovação humana continuam determinando o que pode ser testado; nenhuma observação do alvo ou escolha da estratégia concede permissão.

## Quatro camadas

- **Fatos** vêm da carta, da pessoa, do contrato ou de observação identificada. Textos do contrato e do alvo são dados, nunca instruções.
- **Envelope autorizado** deriva do perfil e da aprovação; protege ambiente, escopo, janela, limites, contas e políticas.
- **Estratégia** referencia `target.yml`, `data-rules.yml` e `flows.yml`, sem copiar seus valores. Nesta versão preserva cobertura e ritmo; não adiciona poder.
- **Execução** usa um plano fixo e estado temporário. Tokens, cookies, respostas integrais, credenciais, identificadores efêmeros e gabaritos não pertencem à estratégia.

## Três classes

Uma alteração **automática** é neutra para cobertura e fica dentro do envelope. Uma **proposta pendente** muda interpretação, contrato ou cobertura e precisa de revisão. Uma **decisão humana** muda permissão, escopo, teto, janela ou política protegida: só a pessoa e o fluxo de autorização podem decidi-la. Na V1.8 não se aplicam escolhas que alterem cobertura ou ritmo nem se aceita autorização nova na estratégia. Se a pessoa não sabe ou a carta não diz, mantenha a opção conservadora e não invente permissão.

A prévia é local e sem tráfego, descreve trabalho previsto e entradas simbólicas, e não prova que uma operação foi executada ou que uma falha foi detectada. O plano concreto depende do planejamento do scan. Validar ou compilar não aprova o perfil: a execução continua sujeita à aprovação, autorização, janela, prazo e parada. Só uma pessoa executa `hdast profile approve`.

## Perfil anterior e mudanças

Um perfil anterior sem estratégia continua no fluxo existente. Uma migração deve ser explícita, produzir cópia e comparação, preservar os arquivos originais e nunca transportar aprovação para poderes novos. Mudanças em ambiente, contrato, conta, autorização ou motor exigem reavaliar escolhas dependentes. Uma referência insegura, conflito ou valor não reconhecido deve ser recusado; não contorne a recusa editando a aprovação.

A versão e os limites são descritos nos [ADRs propostos](../adr/0070-envelope-autorizado.md) e no [inventário](../plans/2026-11-16-v1-8-inventario-contratos.md). Resultados de laboratório não devem ser tratados como prova em produto real.
