# Resultados e evidências de avaliações

Esta pasta preserva material detalhado de **laboratórios locais com dados sintéticos**: relatórios, perfis, auditorias, decisões públicas, chamadas de ferramentas e telemetria. Os resumos próprios para o comparador continuam em [../measurements](../measurements/README.md).

| Estudo | Situação | Entrada |
| --- | --- | --- |
| Clínica Piloto e VAmPI, 2026-11-15 a 16, V1.5.5 | Oito cenários dirigidos aprovados; BOLA, massa e CORS na Clínica; V3 comprovada e V4 não comprovada no VAmPI; sem rodada cega | [Medidas e limites](2026-11-15-v1-5-5-lab/README.md) |
| Clínica Piloto, 2026-11-14, Terra 6.1 medium, modo amplo | Tentativa técnica inicial; rodada cega interrompida antes da varredura; continuação assistida concluída | [Índice e resultados](2026-11-14-clinica-piloto-terra61-medium-wide/README.md) |
| Clínica Piloto, 2026-11-15, Claude Sonnet 5.5 medium, modo amplo, V1.5.1 | Rodada cega completa; nota zerada por um `docker images` do agente (8,02 sem a violação); mesmas falhas achadas que a V1.1 | [Índice e resultados](2026-11-15-clinica-piloto-sonnet55-medium-wide/README.md) |
| Clínica Piloto, 2026-11-15 (tarde), Claude Sonnet 5.5 medium, modo amplo, V1.5.2 e V1.5.3 | Três rodadas: login recusado (corrigido), modo seguro com alarmes entre médicos (corrigido) e modo vulnerável com **8 de 10 falhas, nota 9,16** | [Índice e resultados](2026-11-15-clinica-piloto-rodadas-da-tarde/README.md) |
| Clínica Piloto, 2026-11-15, V1.5.2 | Provas automatizadas de integração de contas, paginação e sinais; não é rodada cega | [Medidas e limites](2026-11-15-v1-5-2-lab/README.md) |
| Clínica Piloto, 2026-11-15, V1.5.3 | Prova de papéis compartilhados nos dois modos, com controle positivo entre pacientes; não é rodada cega | [Medidas e limites](2026-11-15-v1-5-3-lab/README.md) |
| V1.5.4, 2026-11-15 | Recálculo isolado da triagem: Terra 6,29 → 5,79; Sonnet 9,16 → 9,16 | [Método e notas](2026-11-15-v1-5-4/README.md) |
| Clínica Piloto, 2026-11-15, V1.5.4 | Login sintético nos dois modos e conflito com 11 dependências; três casos aprovados após corrigir uma asserção; não é rodada cega | [Medidas e limites](2026-11-15-v1-5-4-lab/README.md) |
| Sonnet 5.5, 2026-11-16, V1.9 e V1.9.1 | Oito rodadas cegas (Clinica e VAmPI): a V1.9 travou o proxy com approval_changed (3,5 e 3,4 na Clinica); a V1.9.1 chegou a 8,99 e 9,16 com 9 de 10 falhas; export-reuse recusado nas quatro iniciais | [Rodadas e limites](2026-11-16-sonnet55-v19/README.md) |

Cada estudo identifica o commit testado, as intervenções e as limitações de comparação. Não entram credenciais, arquivos de aprovação, estado privado do laboratório nem raciocínio interno privado do modelo. As cópias de evidências passam por verificação de segredos e trazem manifesto com SHA-256 e origem. `evals/` inteira é excluída pelo preparador de futuras cópias cegas.

Textos históricos de instruções e relatórios podem estar como `.md.txt`; scripts históricos, como `.py.txt`. São registros da execução, não instruções atuais nem módulos executáveis do projeto.
