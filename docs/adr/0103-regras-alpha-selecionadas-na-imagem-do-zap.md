# 0103. Regras alpha e beta selecionadas na imagem do ZAP

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** [plano da V1.12](../plans/2026-11-17-v1-12-mais-achados.md), passo F7; [ADR 0096](0096-bloco-attack-da-carta-liga-capacidades-v1-12.md) (`attack.experimental_rules`); [ADR 0099](0099-oast-na-varredura.md) (a imagem não tinha regra de SSRF)

## Contexto

A imagem estável do ZAP (`zaproxy/zap-stable` 2.17.0) só traz as regras de varredura ativa estáveis (`ascanrules`). Faltam nela as regras de NoSQL para MongoDB (C12 do crAPI) e a de SSRF, que moram nos complementos `ascanrulesBeta` e `ascanrulesAlpha`. Esses complementos têm regras que o ZAP liga por padrão e que não foram escritas para API: ligá-los sem controle mudaria o tráfego e o ruído de toda varredura. Pela regra do projeto, o que amplia o ataque nasce desligado e só a carta liga. Além disso, nada pode ser baixado em tempo de execução: o ZAP não tem rota para fora.

Medimos a diferença com `ascan/view/scanners` nas duas imagens (contêineres sem rede): a estável tem 53 regras; com os dois complementos, 79. As 26 regras novas nascem todas ligadas. Não existe regra de SQLite por tempo na 2.17.0, nem na imagem derivada: as regras de SQL por tempo (MySQL, Hypersonic, Oracle, PostgreSQL, MsSQL) já são as estáveis.

## Decisão

Vamos criar uma imagem derivada e escolher, no `domain`, quais regras novas ficam ligadas.

1. **Imagem `hdast/zap:2.17.0-alpha54-beta64`** (`docker/zap/Dockerfile`): parte da `zap-stable` 2.17.0 já fixada por digest e acrescenta dois arquivos em `/zap/plugin`, baixados NO BUILD, por https, do release oficial do `zaproxy/zap-extensions` no GitHub e conferidos por SHA-256 fixado no próprio Dockerfile (o build falha se diferir):

   | Complemento | Versão | Arquivo | SHA-256 |
   | --- | --- | --- | --- |
   | `ascanrulesBeta` | 64 | `ascanrulesBeta-beta-64.zap` | `473987bfdede353167483d69ab4725b2509dd3c9a4b3426708dce1b26802e414` |
   | `ascanrulesAlpha` | 54 | `ascanrulesAlpha-alpha-54.zap` | `96299541c8f2a5ebc33c1aad89a635fc5b3de24c7d26b813ad5be43003674a1c` |

   As versões são as publicadas junto do ZAP 2.17.0 (2025-12-15); versões posteriores não foram avaliadas. O `compose.yaml` passa a ter `build:` no serviço `zap` e a tag `hdast/zap:2.17.0-alpha54-beta64`; o `hdast stack up` a constrói como já faz com o `scope-proxy`. A `zap-stable` continua sendo a base e continua protegida no inventário de imagens. Em execução nada é baixado.
2. **Lista fixa e versionada** (`domain/experimental_rules.py`): as 26 regras novas, com id, nome e qualidade. Só três são selecionadas: NoSQL Injection - MongoDB (40033, beta), NoSQL Injection - MongoDB por tempo (90039, beta) e Server Side Request Forgery (40046, beta, que só vale com retorno fora de banda e por isso só liga com `scan.oast`). Trocar a versão dos complementos exige reler a lista.
3. **Política.** `build_policy(config, experimental_rules=...)` recebe `extra_checks.experimental_rules` do perfil, que só a carta liga (ADR 0096). Desligada, as 26 regras ficam todas em `disabled_rules` e a política efetiva é a de antes (as mesmas 53 regras do ZAP estável ligadas, as mesmas desligadas). Ligada, só as selecionadas saem da lista de desligadas (e `scan.disable_rules` do perfil ainda pode recusar uma). O adaptador desliga as regras, liga as selecionadas com `enableScanners` e confere: regra ausente na imagem é erro com a dica de usar a imagem do harness (a estável não as tem), e regra que não ligou também.
4. **Marca de experimental.** Todo achado vindo de uma regra do catálogo sai com `experimental: true` em `findings.json` (campo aditivo; padrão `false`; não entra no fingerprint nem muda severidade). O relatório (`report.md` e `report.html`) mostra `[experimental]` na tabela, no detalhe e no grupo, e um aviso fixo; o painel mostra uma etiqueta "Experimental"; a seção de verificação também. `scan.json` ganha `policy.experimental_rules` (ids ligados) e as regras desligadas continuam em `policy.disabled_rules`, com nome e motivo nas métricas.
5. **Verificação (V1.11).** Os achados experimentais passam pela verificação como os demais. Não há receita segura para esses ids, então o nível é o que o domínio já dá: sem receita, `inconclusive`. Nenhuma receita nova foi escrita.

## Alternativas consideradas

- **Instalar os complementos em tempo de execução pelo marketplace do ZAP.** Rejeitado: exige saída para a internet, que o ZAP não tem por desenho, e não fixa versão nem SHA-256.
- **Ligar todo o conteúdo dos complementos beta e alpha com a chave.** Rejeitado: são 26 regras, várias sem sentido para API (divulgação de código-fonte, fixação de sessão, XSS fora de banda) e com histórico de ruído; a lista fixa é pequena e revisável.
- **Deixar as regras novas no estado padrão do ZAP quando a chave estiver desligada.** Rejeitado: ligaria 26 regras em toda varredura e quebraria a regra de que nada amplia o ataque sem a carta.
- **Filtrar os alertas depois da varredura.** Rejeitado: as regras ainda enviariam o tráfego. O controle é na política.
- **Um complemento por vez (só o beta).** Rejeitado: o beta traz as três regras úteis e o alpha só acrescenta três regras sem uso para API (LDAP, cache de web, entrada suspeita), mas o plano pede os dois; ficam instalados e desligados, listados no catálogo.

## Consequências

- Custo em disco: a camada nova tem 12 MB (os dois `.zap` têm 2,2 MB e o resto vem de `chown`/`chmod` no mesmo `RUN`); a imagem aparece com 3,77 GB como a base, com a qual compartilha camadas. A `zap-stable` continua no disco, porque é a base. A atualização exige trocar versão e SHA-256 no Dockerfile e a tag no `compose.yaml`.
- O primeiro `hdast stack up` precisa de internet para o build (como já precisa para as outras imagens). O `hdast doctor` avisa se a imagem não existe.
- Quem rodar a CLI contra a imagem estável com a chave desligada passa a receber erro de "regra desconhecida" ao desligar as 26 regras: a política do harness pressupõe a imagem do harness.
- O catálogo é de 26 regras medidas nesta versão dos complementos; uma versão nova pode trazer regras novas que ficariam ligadas por padrão no ZAP. A conferência da lista é parte da atualização da imagem (teste de contrato do fake lê as mesmas regras).
- A regra de SSRF 40046 passa a existir na imagem, o que muda a observação do ADR 0099 ("a imagem não tem regra de SSRF"); o SSRF guiado pelo contrato (ADR 0100) continua sendo o caminho principal e não depende da chave.

## Prova no laboratório

Pilhas com o sufixo `-sonnetalpha`, aprovações descartáveis do suporte de integração (`tests/integration/test_lab_experimental_rules.py`), nível rápido; medidas em `C:/harness-dast-artefatos/v1-12-f/f7-metrics`. Imagem construída duas vezes (a manual e a do `stack up`): `docker image inspect` dá 1,21 GB de conteúdo (3,77 GB no `docker images`), camada própria de 12 MB.

| Cenário | `run_id` | Duração (scan) | Resultado |
| --- | --- | --- | --- |
| crAPI, chave ligada, escopo mínimo (login, produtos e `POST /community/api/v2/coupon/validate-coupon`) | `2026-11-17T16-46-08Z-crapi-d197` | 29,5 s | 40033 (27 pedidos) e 90039 (42 pedidos) rodaram e concluíram, **sem alerta**: o C12 **não** foi achado (força LOW, limiar MEDIUM, uma execução; não tentamos força maior) |
| crAPI, chave desligada | `2026-11-17T16-50-06Z-crapi-416b` | 29,2 s | nenhuma regra experimental no `rule-stats.json` (0 pedidos), `policy.experimental_rules` vazio, 4 achados (os mesmos do cenário ligado) |
| Clínica Piloto, modo seguro, chave ligada (`probe` completo e `scan` de todas as operações) | `2026-11-17T16-52-36Z-clinica-piloto-b3de` | 592 s | 1383 pedidos das regras 40033 e 90039; **5 achados experimentais, todos alarmes falsos** (a Clínica usa Oracle, sem MongoDB; modo seguro sem a falha): 40033 em `criarConsulta`, `criarReceita` (2), `atualizarPaciente` e `atualizarConvenio`, todos com severidade proposta alta; 70 achados no total |

Leitura honesta: no laboratório a regra NoSQL deu cinco alarmes falsos de gravidade alta em uma varredura completa do modo seguro e nenhum acerto no C12. Por isso o alerta sai marcado e a chave só liga pela carta; os achados passam pela verificação da V1.11 sem receita e ficam `inconclusive`. A prova não mostra que a regra serve ao C12; mostra só o custo e o ruído. O gabarito do crAPI segue com o C12 como não esperado.
