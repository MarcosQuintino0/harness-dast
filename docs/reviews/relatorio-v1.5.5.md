# Relatório da versão 1.5.5 — rascunho

Data: 2026-11-15. Branch: `feat/v1-5-5-achar-mais`. [Plano](../plans/2026-11-15-plano-v1-5-5-achar-mais.md). ADRs 0061 a 0064: Propostos. **Rascunho: implementação, integração, provas e revisão ainda em andamento.**

## Entrega e aceite

| Item | Mudança | Prova e situação |
| --- | --- | --- |
| A. Espera | `hdast wait`, ADR 0061 e skills | Testes e integração pendentes de consolidação |
| B. Atribuição em massa | Leitura pela conta que escreveu, ADR 0062 | Clínica Piloto e VAmPI: pendentes |
| C. CORS | Amostra limitada no `authz`, ADR 0063 | Clínica Piloto e VAmPI: pendentes |
| D. Par automático | Criação e leitura entre contas, com carta, ADR 0064 | Clínica Piloto e VAmPI: pendentes |
| E. Triagem | Conferência final nas skills | Contrato e revisão pendentes de consolidação |
| F. Avaliação | Casos e régua; histórico `vampi-estrito` | Testes, prepare e approve pendentes de consolidação; crAPI a confirmar |

## Decisões e limites

A saída 0 do `wait` confirma a consulta, não o sucesso da execução. CORS amostra GETs provados e cobre reflexão com credenciais e curinga sem credenciais; não cobre preflight. O par automático exige escrita autorizada, cria recursos novos e pula papéis compartilhados. As verificações respeitam a cerca e os limites do perfil.

## Qualidade e evidências

Gates completos, QA independente e provas direcionadas nas duas APIs: **pendentes**. Nenhuma rodada cega foi executada nesta versão; o dono poderá pedi-la depois em pelo menos duas APIs. Não há prova contra produto real. Resultados e limitações serão preenchidos após as execuções, sem inferir sucesso a partir deste rascunho.
