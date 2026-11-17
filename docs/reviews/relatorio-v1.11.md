# Relatório do coordenador — V1.11

Data: 2026-11-17. Branch `feat/v1-11-verificacao`, candidata 1.11.0.
**Estado parcial: implementação integrada; versão não fechada.** O plano exige
provas operacionais que a falta de aprovação humana impediu executar.

1. **Mudanças por fase.** A: envelope aditivo v1, regras puras offline e leitura
   estrita. B: declaração humana separada, aditiva, com TTY e confirmação digitada;
   agente não executa nem grava. C: `hdast confirm`, receitas fixas de GET com
   controle, recibo da semente e conta efetivamente varridas, prova parcial e causa
   de parada preservadas. Teto de 12 pedidos totais por achado, incluindo sessão,
   e 30 achados. E: painel e relatórios com nível/motivo, ataque/controle, lista que
   precisa de pessoa, declaração humana e calibração separadas; skills e critério
   privado de acerto da triagem sem mudar a nota histórica. Achados, severidade e
   status preservados. Fases 0/D/F operacionais pendentes.
2. **ADRs.** [0085 a 0091](../adr/README.md#verificação-v111), todos Propostos:
   contrato; declaração humana; reprodução; apresentação/calibração; régua privada;
   vínculo da semente/prova/parada; observações passivas. Nenhuma dependência nova.
3. **Linha de base.** Base develop `44ef387`. Clínica vulnerável, Clínica segura e
   VAmPI vulnerável não iniciados: sem `run_id` e contagens. O [registro da fase 0](2026-11-17-painel-olhar-de-usuario.md)
   lista lacunas de prova, pedido, comparação, motivo, revisão humana e calibração,
   identificadas estaticamente. Fixture sintética offline não conta como execução
   ou inspeção visual operacional; a leitura do Edge foi bloqueada pelo computer use.
4. **Calibração.** [Fonte versionada](../reference/verification-calibration.md)
   em `blocked`, `measurements: []`. Não há matriz medida nem taxa de acerto.
   Contagem e amostra aparecem quando medidas; percentual exige pelo menos dez.
   A régua suplementar e o gabarito continuam fora da cópia cega.
5. **Laboratório.** Ambos os perfis locais retornaram `not_approved`. O roteiro
   `C:\harness-dast-artefatos\v1-11\aprovar-laboratorio.ps1` foi preparado para uma
   pessoa, com pergunta assíncrona pendente. O agente não executou aprovação
   nem gravou seu arquivo ou iniciou `run`/`confirm`, pilha ou limpeza operacional.
   Sem trava de laboratório adquirida, tráfego contra produto real ou rodada cega.
6. **Validador.** Novo Terra medium em worktree própria: [parecer inicial corrigir](2026-11-17-v1-11-validacao.md)
   por JSON duplicado; `26c56b7` corrigiu. [Reteste: continuar](2026-11-17-v1-11-validacao-reteste.md)
   no escopo da correção, 37 testes e reprodução independente dos casos topo e
   aninhado recusados pelos dois leitores. Nenhum outro defeito concreto nessa
   revisão dirigida. Não é parecer de fechamento. O [QA Terra high](2026-11-17-v1-11-qa.md)
   tem [resposta por item](2026-11-17-v1-11-qa-resposta.md); a falta de prova real
   permanece aberta.
7. **Gates.** No SHA `653dbac`, todos passaram: ruff, format, mypy Windows e Linux,
   import-linter, vulture, pytest (10.459 aprovados, 5 pulados, 252 desmarcados),
   pisos (domain 97,9%, application 95,7%), diff-cover 94% e gitleaks sem achados.
   Esses números antecedem a correção JSON. Após a correção, 37 focados,
   ruff/mypy/vulture passaram. Os comprovantes definitivos após esta documentação
   ficam em `C:\harness-dast-artefatos\v1-11\gates-final\manifest.json` e
   `windows-final\manifest.json`, com SHA e códigos de saída. Somente manifesto
   concluído com `all_passed: true` e fonte inalterada comprova o gate final;
   este registro não presume resultado futuro. CI remoto não executado.
8. **Commits e hash.** Commits pequenos por assunto, com coautoria, integrados
   por cherry-pick e enviados à branch. Código revisado em `26c56b7`; exemplos:
   `abcc580` (recibo), `90fde87` (confirmação/prova), `09c8f02` (HTML), `a37a7e4`
   (passivos), `6922c01` (teto total) e `26c56b7` (JSON estrito). Hash final,
   igualdade com a branch remota, gates e limpeza das worktrees próprias são
   registrados em `C:\harness-dast-artefatos\v1-11\entrega-final.json` e no diário.
   Sem PR, merge, force-push ou modificação de develop/main.
9. **Recusas.** Nenhuma recusa de cibersegurança do provedor nos programadores ou
   validadores. Retornos prematuros de propostas foram retomados. Houve bloqueio
   de computer use na inspeção do Edge; a interação foi encerrada sem contorno.
10. **Não feito ou provado.** Faltam aprovação humana, baseline com varredura,
    matriz e eficácia/ausência de reproduções no modo seguro, prova operacional
    e inspeção visual. Não houve integração/e2e Docker, CI remoto ou release.
    Escrita, DELETE e travessia sem oráculo benigno são recusados. SQL temporal é
    específico de PostgreSQL; reflexão HTML não prova execução JS. Resumos e
    digests não substituem inspeção integral da resposta. Identidade da pessoa
    declarante não é autenticada. Execuções antigas sem recibo não ganham prova
    retroativa. Revisão humana das áreas críticas continua exigida pelo CONTRIBUTING.

Diário e evidências: `C:\harness-dast-artefatos\v1-11\diario-coordenador.md`.
Para retomar os aceites operacionais, uma pessoa deve aprovar os perfis pelo roteiro
e então seguir a trava de laboratório e as fases 0/D/F do plano, registrando novas
provas datadas sem reescrever os pareceres preservados.
