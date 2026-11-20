# Relatório da V1.11: verificação de achados

Data: 2026-11-17. Branch `feat/v1-11-verificacao`, candidata 1.11.0.
**Estado: implementação integrada e provada só no laboratório (Clínica Piloto e VAmPI); versão ainda não fechada.**
As fases 0, D e F foram executadas na retomada pelo Claude Code (seção 11); sem produto real, sem rodada cega, sem PR nem merge.

1. **Mudanças por fase.** A: envelope aditivo v1, regras puras offline e leitura
   estrita. B: declaração humana separada, aditiva, com TTY e confirmação digitada;
   agente não executa nem grava. C: `hdast confirm`, receitas fixas de GET com
   controle, recibo da semente e conta efetivamente varridas, prova parcial e causa
   de parada preservadas. Teto de 12 pedidos totais por achado, incluindo sessão,
   e 30 achados. E: painel e relatórios com nível/motivo, ataque/controle, lista que
   precisa de pessoa, declaração humana e calibração separadas; skills e critério
   privado de acerto da triagem sem mudar a nota histórica. Achados, severidade e
   status preservados. Fases 0/D/F operacionais pendentes.
2. **ADRs.** [0085 a 0091](../../decisoes/README.md#todas-as-decisões), todos Propostos:
   contrato; declaração humana; reprodução; apresentação/calibração; régua privada;
   vínculo da semente/prova/parada; observações passivas. Nenhuma dependência nova.
3. **Linha de base (fase 0).** Base `44ef387`, aprovações descartáveis do suporte
   de integração e pilhas locais. Clínica vulnerável `2026-11-17T05-02-42Z-clinica-piloto-80a9`
   (98 ZAP, 4 autorização, 29 sinais do proxy), Clínica segura `2026-11-17T05-24-04Z-clinica-piloto-ab47`
   (63 ZAP, 1 autorização) e VAmPI vulnerável `2026-11-17T05-35-12Z-vampi-1fd0` (30 ZAP,
   3 autorização, 4 sinais). Scan `completed` nas três, com cobertura parcial declarada;
   duas tentativas anteriores foram rejeitadas e preservadas (rede do wrapper e `STACK_STALE`).
   Lacunas do painel em [olhar de usuário](2026-11-17-painel-olhar-de-usuario.md); a inspeção
   visual por uma pessoa continua pendente.
4. **Calibração (fase D).** Cinco execuções completas com `hdast confirm` em todos os achados
   (retomada pelo Claude Code, seção 11). Matriz por tipo, amostras e limites em
   [calibração](../../referencia/verification-calibration.md); o JSON lido pelo relatório e pelo
   painel tem três linhas, todas com amostra abaixo de 10, então só contagens. Resumo: 11
   `reproduced`, todos de recibo de autorização (3 falhas plantadas, 2 médicos que compartilham
   pacientes sem `shared_roles`, 6 respostas sem login do VAmPI sem gabarito); 1 `inconclusive`
   (o único SQL elegível a receita ativa, `pacientes/busca`, falha plantada H1); o restante
   `not_verifiable`. Nenhum `likely` nem `likely_false_positive`: a capacidade de descartar
   falso positivo não foi exercitada.
5. **Prova (fase F).** Modo seguro da Clínica: nenhum `reproduced` falso quando a carta declara
   `shared_roles: [medico]` (execução `7ee5`: 63 achados do ZAP, zero de autorização, zero
   `reproduced`). Sem a declaração (execução `143c`) há 1 achado de autorização,
   `authz_horizontal` em `buscarPaciente` entre médicos, e a verificação o marca `reproduced`
   (seção 12). Modo vulnerável: as falhas reais que a receita alcança foram `reproduced` (CORS,
   campos fora do esquema e leitura entre pacientes, por recibo); SQL em consulta ficou
   `inconclusive`; SQL em caminho, travessia, hash e cabeçalho ficaram `not_verifiable`,
   nunca descartados. Também passaram os 4 testes de integração de autorização da V1.9.3
   (`tests/integration/test_authz_owner_lab.py`, Clínica e VAmPI nos dois modos). O roteiro
   `regressao_dirigida` não existe nesta branch.
6. **Validador.** Novo Terra medium em worktree própria: [parecer inicial corrigir](2026-11-17-v1-11-validacao.md)
   por JSON duplicado; `26c56b7` corrigiu. [Reteste: continuar](2026-11-17-v1-11-validacao-reteste.md)
   no escopo da correção, 37 testes e reprodução independente dos casos topo e
   aninhado recusados pelos dois leitores. Nenhum outro defeito concreto nessa
   revisão dirigida. Não é parecer de fechamento. O [QA Terra high](2026-11-17-v1-11-qa.md)
   tem [resposta por item](2026-11-17-v1-11-qa-resposta.md); a falta de prova real
   permanece aberta.
7. **Gates.** Retomada, SHA `1d8f02c`: ruff, format, mypy Windows e Linux, import-linter,
   vulture, pytest (10.474 aprovados, 5 pulados, 255 desmarcados), pisos (domain 98,0%,
   application 95,7%), diff-cover 94% e gitleaks sem achados, todos verdes, com o roteiro de gates
   do coordenador (manifesto `C:\harness-dast-artefatos\v1-11\gates-claude\manifest.json`,
   `all_passed: true`, fonte inalterada). Os números do coordenador anterior (SHA `719fdf5`,
   10.472 aprovados) seguem preservados em `gates-final`. A falha de memória do teste de
   descompressão que apareceu uma vez antes não voltou. CI remoto não executado.
8. **Commits e hash.** 49 commits do coordenador anterior sobre `44ef387` (hash final dele
   `719fdf5`, depois mais comprovantes de laboratório até `e79c5b0`) e, na retomada, `80929bb`
   (correção dos cabeçalhos repetidos) e `1d8f02c` (calibração, prova e relatório), mais o commit
   deste ajuste de gates. Sem PR, merge, force-push ou modificação de develop/main.
9. **Recusas.** Nenhuma recusa de cibersegurança do provedor nos programadores ou
   validadores. Retornos prematuros de propostas foram retomados. Houve bloqueio
   de computer use na inspeção do Edge; a interação foi encerrada sem contorno.
10. **Não feito ou provado.** Sem produto real, rodada cega, release, PR, merge ou CI remoto.
    Inspeção visual do painel por uma pessoa pendente. Amostras pequenas: nenhuma
    porcentagem. Receitas de tempo, de reflexão HTML e de erro detalhado nunca rodaram
    contra um achado real no laboratório; o único caso ativo foi inconclusivo. A recusa de
    falso positivo (`likely_false_positive`) não foi exercitada. Escrita, DELETE e travessia
    sem oráculo benigno são recusados. SQL temporal é específico de PostgreSQL; reflexão HTML
    não prova execução JS. `reproduced` por recibo de autorização confirma o fato observado,
    não a vulnerabilidade. Identidade da pessoa declarante não é autenticada. Execuções antigas
    sem recibo não ganham prova retroativa. Revisão humana das áreas críticas continua exigida
    pelo CONTRIBUTING.

Diário e evidências: `C:\harness-dast-artefatos\v1-11\diario-coordenador.md`.

## 11. Retomada pelo Claude Code (fases 0 verificada, D e F)

O coordenador anterior foi interrompido pelo filtro do provedor no meio da calibração. A retomada
usou o suporte de integração com aprovações descartáveis só no estado do teste (decisão do dono):
nenhum `profile approve`, nenhuma aprovação em `products/` ou no estado real, nenhum HTTP direto
ao alvo, nenhuma leitura de `.env`. Trava do laboratório exclusiva durante todo o trabalho,
pilhas locais derrubadas e `docker compose ls -a` vazio no fim.

| Execução (código) | run_id | Achados | Níveis |
| --- | --- | --- | --- |
| Clínica vulnerável (`e79c5b0`) | `2026-11-17T06-14-55Z-clinica-piloto-3454` | 131 | 4 reproduced, 1 inconclusive, 126 not_verifiable |
| Clínica segura (`e79c5b0`) | `2026-11-17T06-01-16Z-clinica-piloto-143c` | 64 | 1 reproduced, 63 not_verifiable |
| Clínica segura com `shared_roles` (`80929bb`) | `2026-11-17T06-39-37Z-clinica-piloto-7ee5` | 63 | 63 not_verifiable |
| VAmPI vulnerável (`e79c5b0`) | `2026-11-17T06-35-11Z-vampi-009c` | 37 | 3 reproduced, 34 not_verifiable |
| VAmPI seguro (`80929bb`) | `2026-11-17T06-53-13Z-vampi-050d` | 28 | 3 reproduced, 25 not_verifiable |

Em todas, `findings.json` ficou idêntico antes e depois das confirmações. O pedido de receita
mais caro foi o do SQL de `pacientes/busca`: 5 pedidos de receita, dentro do teto de 12. Uma
primeira tentativa do VAmPI foi invalidada porque uma segunda sequência de execução, iniciada
por engano, subiu pilha ao mesmo tempo (colisão de chave do ZAP); foi encerrada, as pilhas
foram derrubadas e as pastas ficaram em `claude/invalido-concorrencia`. As execuções válidas
são as da tabela, feitas em sequência. O candidato anterior do Codex (`1633`, Clínica vulnerável,
30 achados confirmados) tem o mesmo padrão (4 reproduced, 1 inconclusive) e a candidata segura
dele foi cortada antes de concluir.

## 12. O achado de autorização do modo seguro

É `authz_horizontal` em `GET /api/pacientes/{id}` (`buscarPaciente`): `medico_b` leu um paciente
de `medico_a` (200 e corpos equivalentes). **Não é defeito da ferramenta**: a carta do caso declara
que médicos compartilham pacientes, consultas e receitas, e o perfil do laboratório copiado sem
alteração não tem `authz.shared_roles` (só a carta o liga, ADR 0057). Com `shared_roles: [medico]`
no perfil (como a carta gera, e como já fazia a prova da V1.9.3), a execução segura `7ee5` teve
zero achados de autorização, `authz.not_tested` com `shared_role` nas comparações entre médicos e
nenhum `reproduced`. O mesmo achado aparece no modo vulnerável (`3454`).

Consequência para a verificação, e limite declarado: o `reproduced` de recibo de autorização
significa "a propriedade descrita foi observada", não "é vulnerabilidade". Sem a declaração
do perfil, a ferramenta não distingue compartilhamento permitido de falha. O texto do motivo diz que não
houve novo pedido; a decisão fica com a pessoa.

## 13. Defeito corrigido na retomada

Cabeçalhos registrados com nome repetido (`Vary`, `Set-Cookie`, como o Spring envia) tornavam a
evidência "indisponível" nos 30 alertas de `X-Content-Type-Options` da Clínica vulnerável. A
leitura agora junta só nomes repetíveis; os demais repetidos continuam recusados (teste
`test_cabecalho_repetivel_do_spring_nao_torna_a_evidencia_indisponivel` e par). O nível não muda
neste laboratório (a resposta é JSON): muda só o motivo. A execução medida é anterior à correção.

## 14. Painel para inspeção visual

Gerado com `hdast panel` (e `hdast report`, para a calibração aparecer) sobre a execução vulnerável:
`C:\harness-dast-artefatos\v1-11\claude\20261117-0300-clinica-piloto-vulnerable\runs\2026-11-17T06-14-55Z-clinica-piloto-3454\panel\findings.html` (comece por `summary.html`; a seção "Verificação dos achados" está em `findings.html`,
e o `report.html` fica na pasta da execução). Estão lá 131 verificações, a lista "precisa de uma
pessoa" (5) e a calibração em contagens.

## 15. Polimento do painel

Em 2026-11-17, os cartões de `findings.html` passaram a mostrar nível e motivo de verificação,
ataque e controle redigidos lado a lado quando disponíveis e declaração humana separada. O
índice usa nomes legíveis, gravidade em português e links para os cartões; os 131 detalhes de
verificação ficam recolhidos. CORS e campos fora do esquema descrevem sua própria técnica,
sem afirmar comparação entre contas. O recibo CORS atual não guarda o valor de `Origin`,
então a reprodução explica essa lacuna, sem inventar um pedido.

Regra sem receita recebe esse motivo antes da recusa por método. Os ADRs 0085–0091 exigem
motivo e recusas seguras, mas não fixam essa redação literal ou precedência; nenhum contrato
persistido mudou. Os motivos já gravados em `verification.json` continuam históricos: não
houve nova confirmação nem alteração dos níveis (126 não verificáveis, 1 inconclusivo e 4
reproduzidos), das severidades ou dos achados.

Painel e relatórios da execução `3454` regenerados por `hdast report` e `hdast panel`.
`summary.html` conserva a apresentação e os resultados (9 graves, 28 de 28 funções atacadas);
o diário inclui os comandos locais de regeneração. `report.md` e `report.html` conservam seus
renderizadores. Validação nos degraus 1 e 2, com regressões unitárias/de contrato, isolamento
da cópia cega e links; hashes e registros em
`C:\harness-dast-artefatos\v1-11\panel-polish-20261117`. A inspeção visual pelo Computer Use
foi bloqueada porque a ferramenta não conseguiu determinar a URL atual do Edge; a conferência
dos arquivos HTML foi estrutural. Sem pilha, tráfego ao alvo ou rodada cega nesta tarefa.
