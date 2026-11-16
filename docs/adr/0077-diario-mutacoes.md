# 0077. Diário de intenções de mutação

- **Status:** Proposto
- **Data:** 2026-11-16

## Decisão

Antes do envio de mutação, reservar chave estável derivada de produto, operação, conta e tipo, sem ID ou valor, e gravar intenção e classe do estado anterior (`absent`, `present`, `unknown`) em arquivo exclusivo. Sincronizar o arquivo antes de enviar; falha de criação ou sincronização impede envio. Registro existente, inclusive incompleto, bloqueia repetição. Depois de resultado conhecido, gravar e sincronizar resultado (`observed`, `succeeded` ou `failed`) e arquivar com identificador aleatório; só então outra tentativa pode ser reservada. Timeout, falha de comunicação ou queda após envio não são resultado conhecido e deixam pendência. Não guardar resposta, token, cookie, credencial ou ID. O diário é local e não exportável.

## Limites

O diário serializa pela chave conservadora, não identifica recurso individual; escritas distintas podem ficar bloqueadas juntas. A integração dos pontos de envio é requisito separado: o adaptador sozinho não protege mutações. A sincronização de conteúdo não garante durabilidade de metadados de diretório após perda abrupta de energia em todas as plataformas; a garantia de persistência precisa ser reforçada e provada no sistema de arquivos antes de afirmar recuperação contra essa falha. Não há mecanismo de reconciliação humana nesta alteração: pendência permanece bloqueada. Erros usam `CONFIG_ERROR`, saída 2.
