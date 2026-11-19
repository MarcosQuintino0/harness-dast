# Trilha L da V1.12: prova inicial e limites

Registro de 2026-11-17, anterior ao fechamento da trilha. Não é aceite de versão.
Escopo: L1–L6 do [plano](../plans/2026-11-17-v1-12-mais-achados.md), sem funcionalidades F,
rodada cega, PR ou merge. ADRs [0094](../../decisoes/0094-crapi-na-pilha.md) e
[0095](../../decisoes/0095-retorno-oast-isolado.md) propostos; 0092 reservado.

## Prova real inicial de L1

`pytest -m integration tests/integration/test_lab_crapi.py`, no commit `4c721aa`,
sob criação exclusiva de `C:\harness-dast-artefatos\lab.lock` em 2026-11-17T03:18:40Z.
Os projetos `hdast-codex` e `hdast-crapi-codex` subiram; o cadastro de contas/veículos
terminou sem expor credenciais. A primeira chamada do `preflight` foi recusada pelo proxy
com `STACK_STALE` e motivo `approval_changed`. Não houve edição intencional das fontes;
o motivo exato não foi demonstrado. A vigia também usa esse motivo para falha ou atraso.
Nenhuma trava foi afrouxada, aprovação alterada ou componente reiniciado para ignorar a recusa.

- Pilha: `2026-11-17T03-18-53Z-crapi-744e`.
- Preflight: `2026-11-17T03-23-13Z-crapi-4dda`.
- `probe` e varredura não chegaram a rodar nesta tentativa.
- O `finally` executou `stack down`; `docker compose ls -a` devolveu `[]`, e a trava própria foi liberada.
- Evidências externas: `C:\harness-dast-artefatos\v1-12-lab\l1-proof.log`,
  `l1-proof-junit.xml`, `l1-topology.json` e `l1-compose-after.json`.

O suporte posterior acrescenta tempos, frescor e estado de aprovação por comandos de leitura,
topologia e remoção dos volumes observados. Isso ainda não prova que a segunda execução passou.

## Preparação offline e lacunas

`prepare --case crapi-foco --mode vulnerable --seed 7` criou a cópia em
`crapi-foco-dryrun-20261117-0327`: 53 exclusões e zero termos de vazamento.
`init --from-letter` gerou o perfil; `evals.runner approve` aprovou a pasta descartável
em 2026-11-17T03:28:28.920105+00:00; `profile approval` mostrou `approved` e nenhum bloco alterado.
O agente não executou `hdast profile approve` nem leu segredos do lacre.
Os 89 testes focados de caso/aprovação/nota passaram em 111,65 s.
Os seis desafios permanecem `detectable: false`, o orçamento de 900 s não é duração medida
e cabeçalho fica fora deste caso de alvo único.

OAST possui ponte interna de destino fixo, overlay do workshop e suporte que emite o retorno
do namespace do workshop, consulta evento/contador e exige `ENETUNREACH` para TEST-NET.
A prova real e a presença do complemento na imagem ainda precisam ser conferidas;
o código não liga regra de varredura nem prova detecção SSRF.

L3/L5 foi interrompida pelo provedor em 2026-11-17T03:08:38Z por “possible cybersecurity risk”.
O WIP está em `pilot-wip.patch` e `0092-wip.md`, fora da branch; nenhum contorno foi tentado.
A sessão externa `claude-pilot` adquiriu a trava em 03:25:05Z para L5; seu primeiro log
também registra `STACK_STALE`. Isso é evidência concorrente, não prova de causa ou aceite L5.
A segunda prova L1 e a prova OAST aguardavam essa trava neste registro.

## Imagens e verificação

A captura inicial de 53 registros está em `images-before.jsonl`. O chatbot de 1,5 GB já existia,
deixou de ser necessário e foi preservado. Nenhuma imagem foi removida nesta prova.
A tabela e o manifesto protegido ficam em [lab/README](../../../lab/README.md).
O ensaio do roteiro com o registro vazio e a captura real devolveu
`{"simulation": true, "commands": []}`, sem consultar Docker ou remover imagens.
Casos com candidatos usam IDs completos, validação de origem, proteção e uso antes de gerar comandos.

Gates finais, hashes e qualquer prova posterior devem ser consultados no diário externo
`C:\harness-dast-artefatos\v1-12-lab\diario-coordenador.md`; este registro preserva o que foi observado aqui.
