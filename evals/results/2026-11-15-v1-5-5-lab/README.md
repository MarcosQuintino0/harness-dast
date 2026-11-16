# Laboratório da V1.5.5

Provas dirigidas entre 2026-11-15 e 2026-11-16, com dados sintéticos, ZAP e cerca reais.
Não são rodadas cegas nem varreduras completas. [Resumo redigido](summary.json) e
[manifesto SHA-256](manifest.json) preservam contagens e a origem dos arquivos utilizados.

| API | Modo | CORS: pedidos / achados | Horizontal + massa: pedidos / achados |
| --- | --- | --- | --- |
| Clínica Piloto | Vulnerável | 1 / 1 alto | 80 / 1 BOLA e 1 atribuição em massa |
| Clínica Piloto | Seguro | 1 / 0 | 78 / 0 |
| VAmPI | Vulnerável | 1 / 0 | 11 / 1 BOLA de leitura já provada pelo probe |
| VAmPI | Seguro | 1 / 0 | 11 / 0 |

Oito cenários aprovados em dois blocos. As auditorias do proxy tiveram **422 requisições
liberadas, zero fora dos caminhos/métodos das cartas dos casos e nenhum DELETE**. Esse
verificador de auditoria não mede a taxa instantânea. As fixtures encerraram as pilhas;
`docker compose ls -a` devolveu `[]` no fechamento.

## O que foi demonstrado

- **Massa:** na Clínica, o probe leu o perfil como uma conta e escreveu como outra; as
  leituras de confirmação usaram a escritora. Houve um achado no vulnerável e nenhum no
  seguro. VAmPI executou oito candidatos em cada modo sem achado; V4 continua não provada.
- **CORS:** reflexão com credenciais somente na Clínica vulnerável. As outras três
  amostras não apresentaram as duas classes detectadas pela regra.
- **Par novo:** na Clínica, POST pela conta dona retornou 201; a dona leu o recurso novo
  com 200 e a outra conta recebeu 200 no vulnerável e 403 no seguro. Médicos continuaram
  excluídos por compartilhamento. O VAmPI respondeu 200 ao POST: `create_unconfirmed`, sem
  comparação desse recurso. Sua BOLA observada veio do GET já provado pelo probe.

O perfil descartável da Clínica declara o vínculo do identificador do próprio paciente
obtido no GET do perfil com o POST de consulta. A conta dessa leitura é a primeira do
papel na configuração de teste. Isso torna a referência válida para quem cria; o código
da ferramenta não conhece esses nomes nem presume posse. O alvo não foi modificado.
No VAmPI, a leitura pública de usuário é declarada pública no perfil do teste para não
confundi-la com o recurso privado de livro.

## Tentativas preservadas e limites

Arquivo externo: `C:\harness-dast-artefatos\v1.5.5\`.

1. `cors-lab.log`: quatro falhas após uma junção durante o uso da CLI; a pilha residual
   foi encerrada por `hdast stack down`. Essa tentativa não prova as verificações.
2. `integration-r2.log`: quatro CORS aprovados e uma falha em D (contador inicial alto e
   referências não preservadas). D foi corrigido com contador do probe e `flows.yml`.
3. `integration-r3.log`: uma falha em D por referência de outra conta no perfil do teste;
   os cinco POSTs receberam 403. A configuração foi corrigida sem alterar o alvo.
4. `integration-r4.log`: quatro casos de massa/par aprovados em **591,49 s**.

Os oito resultados públicos vêm dos quatro CORS de `lab-r2` e quatro massa/par de `lab-r4`.
As alterações posteriores de tradução de comando e preservação do leitor original da
escrita horizontal não alteram as verificações selecionadas nessas provas. Os arquivos
do manifesto permitem conferir exatamente os resultados usados.

`created_resources_reported` é o contador produzido pela CLI, não uma contagem independente
do banco. O novo par exige 201; a atribuição em massa mantém sua contagem de POSTs aceitos
por HTTP. Não se comprovou V4, economia de tokens, comportamento de um agente cego,
varredura completa, crAPI ou produto real. Nenhum estado privado, aprovação ou segredo foi
copiado para estas evidências.
