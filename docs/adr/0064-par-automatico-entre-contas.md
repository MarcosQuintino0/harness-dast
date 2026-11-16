# 0064. Par automático entre contas do mesmo papel

- **Status:** Proposto
- **Data:** 2026-11-15

## Contexto

O roteamento do probe pode não registrar leituras da conta de um papel não compartilhado. Comparar apenas os recursos já lidos pode deixar essa lacuna invisível.

## Decisão

Na verificação `horizontal`, com `authz.allow_writes`, para cada POST de negócio com JSON e GET irmão provados, tenta-se criar um recurso por papel com pelo menos duas contas não compartilhadas. O corpo é gerado pelo mesmo `RequestBuilder` e regras do perfil, com a etiqueta da execução e um contador inicial sorteado na metade superior; se o corpo coincide com o do probe, a criação é pulada. A primeira conta cria; o identificador deve vir do `Location` ou corpo da própria resposta, conforme o mecanismo de leitura já existente. O caminho concreto do pai do GET deve coincidir com o do POST. A conta criadora lê o recurso e só então a segunda conta lê o mesmo alvo. A cerca, janela e limites seguem vigentes. Nunca se envia DELETE.

Um corpo não vazio e equivalente nas duas leituras é achado horizontal; 401, 403 e 404 para a segunda conta são negações; outras respostas ou conteúdo diferente são inconclusivos. Operações públicas e papéis compartilhados são excluídos. Criações com 201 e identificador não conhecido contam em `created_resources`, inclusive quando a leitura posterior falha; uma resposta 201 sem identificador também é contada. O teto de 400 escritas é compartilhado com atribuição em massa; para atualizações reserva-se espaço para uma possível restauração. Recursos permanecem no ambiente para limpeza autorizada ou reset.

Para comparar, exige-se HTTP 201 e sucesso conforme `probe.success`. Um identificador já presente em GET provado é recusado (`created_target_preexisting`). Outro 2xx é `create_unconfirmed`: pode ter criado um recurso, mas não conta como criação confirmada. Em ambos os casos não se executa a comparação; o aviso lembra que a operação pode ter deixado recurso. O código 201 e a ausência em `exchanges.json` não provam, contra um servidor incoerente, que o recurso não existia anteriormente.

Cada escrita sujeita ao teto, inclusive a restauração, tem no máximo uma tentativa: evita ultrapassar o orçamento quando o despachante repetiria após 401, 429 ou renovação de CSRF. Essas respostas podem deixar a verificação inconclusiva; não há retentativa automática dessas escritas.

## Consequências e limites

Os motivos incluem `writes_not_authorized`, `shared_role`, `create_not_readable`, `new_data_unavailable`, `create_failed`, `create_unconfirmed`, `created_target_preexisting`, `created_identifier_unavailable`, `created_owner_read_failed`, `created_read_different`, `budget_exhausted`, além das recusas normais de escopo, conta e respostas inconclusivas. APIs que criam com HTTP 200 não são cobertas por esta comparação automática. Sem identificador devolvido não se compara. O gerador não garante que regras constantes ou esquemas com campos únicos sem regra produzam um valor aceito; 409 não prova segurança. O contador usa a etiqueta do probe para compatibilidade com a limpeza, mas sorteios podem colidir em execuções repetidas e a aplicação pode rejeitar valores já existentes. Paradas respeitam o resultado parcial. A prova nos dois laboratórios permanece gate posterior.
