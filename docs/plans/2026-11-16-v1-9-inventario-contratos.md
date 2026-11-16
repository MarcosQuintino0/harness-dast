# Inventário de contratos da V1.9

Base conferida: `feat/v1-9-conhecimento`, derivada de `aec8cf8`. A versão mantém
as quatro camadas do plano: fatos e referências; envelope da carta/perfil aprovado;
proposta persistente; estado efêmero adquirido em cada execução.

| Contrato | Responsável | Persistência e fronteira |
| --- | --- | --- |
| Conhecimento versão 1 | `domain/knowledge.py` | Cinco categorias fechadas, fonte, justificativa, estado, validade e dependências; sem valores livres de resposta |
| Invalidação | `Knowledge.review`, `KnowledgeProfiles`, `InspectKnowledge` | Hashes calculados das fontes atuais; resultado por categoria. Sem motor atual não há reutilização validada |
| Referências executáveis | `target.yml`, `data-rules.yml`, `flows.yml` | Valores continuam em seus contratos originais; novo probe gera sessões e recursos novos |
| Captura | `CaptureKnowledge`, `FileKnowledgeStore` | Cópia exclusiva `knowledge.captured.yml`, sob trava da pilha; não ativa ou aprova |
| Diário | `MutationJournal`, `FileMutationJournal`, `mutation_key` | Estado privado `mutations/`, chave de produto/operação/conta/método, intenção e estado anterior antes do envio; nunca exportável |
| Envio de mutação | `GuardedSender`, `ReplaySender`, `NegativeSender`, `ScanRunner` | Sem retentativa automática mutante; falha/5xx mantém pendência. Scan registra lote, sem atestar cada efeito |
| Par criado | `authz_created_pair.py` | Identificador e marcadores só em memória; provas insuficientes viram motivo não testado |
| Exportação | `evals.runner.reuse`, `reuse_recipes` | Lista fechada, conteúdo canônico validado, segredo/vazamento, vínculo de origem e manifesto; destino recebe propostas |

Os comandos `knowledge capture`, `knowledge validate` e `knowledge diff` usam
envelope JSON v1. Sucesso 0; `CONFIG_ERROR` 2; escopo/aprovação 3; ferramenta externa
5; pilha ocupada 8. A captura não toca o alvo. O diário indisponível ou pendente
preserva resultado parcial do estágio, com motivo `mutation_outcome_unknown`.
Nenhum comando novo recupera ou repete mutação desconhecida.

Automática significa somente preservar referências válidas dentro do envelope.
Interpretação/efeito pendente permanece proposta. Permissão, escopo, teto, janela e
política protegida continuam decisão humana. Arquivo inválido, ausente quando
obrigatório ou malformado falha fechado. Sem conhecimento, o caminho legado segue
disponível; o diário adiciona a trava de repetição, não nova autoridade.

ADRs 0076–0080 permanecem Propostos. Os testes unitários e de contrato cobrem
entrada negativa, invalidação, corrida persistente, crash, segredo e cruzamento de
estágios. Prova offline, ensaio de exportação e integração assistida são distintos
do estudo cego, que não foi executado nesta versão.
