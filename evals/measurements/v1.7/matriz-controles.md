# Matriz dos controles: situação antes da prova V1.7

Nenhuma célula abaixo comprova resultado V1.7. Os exemplos de operação são mecanismos, não uma promessa de que cada classe exista em cada API. Testes de autorização e valores inválidos não verificam o efeito do ritmo no scanner ZAP; mantê-los como controles independentes. Registrar variante, modo, número de pedidos, regra concluída, achado e referência ao artefato em cada célula depois da execução.

| Classe | Clínica vulnerável | Clínica segura | VAmPI vulnerável | VAmPI seguro | Instrumento / lacuna |
| --- | --- | --- | --- | --- | --- |
| Injeção SQL | Pendente A/B | Pendente A/B | Pendente A/B | Pendente A/B | `test_v17_t2_sql`; regra 40018 e operação precisam estar concluídas. `pending` ou regra ausente é lacuna, não defeito de segurança. |
| Caminho/travessia | Pendente A/B | Pendente A/B | Sem controle conhecido | Sem controle conhecido | `test_v17_t2_path`: `baixarDocumento`, regra 6 e detecção H4; ainda não executado. |
| Autorização horizontal | Pendente | Pendente | Pendente | Pendente | `test_lab_v155.py`; confirmar qual operação/conta realmente foi comparada. Par novo VAmPI foi `create_unconfirmed` na V1.5.5. |
| Atribuição em massa | Pendente | Pendente | Lacuna histórica V4 | Lacuna histórica V4 | `test_lab_v155.py`; relatório V1.5.5 não comprovou V4 no VAmPI. Não transformar ausência de achado em equivalência. |
| CORS | Pendente | Pendente | Sem controle vulnerável conhecido | Pendente | `test_lab_cors.py`; VAmPI sem achado nos dois modos na V1.5.5. |
| Valores proibidos | Pendente | Pendente | Sem controle conhecido | Sem controle conhecido | `test_lab_negative.py` cobre Clínica; observar pedidos e restauração, não inferir detecção só pela conclusão do comando. |

Controles anteriores: [relatório V1.5.5](../../../docs/reviews/relatorio-v1.5.5.md). Se o baseline A não detectar a falha, registrar **lacuna da referência**, mesmo que B também não detecte. Ausência de resultado, classe, conta, regra ou prova em modo seguro é **inconclusivo** para esse critério. As linhas pendentes não são um aceite.
