# Provas da V1.5.4

Laboratório local, dados sintéticos, versão 1.5.4. Não é rodada cega nem varredura completa. O plano limita a integração aos itens A e C. As políticas novas são exercidas também por dois contratos sintéticos diferentes e por QA independente; nomes de produto nos JSONs abaixo identificam observações do laboratório.

- [Validação, gates e proveniência](validation.json).
- [Oito probes sanitizados](probe-observations.json): somente nomes, classes, códigos HTTP e contagens; nenhum corpo, credencial, estado ou arquivo de aprovação.
- [Recálculo isolado da triagem histórica](../2026-11-15-v1-5-4/README.md).

## Resultado da integração

Três casos aprovados: login sintético no modo vulnerável, login sintético no modo seguro e conflito com dependentes. A primeira execução completa teve dois aprovados e uma falha de asserção em 454,90 s. O reteste seguro passou em 194,78 s; somente ele foi repetido porque as demais provas já estavam verdes e a produção não mudou.

A asserção inicial exigia zero `auth_error`, embora o modo seguro deva negar uma operação protegida com 403. O QA conferiu os artefatos e o contrato, e a prova passou a verificar separadamente a recusa esperada do login e a preservação das recusas protegidas. Não houve correção na produção para satisfazer esse teste. Os resultados e logs de ambas as execuções foram preservados.

Nos probes normais há 41 operações, das quais dez são excluídas por desenho e 31 tentadas. O vulnerável teve 30 sucessos 2xx e uma recusa esperada, alcançando 31/31; o seguro teve 29 sucessos, uma recusa esperada e um `auth_error` protegido, alcançando 30/31. O conflito do produtor informou o campo na resposta e bloqueou 11 operações; essa contagem e o ranking constam do probe.

As imagens foram reconstruídas; a chave do ZAP foi gerada no processo pelo suporte compartilhado. Cada fixture executou `stack down`, com encerramento adicional do executor; `docker compose ls -a --format json` confirmou `[]`. Nenhum comando de aprovação humana, gravação de segredo ou limpeza foi executado.

Uma tentativa anterior foi interrompida antes da coleta final ao identificar suporte antigo com quatro contas para um perfil de cinco. A pilha residual foi encerrada pelo `hdast stack down` e o Compose conferido vazio. O suporte passou a usar `throwaway_pilot_env`; contagens históricas fixas foram substituídas pelo comportamento que o item A exige.

Saídas completas externas: `C:\harness-dast-artefatos\v1.5.4\`, em `gates/` e `integration/`. As pastas temporárias de execução contêm estado privado e não foram copiadas para este arquivo. O manifesto SHA-256 acompanha somente os resumos sanitizados.
