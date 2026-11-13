"""Lógica do proxy de escopo (camada 3 de AD-11), sem dependência do mitmproxy.

Responsabilidade: carregar e validar a política de uma execução, decidir se uma requisição
de saída pode passar (delegando ao `ScopeGuard`), limitar a taxa, aplicar a trava de
emergência e o prazo, e montar a trilha de auditoria. Tudo aqui é testável no host.
A cola com o mitmproxy fica em `docker/scope-proxy/addon.py`, dentro da imagem do proxy.
Não decide escopo por conta própria: só o `ScopeGuard` permite; este pacote só acrescenta
recusas (endereço resolvido, prazo, trava, taxa).
"""
