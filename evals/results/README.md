# Resultados e evidências de avaliações

Esta pasta preserva material detalhado de **laboratórios locais com dados sintéticos**: relatórios, perfis, auditorias, decisões públicas, chamadas de ferramentas e telemetria. Os resumos próprios para o comparador continuam em [../measurements](../measurements/README.md).

| Estudo | Situação | Entrada |
| --- | --- | --- |
| Clínica Piloto, 2026-11-14, Terra 6.1 medium, modo amplo | Tentativa técnica inicial; rodada cega interrompida antes da varredura; continuação assistida concluída | [Índice e resultados](2026-11-14-clinica-piloto-terra61-medium-wide/README.md) |
| Clínica Piloto, 2026-11-15, Claude Sonnet 5.5 medium, modo amplo, V1.5.1 | Rodada cega completa; nota zerada por um `docker images` do agente (8,02 sem a violação); mesmas falhas achadas que a V1.1 | [Índice e resultados](2026-11-15-clinica-piloto-sonnet55-medium-wide/README.md) |
| Clínica Piloto, 2026-11-15, V1.5.2 | Provas automatizadas de integração de contas, paginação e sinais; não é rodada cega | [Medidas e limites](2026-11-15-v1-5-2-lab/README.md) |
| Clínica Piloto, 2026-11-15, V1.5.3 | Prova de papéis compartilhados nos dois modos, com controle positivo entre pacientes; não é rodada cega | [Medidas e limites](2026-11-15-v1-5-3-lab/README.md) |

Cada estudo identifica o commit testado, as intervenções e as limitações de comparação. Não entram credenciais, arquivos de aprovação, estado privado do laboratório nem raciocínio interno privado do modelo. As cópias de evidências passam por verificação de segredos e trazem manifesto com SHA-256 e origem. `evals/` inteira é excluída pelo preparador de futuras cópias cegas.

Textos históricos de instruções e relatórios podem estar como `.md.txt`; scripts históricos, como `.py.txt`. São registros da execução, não instruções atuais nem módulos executáveis do projeto.
