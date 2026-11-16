# 0064. Par automático entre contas do mesmo papel

- **Status:** Proposto
- **Data:** 2026-11-15

## Contexto

O roteamento do probe pode não registrar leituras da conta de um papel não compartilhado. Comparar apenas os recursos já lidos pode deixar essa lacuna invisível.

## Decisão

Na verificação `horizontal`, com `authz.allow_writes`, para cada POST de negócio com JSON e GET irmão provados, tenta-se criar um recurso por papel com pelo menos duas contas não compartilhadas. O corpo é gerado pelo mesmo `RequestBuilder` e regras do perfil, com a etiqueta da execução e um contador inicial sorteado na metade superior; se o corpo coincide com o do probe, a criação é pulada. A primeira conta cria; o identificador deve vir do `Location` ou corpo da própria resposta, conforme o mecanismo de leitura já existente. O caminho concreto do pai do GET deve coincidir com o do POST. A conta criadora lê o recurso e só então a segunda conta lê o mesmo alvo. A cerca, janela e limites seguem vigentes. Nunca se envia DELETE.

Um corpo não vazio e equivalente nas duas leituras é achado horizontal; 401, 403 e 404 para a segunda conta são negações; outras respostas ou conteúdo diferente são inconclusivos. Operações públicas e papéis compartilhados são excluídos. Criações aceitas contam em `created_resources`, inclusive quando a confirmação posterior falha. O teto de 400 escritas é compartilhado com atribuição em massa; para atualizações reserva-se espaço para uma possível restauração. Recursos permanecem no ambiente para limpeza autorizada ou reset.

## Consequências e limites

Os motivos incluem `writes_not_authorized`, `shared_role`, `create_not_readable`, `new_data_unavailable`, `create_failed`, `created_identifier_unavailable`, `created_owner_read_failed`, `created_read_different`, `budget_exhausted`, além das recusas normais de escopo, conta e respostas inconclusivas. Um `2xx` sem identificador devolvido não permite comparar. O gerador não garante que regras constantes ou esquemas com campos únicos sem regra produzam um valor aceito; 409 não prova segurança. O contador usa a etiqueta do probe para compatibilidade com a limpeza, mas sorteios podem colidir em execuções repetidas e a aplicação pode rejeitar valores já existentes. Paradas respeitam o resultado parcial. A prova nos dois laboratórios permanece gate posterior.
