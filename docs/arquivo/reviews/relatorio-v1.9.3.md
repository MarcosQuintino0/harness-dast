# Relatório da V1.9.3

Data: 2026-11-16. Branch `feat/v1-9-3-authz-dono`. Provada só no laboratório (Clínica Piloto e VAmPI); nada foi provado contra produto real, e nenhuma rodada cega nem varredura completa do ZAP foi feita nesta entrega.

## O problema

O `plan_horizontal` só repete pedidos que o `probe` já fez com sucesso, com a conta que o perfil escolheu. O perfil é otimizado para alcançar a API, e a conta que mais alcança (um papel compartilhado) é a que não serve para provar BOLA. Nas rodadas cegas da 1.5.3 à 1.9.2 o agente roteou as consultas ao médico compartilhado e a falha H5 da Clínica (um paciente lê a consulta de outro) nunca foi achada; a operação nem aparecia em `authz.json`, e a ausência de achado ficava invisível. A V3 do VAmPI (`/books/v1/{book_title}`) tem o mesmo desenho e também escapou. Orientar o agente nas skills não resolveu; a solução tinha de estar no código.

## A mudança ([ADR 0082](../../decisoes/0082-leitura-de-dono-no-teste-horizontal.md), proposto)

- **Domínio** (`authz_owner_ids.py`, `authz_owner_plan.py`): escolha determinística do par (primeiras duas contas do primeiro papel com par fora de `authz.shared_roles`; operação pública é excluída), validação do parâmetro (um marcador final escalar, sem outro parâmetro obrigatório), extração e validação de identidade, veredito e motivos.
- **Aplicação** (`authz_owner_read.py`): só `GET`, pelo `ReplaySender` e pelo envio guardado já existentes (cerca, `deny_paths`, limites, janela, prazo, stop, diário, pilha atual). Teto de dois objetos por operação e par. A conta dona precisa obter 2xx com o mesmo identificador; a outra conta repete; 401/403/404 protege, 2xx com o mesmo objeto é `authz_horizontal` alto, o resto é inconclusivo.
- **Fontes, em ordem:** coleção `GET` irmã da própria conta (array de objetos, consultada nas duas contas; interseção, repetição ou forma ambígua recusam), identificadores de alvos de `GET` de sucesso da conta, e o campo exato do parâmetro no corpo já redigido de uma criação de sucesso. Nada é adivinhado; nenhum valor novo é gravado (o corpo já constava, redigido, em `exchanges.json`).
- **Lacunas:** `owner_read_unsupported`, `owner_collection_missing`, `owner_collection_empty`, `owner_collection_unavailable`, além de `ambiguous_identifier`, `no_peer_account`, `public_operation`, `baseline_failed`, `inconclusive` e `budget_exhausted`, cada uma com a ação sugerida, em `authz.json`, `report.md`, `report.html` e na nova aba Autorização do painel (`authorization.html`). As lacunas horizontais não são cortadas pelo limite geral de linhas.
- **Sem mudança** no perfil, no envelope, nos códigos de saída nem na aprovação. `authz.allow_writes` continua mandando em toda escrita.

## Correções na revisão do trabalho do Codex

O código do Codex foi revisado contra o plano e o `CLAUDE.md`: sem nome de produto em `src/` ou `.claude/`, camadas e `lint-imports` íntegros, só `GET`, nenhuma identidade adivinhada. Ajustes: importação local em `evals/runner/metrics.py` movida para o topo; a ADR passou a tratar a privacidade do valor vindo do corpo enviado.

## Prova no laboratório

Teste: `tests/integration/test_v193_authz_owner.py` (perfil que imita o da rodada cega: consultas roteadas ao médico compartilhado, `shared_roles: [medico]`, dois pacientes; no VAmPI, `probe --only` na criação e `authz --check horizontal`). Sob a trava `lab.lock`. Saídas em `C:\harness-dast-artefatos\v1-9-3\fechamento\` (`clinica.log`, `vampi.log`, `metrics\`).

| Alvo e modo | `run_id` | Resultado |
|---|---|---|
| Clínica, vulnerável | `2026-11-16T23-16-21Z-clinica-piloto-9220` | `authz_horizontal` alto em `buscarConsulta` (H5); nenhum achado horizontal entre médicos (`shared_role`) |
| Clínica, seguro | `2026-11-16T23-19-33Z-clinica-piloto-7a1a` | **zero** achado de autorização |
| VAmPI, vulnerável | `2026-11-16T23-22-46Z-vampi-16a5` | `authz_horizontal` alto em `api_views.books.get_by_title` (V3) |
| VAmPI, seguro | `2026-11-16T23-23-35Z-vampi-df3a` | zero achado |

Os quatro passaram (Clínica 387 s, VAmPI 99 s). Lacunas aparecem no painel (`panel_has_gaps` verdadeiro nos quatro). O diário do estágio mostra só `GET` em `authz:owner:*`.

**Regressões** (`regressao.log`): `test_lab_authz.py`, `test_v19_authz.py` e `test_lab_v155.py`, nos dois modos; 41 passaram e 3 foram puladas por desenho (testes de um só modo), em 1776 s; nada regrediu (inclusive `shared_role` entre médicos e BOLA entre pacientes no vulnerável).

## V3 do VAmPI

Provada pela terceira fonte: o título que a própria conta enviou na criação consta, redigido, no `ExchangeRecord.body`. Como a criação não é legível pela conta (`create_not_readable` fica registrada como lacuna), o teste de dono usa o título para montar o `GET`.

## Limites e o que não foi provado

- Só laboratório; nenhum produto real, nenhuma rodada cega e nenhuma varredura completa do ZAP.
- Um marcador final escalar; caminhos aninhados, identificador no corpo de `GET`, coleção paginada em envelope e `DELETE` ficam fora (viram lacuna).
- Inventário prova visibilidade, não propriedade global; sucesso HTTP sozinho não prova propriedade, por isso exige identidade no corpo.
- A opção de ritmo para rodadas cegas foi retirada desta versão: ela gravava `scan.pacing: proxy` em `products/_template/target.yml`, que o `init --from-letter` ignora (o perfil vem da carta). Ligar o ritmo numa rodada cega pede a carta declarar o ritmo, num trabalho separado.
