# Comparação T4 B da V1.8

As duas APIs excederam o limite pré-registrado de 10 pontos percentuais entre o ganho previsto e o observado. **Não promover `scan.pacing: proxy` no `init --from-letter`**. A previsão agregada V1.8 não altera a conclusão histórica da V1.7.

| API | T4 A (s) | T4 B (s) | Ganho previsto | Ganho observado | Erro |
| --- | ---: | ---: | ---: | ---: | ---: |
| Clínica Piloto | 619,491791 | 436,801836 | 45,086932% | 29,490295% | 15,596637 p.p. |
| VAmPI | 133,769327 | 82,231248 | 60,960393% | 38,527576% | 22,432817 p.p. |

O tempo é a diferença entre `scan.started_at` e `scan.finished_at`. A previsão, fontes e run IDs estão em `forecast-frozen.json`; as comparações completas estão em `t4-comparison-clinica-piloto.json` e `t4-comparison-vampi.json`. São arquivos derivados sanitizados: identificam os arquivos externos por caminho e SHA-256 e não incluem auditoria bruta ou respostas. A matriz por operação/regra contém também contagens iguais, diferenças, estados, tempos e valores ausentes; não transforma ausência em zero.

Nas duas APIs, as operações e desfechos registrados, as operações puladas e as matrizes de regras coincidem, excluindo somente DOM XSS 40026, historicamente pulada e sem prova de navegador. A Clínica apresenta 1.204 pares operação/regra e o VAmPI 430; pedidos e alertas por par coincidem, sem contagens ausentes. Isso não prova equivalência de pontos de injeção ou valores enviados, que não estão integralmente disponíveis.

Os achados por origem também coincidem nas chaves sanitizadas comparadas: Clínica, 98 ZAP, 4 authz e 0 negative em cada execução; VAmPI, 30 ZAP, 3 authz e 0 negative. Controles, contagens e estados de authz e negative registrados coincidem; seus detalhes e itens não testados estão nos JSONs. Comparação de achados por essas chaves não prova que toda evidência ou causa seja idêntica.

Escopo, limites de perfil e política são iguais. Os perfis mostram `legacy` em A e `proxy` em B, e o delay configurado passa de 20 para 0 ms; os demais limites de scan registrados coincidem. Os desfechos e aliases do probe coincidem. Na trilha de contas, a Clínica tem diferenças nas frequências de login, CSRF e saúde; no VAmPI, A registra uma decisão e um resultado de login de `user_a`, ausentes em B. A duração menor de B pode afetar renovações, mas os registros não demonstram essa causa e não provam troca de identidade.

O coletor observou cabeçalho `Authorization` em todas as mensagens do scanner nas duas variantes: 17.954/17.954 na Clínica e 4.272/4.272 no VAmPI. Na Clínica, as 5.036 escritas que passaram pela cerca tinham cabeçalho e cookie CSRF e nenhuma foi classificada como rejeitada por CSRF, em A e B. Os totais do VAmPI também coincidem, sem cabeçalho ou cookie CSRF identificados pelo coletor. Essas observações comprovam presença dos cabeçalhos segundo o coletor, não sua validade nem a identidade autenticada em cada pedido; o mesmo alias no manifesto e no probe tampouco a comprova. Nenhuma equivalência de identidade é declarada.

As contagens de pedidos e alertas podem oscilar entre execuções; diferenças não são descartadas automaticamente. Os testes T2 e a decisão global de qualidade são independentes desta análise. A comparação executada é de laboratório local e não prova comportamento em produto real.
