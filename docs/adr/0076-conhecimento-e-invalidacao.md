# 0076. Conhecimento de produto e invalidação seletiva

- **Status:** Proposto
- **Data:** 2026-11-16

## Contexto e decisão

O conhecimento é dado auxiliar, não autorização. Nenhuma observação modifica carta, perfil aprovado, escopo, teto, janela ou política protegida. `knowledge.yml` contém `schema_version: 1`, `references` fixas para `target.yml`, `data-rules.yml` e `flows.yml`, `basis` com digests SHA-256 de `environment`, `authorization`, `accounts`, `planning`, `openapi`, `data_rules`, `flows` e `engine`, e cinco entradas: `account`, `data`, `flow`, `effect` e `authentication`.

Cada entrada tem `source` (`owner`, `contract` ou `observation`), `reason` (`references_existing_documents`), `state` (`proposed`, `validated` ou `review_required`), `valid_until` e `dependencies`. Não há campo de texto livre. O domínio exige as dependências mínimas da categoria e, para todas, planejamento e motor. A revisão compara cada dependência com as fontes atuais obtidas independentemente do arquivo; ausência do motor, estado pendente ou validade expirada exigem revisão. O efeito proposto não é aplicado e não afirma que houve observação remota.

Não se transfere token, cookie, credencial, resposta, ID de recurso ou gabarito. O diário de mutações não é exportável. A exportação de `knowledge.yml` requer validação estrutural e controle de vazamento; documentos de perfil e regras têm seus próprios controles. O reuso não dispensa novas sessões e recursos.

## Comandos e resultado

`hdast knowledge capture <produto>` confere perfil, aprovação, autorização, documentos e motor da pilha local; cria `knowledge.captured.yml` sem substituir ou ativar `knowledge.yml`, sem tocar o alvo e sem modificar aprovação. A pessoa que opera decide ativar a cópia. `hdast knowledge validate <produto>` e `hdast knowledge diff <produto>` consultam as fontes locais sem motor, de modo que o resultado informa `engine_status: unavailable` e não declara reutilização validada. Ambos retornam `product`, `entries` com categoria e razões, `reusable`, `classification` e `engine_status`. `capture` retorna `product`, `copy`, `activated` e `approval_changed`.

Os três comandos usam envelope JSON v1. Sucesso sai com 0; entrada ou documento inválido usa `CONFIG_ERROR`, saída 2; aprovação ou autorização recusada usa saída 3; erro do motor segue o erro externo existente. A leitura isolada não aprova o perfil. Perfis sem conhecimento mantêm o comportamento anterior.

Na execução, o repositório aprovado verifica vínculo e validade das categorias efetivamente utilizadas antes de o probe ler os documentos de perfil, dados e fluxos. Mudanças de permissões, escopo, teto, janela ou política protegida permanecem decisões humanas e não podem ser introduzidas por esse arquivo. A equivalência de detecção e a economia de retrabalho requerem prova separada.

## Limite da conferência de fontes

Depois de ler OpenAPI, regras e fluxos, o probe recarrega o perfil e revalida o conhecimento antes do envio. Mudança persistente entre as leituras é recusada, e os modelos já lidos seguem na execução. Uma mudança A para B e novamente para A durante as leituras não é detectada: a dupla verificação não é uma captura atômica das fontes.

A prova offline em dois processos usa motor, especificação e alvo falsos, com documentos de dados e fluxo em disco. Ela não prova detecção nas APIs do laboratório, não demonstra redução de retrabalho e não comprova observação de efeito.

## Captura explícita de observações por execução

`hdast knowledge capture PRODUTO --run RUNID` lê manifesto, probe e, quando existe, authz da mesma execução. Exige execução concluída não simulada, produto, perfil, arquivos e versão do motor correspondentes às fontes atuais. `probe.json` passa a registrar, apenas em operações 2xx, referências sanitizadas às regras efetivamente aplicadas e aos encadeamentos resolvidos; os recibos não guardam valores ou identificadores concretos. Os apelidos associados a operações 2xx indicam uso da conta configurada, não comprovam a identidade de quem está por trás dela. Regra ou fluxo sem recibo ficam propostos e o fluxo legado dos documentos permanece disponível.

Receitas de efeito só entram quando `authz.json` contém recibos de releitura verificada, com operação de escrita, leitura, conta e nomes de campos; escrita isolada não comprova efeito. O consumidor revalida validade e fontes, e o authz só pode aplicar receitas a candidatos do plano existente. Nenhuma receita concede autorização nova.

A captura guarda run_id e hashes de manifesto, probe e authz quando disponível. Os hashes permitem comparar arquivos, mas não autenticam autoria e não impedem forja local; a cópia em outro contexto não inclui os artefatos originais. Cada referência é confrontada com perfil e contrato atuais, e dados, respostas, tokens, cookies, credenciais e identificadores de recurso não são copiados. Recibos incompatíveis são recusados na captura; referências propostas não suprimem cobertura.
