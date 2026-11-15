# Relatório da versão 1.5.3

Data: 2026-11-15. Branch: `feat/v1-5-3-papeis-compartilhados`. Plano: [V1.5.3](../plans/2026-11-15-plano-v1-5-3-papeis-compartilhados.md). Decisão: [ADR 0057](../adr/0057-papeis-compartilhados.md), **Proposto**.

Entrega: itens A a D implementados, QA independente, gates de qualidade e prova local nos dois modos. O PR é destinado à `develop`, sem merge pelo Codex. `domain/` e `application/` abaixo pertencem a `src/harness_dast/`.

## Entrega e aceite

| Item | Mudança e arquivos principais | Testes e prova |
| --- | --- | --- |
| A. Papéis compartilhados | **Feito.** Carta `attack.authz_shared_roles` gera `authz.shared_roles`; preenchimento exige origem e frase da carta. Planos horizontais registram `shared_role`. `domain/{authz_config,authz_plan,authz_plan_write,letter_shared_roles,letter_review,scope_fingerprint,scope_approval_summary,profile}.py`, `application/authz.py` e ADR 0057. | Unitários de domínio e aplicação, contrato `test_cli_init_letter_shared_roles.py` e três regressões independentes de QA passaram na suíte consolidada; laboratório comprova a omissão sem alarme entre médicos. |
| B. Avaliação | **Feito.** Carta da Clínica Piloto declara médicos compartilhados e pacientes isolados; caso esperado e régua conferem a supressão autorizada, preservando casos históricos. `evals/cases/clinica-piloto/` e `evals/runner/{models,checks_profile}.py`. | `tests/unit/evals/`, incluindo `prepare`, `approve`, recusa de supressão não autorizada e nota histórica, passou. Ensaio offline da CLI: 34 exclusões e zero termos do gabarito na cópia. Nenhum `hdast profile approve` foi executado. |
| C. Skills e dicas | **Feito.** Skills `onboard-product`, `fix-reachability`, `run-scan` e `triage-findings`, guias e referências orientam copiar a carta e alcançar leituras com pares de papel não compartilhado. `domain/spec_hints.py` evita recomendar papéis compartilhados. | Testes de dicas, links e contratos de skills passaram; efeito sobre um agente cego ainda não medido, fora da prova pedida pelo plano. |
| D. Laboratório | **Feito.** `tests/integration/test_lab_authz.py` declara `medico` compartilhado na cópia descartável, retira exceções de falso positivo e mantém controle positivo entre pacientes. | 33 testes passaram, 3 pulados por serem específicos do outro modo, em 863,92 s. Ambos os modos verdes; sem achado horizontal entre médicos; no vulnerável, BOLA entre pacientes preservado; no seguro, nenhum achado de autorização. |

## Qualidade e evidências

Saídas externas: `C:\harness-dast-artefatos\v1.5.3\`. [Resumos sanitizados, manifesto e validação](../../evals/results/2026-11-15-v1-5-3-lab/README.md) estão versionados. A conferência completa final sem filtro fica em `gates/pytest-final.log` na pasta externa.

| Gate | Resultado |
| --- | --- |
| Ruff | Lint e formatação sem problemas |
| Mypy Windows e Linux | 816 arquivos em cada plataforma |
| Import-linter | 6 contratos mantidos, nenhum afrouxado |
| Vulture | Sem código morto detectado |
| Gitleaks | Sem segredos nos commits examinados; configuração preservada |
| Auditoria do lock | Nenhuma vulnerabilidade conhecida encontrada |
| Pytest com cobertura | 9.283 passaram, 4 pulados, 167 desselecionados; 489,33 s |
| Cobertura de ramos | Domínio 98,4%; aplicação 97,2% |
| Cobertura do diff | 100% das 52 linhas executáveis alteradas, nenhuma ausente |
| Integração | 33 passaram, 3 pulados; 863,92 s; imagens reconstruídas nos dois modos e pilhas encerradas |

O authz enviou 165 pedidos no vulnerável e 157 no seguro, criou 10 recursos sintéticos em cada modo e registrou uma omissão de leitura e duas de escrita por `shared_role` em cada modo. No vulnerável houve um achado horizontal entre pacientes, um de exposição excessiva e um de atribuição em massa; no seguro não houve achado. A suíte conferiu cerca, ausência de DELETE, de erro de transporte e de segredos nos artefatos. Cada fixture executou `stack down`, e `docker compose ls -a` confirmou `[]` ao final.

O QA independente acrescentou três testes: lista reordenada de dois papéis mantém a aprovação; alteração posterior bloqueia o perfil e aponta só `authz`; o resumo legível mostra o papel compartilhado. Revisou o diff corrigido sem bloqueios de código. A revisão encontrou a precedência de `shared_role` sobre motivos estruturais: agora operação pública, corpo ou identificador ausente preservam seus motivos, com regressões. Um fixture novo das dicas usava nomes de referências em minúsculas e foi corrigido; não foi necessário alterar a validação. Dois textos com acentos corrompidos também foram corrigidos.

O mypy Linux apresentou erro interno quando executado simultaneamente ao mypy Windows; a repetição isolada passou. A causa da falha simultânea não foi comprovada, e nenhum gate foi afrouxado.

## Limites e revisão

- A declaração vale para todos os recursos do papel: o dono deve confirmar essa generalidade na carta. `shared_role` significa comparação não testada, sem comprovação de segurança.
- Não há dependência nova, técnica de ataque nova ou mudança de severidade. A lista vazia preserva a impressão digital anterior; a lista preenchida exige nova aprovação.
- O plano limita a prova ao degrau 3 do item D; não inclui `lab_full`, rodada cega nova ou produto real. Não foram executados `hdast profile approve`, `secret set`/`delete` nem limpeza.
- Nenhum item foi recusado ou limitado por regra do modelo. Os limites acima são de cobertura e do recorte de prova previsto no plano.
- Quatro subagentes GPT 6.1 Terra em worktrees próprias: núcleo e avaliação em high, documentação em medium e QA independente em high. O coordenador integrou e executou o laboratório. As worktrees e branches temporárias foram removidas após conferir os patches integrados. O checkout `C:\harness-dast` não foi utilizado.
- O Claude Code deve revisar o contrato, a declaração ampla por papel e as evidências, manter o ADR como Proposto até decisão do dono e cumprir a revisão humana dos módulos críticos prevista em `CONTRIBUTING.md` antes de juntar.
