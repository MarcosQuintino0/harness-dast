# Reteste independente da constatação P2 — V1.11

**Parecer: continuar**, restrito à correção do P2 e à mudança revisada. O defeito reproduzido anteriormente está corrigido nos casos testados; não encontrei outro defeito concreto nesta revisão dirigida. Isso não é autorização para fechar a versão.

- SHA revisado: `382cc25df5dd29835a37dd922e38584553110693`, branch `chore/v1-11-validator`, árvore limpa. `git rev-parse HEAD^{tree}` e `git rev-parse 26c56b7^{tree}` retornaram ambos `6e6c36d09343914033739a4f2070b0f1f345ee0f`: árvore idêntica à integração `26c56b7`.
- Último commit: `fix(verification): recusar JSON ambíguo em todos os leitores`. Revisei a implementação de `domain/strict_json.py`, sua integração nos três leitores e os testes alterados. O parser rejeita chaves duplicadas em qualquer objeto e as constantes `NaN`, `Infinity` e `-Infinity`; converte erro de formato, codificação ou profundidade em `ConfigError` sem ecoar os dados. Os adaptadores mantêm erros seguros próprios.
- Reprodução independente por script efêmero em stdin e `TemporaryDirectory`: o envelope original com `schema_version` duplicado e uma entrada aninhada com `level` duplicado foram recusados por `VerificationStore.read()` e pelo leitor de apresentação: quatro `ConfigError` seguros. O conteúdo de cada arquivo temporário permaneceu intacto. Não houve escrita em arquivo operacional nem gravação humana.
- `uv run pytest -q tests/unit/domain/test_strict_json.py tests/unit/adapters/storage/test_verification_store.py tests/unit/adapters/storage/test_human_confirmation_store.py tests/unit/application/test_report_presentation.py`: **37 passaram**. Cobrem entradas válidas e malformadas, duplicidade no topo e aninhada, constantes não finitas, entrada não UTF-8 e profundidade excessiva, entre os demais testes dos arquivos selecionados.

## Limites

Sem subagentes, Docker, HTTP operacional, alvo, segredos, aprovações, limpeza, integração ou e2e. Não alterei fonte, testes, documentos ou o relatório inicial `validator-report.md`. Não repeti suíte completa ou gates finais; os números da execução consolidada anterior pertencem ao SHA `653dbac`, não a este SHA. O coordenador fará os gates finais após a última mudança. Nenhuma recusa do provedor nesta revisão.

As fases 0/D/F continuam bloqueadas externamente pela falta de aprovação humana (`not_approved`), sem execuções reais, run_id, contagens ou matriz de calibração; a inspeção visual operacional permanece sem prova. A aprovação só pode ser registrada por pessoa. A correção do P2 não resolve esses aceites nem permite declarar a V1.11 fechada.
