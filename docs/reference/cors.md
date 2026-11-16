# Verificação CORS

O `authz` repete até cinco GETs provados pelo `probe`, usando uma origem inexistente sob `.invalid`, sem fazer pedidos a essa origem. O perfil pode ajustar `authz.cors_max_requests` de 0 a 10; zero desliga os envios. A verificação `cors` também pode ser selecionada ou desativada como as demais do `authz`.

Origem refletida com credenciais gera achado alto; curinga sem credenciais, baixo. Os achados são agrupados por classe de política, com a primeira operação como evidência. Um resultado sem achados não prova a segurança de outras operações ou origens. Detalhes e limites: [ADR 0063](../adr/0063-verificacao-cors.md).
