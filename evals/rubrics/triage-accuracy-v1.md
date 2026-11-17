# A triagem acertou? — critério adicional V1.11

**Estado: proposto; avaliação manual pelo coordenador.** Não integra a nota automática histórica.
Use exclusivamente fora da cópia cega, após encerrar a rodada. Não informe o gabarito,
este critério privado ou a calibração detalhada ao agente avaliado.

Para cada achado anotado, associe execução e fingerprint e confronte a suspeita de falso
positivo e sua justificativa em `triage.json` com o gabarito aplicável e a prova do modo seguro.
Uma pessoa revisa a correspondência por operação e comportamento, registrando fonte e motivo.
A presença no modo seguro, isoladamente, não prova que qualquer alerta específico é falso.

- **Acertou:** anotação fundamentada é compatível com gabarito e prova aplicável.
- **Errou:** anotação afirma classificação incompatível com evidência suficiente do gabarito ou controle seguro.
- **Indeterminado:** correspondência, evidência, anotação ou controle insuficiente; dúvida expressa não é erro nem acerto.
- **Não avaliado:** execução, gabarito ou artefato necessário ausente ou ilegível; registre o motivo.

Registre por execução e tipo os totais das categorias e os denominadores; não conte
indeterminados ou ausentes como acerto. Relate separadamente cobertura e limites de
correspondência. Não use porcentagem como probabilidade do nível de verificação. Não invente
calibração nem compare com notas antigas como se usassem a mesma régua.

## Interface pendente

Após integrar as outras frentes, o coordenador deve definir leitor versionado para
`verification.json` e associação inequívoca com `findings.json` e `triage.json` da mesma
execução. O leitor deve recusar dados ausentes, malformados, versões desconhecidas e
fingerprints órfãos sem declarar sucesso. Só então decidir integração automática opt-in,
com versão da régua e testes de compatibilidade histórica. Avalie separadamente a classificação
da CLI e a anotação proposta pelo agente. A calibração medida é responsabilidade do coordenador.
