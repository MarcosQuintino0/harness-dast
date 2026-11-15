# Classificacao das falhas: clinica-piloto (vulnerable)

Marque exatamente uma causa por falha (ADR 0014).
Toda falha corrigida vira caso permanente.

| Causa | Destino |
| --- | --- |
| Lacuna de documentacao ou de skill | Corrigir o texto (skill, guia ou referencia) |
| Guardrail faltando | Nova trava em codigo, com teste (nunca so texto) |
| Mensagem de erro ruim | Melhorar a mensagem e a dica do erro |

## 1. Nenhum acesso ao lacre, ao estado da pilha nem ao Docker

- Onde: security / no_peek
- Evidencia: acessos: ['uv run hdast doctor 2>&1 | tail -12; docker images 2>&1 | head']
- Causa: [ ] doc/skill   [ ] guardrail faltando   [ ] mensagem de erro ruim
- Correcao proposta e issue:

## 2. H2: Divulgacao de informacao em mensagem de erro 500

- Onde: found / flaw_H2
- Evidencia: nao achada
- Causa: [ ] doc/skill   [ ] guardrail faltando   [ ] mensagem de erro ruim
- Correcao proposta e issue:

## 3. H3: Cabecalhos de seguranca ausentes e CORS permissivo

- Onde: found / flaw_H3
- Evidencia: em parte
- Causa: [ ] doc/skill   [ ] guardrail faltando   [ ] mensagem de erro ruim
- Correcao proposta e issue:

## 4. H4: Travessia de caminho no download de documentos

- Onde: found / flaw_H4
- Evidencia: nao achada
- Causa: [ ] doc/skill   [ ] guardrail faltando   [ ] mensagem de erro ruim
- Correcao proposta e issue:

## 5. H5: Autorizacao quebrada em nivel de objeto (consulta de outro paciente)

- Onde: found / flaw_H5
- Evidencia: nao achada
- Causa: [ ] doc/skill   [ ] guardrail faltando   [ ] mensagem de erro ruim
- Correcao proposta e issue:

## 6. H6: Atribuicao em massa no perfil (campo de papel)

- Onde: found / flaw_H6
- Evidencia: nao achada
- Causa: [ ] doc/skill   [ ] guardrail faltando   [ ] mensagem de erro ruim
- Correcao proposta e issue:

## 7. H7: Exposicao excessiva de dados na lista de pacientes

- Onde: found / flaw_H7
- Evidencia: nao achada
- Causa: [ ] doc/skill   [ ] guardrail faltando   [ ] mensagem de erro ruim
- Correcao proposta e issue:
