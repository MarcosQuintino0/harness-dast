# 0096. Bloco attack da carta liga as capacidades da V1.12

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** [plano da V1.12](../arquivo/plans/2026-11-17-v1-12-mais-achados.md), passo F1; [ADR 0075](0075-ritmo-proxy-em-perfis-novos.md)

## Contexto

A V1.12 acrescenta capacidades que mudam o tráfego ao alvo ou o que se relata: retorno fora de banda (OAST), injeção em cabeçalhos e cookies, testes de limite de consumo, regras experimentais do ZAP e inventário de versões irmãs. Cada uma amplia o que o teste faz dentro do escopo já aprovado. Pela regra do projeto, nada que amplia o ataque nasce ligado nem é ligado pelo agente: só a carta assinada o liga, pela CLI (`init --from-letter`), como `scan.allow_upload_scan` ([ADR 0052](0052-multipart-no-probe-e-no-scan.md)), `authz.allow_writes` ([ADR 0038](0038-authz-padrao-no-run-e-escrita-pela-carta.md)) e `negative.allow_writes` ([ADR 0051](0051-valores-que-o-esquema-proibe.md)).

Além disso, o ritmo (`scan.pacing`) existe no perfil, mas a carta não o declara: o `init --from-letter` gera sempre o padrão `legacy`. Sem a chave na carta, a opção de ritmo nas rodadas cegas não tem efeito.

## Decisão

Vamos acrescentar à seção `attack` da carta estruturada seis chaves opcionais, todas desligadas quando ausentes, nulas ou `desconhecido`. O `init --from-letter` as transcreve para o perfil; nenhuma flag da CLI liga nada (flags só reduzem).

| Chave da carta | Vira no perfil | Quem pode ligar | Efeito |
| --- | --- | --- | --- |
| `attack.pacing` (`legacy` ou `proxy`) | `scan.pacing` (só se `proxy`) | `source: carta` ou `pessoa`, sem frase | Só o ritmo; não promove nada do ADR 0075 (padrão segue `legacy`) |
| `attack.inject_headers` | `scan.inject_headers: true` | `source: carta` com frase em `quote` | Injeção em cabeçalhos e cookies |
| `attack.oast` | `scan.oast: true` | `source: carta` com frase | Retorno fora de banda no servidor de retorno do laboratório |
| `attack.allow_rate_tests` | `extra_checks.allow_rate_tests: true` | `source: carta` com frase | Testes de limite de consumo, com teto |
| `attack.experimental_rules` | `extra_checks.experimental_rules: true` | `source: carta` com frase | Regras experimentais (alpha) do ZAP |
| `attack.inventory` | `extra_checks.inventory: true` | `source: carta` com frase | Inventário de versões irmãs e documentação exposta |

`extra_checks` é um bloco novo e opcional do perfil (modelo congelado, chave desconhecida ou tipo errado recusados). `inject_headers` e `oast` ficam em `scan`, por serem política da varredura. Os cinco booleanos aceitam só `true` ou `false` (o texto "sim" é recusado) e `true` sem origem `carta` e frase é a pendência `ATTACK_FLAG_NEEDS_LETTER`. Cada chave ligada gera o aviso `ATTACK_FLAG_AUTHORIZED` e uma linha destacada no resumo da aprovação humana.

**Impressão digital da aprovação.** O cálculo (`FINGERPRINT_VERSION` 2) não muda de versão. As chaves novas de `scan` entram só quando diferem do padrão, pela regra que já vale para as chaves aditivas do bloco. O bloco `extra_checks` entra como bloco de proteção próprio só quando difere do padrão, como `negative` ([ADR 0051](0051-valores-que-o-esquema-proibe.md)). Logo, um perfil que não usa nenhuma chave mantém exatamente a impressão digital e a aprovação de antes; ligar qualquer chave, ou mudar `scan.pacing` para `proxy`, muda a impressão digital e exige nova aprovação. Uma chave ligada à mão no perfil, sem a carta, cai nessa mesma regra: o perfil muda e a CLI recusa com `SCOPE_NOT_APPROVED` até uma pessoa aprovar.

Este ADR só cria as chaves, a transcrição e a impressão digital. As capacidades que as consomem (OAST, SSRF guiado, cabeçalhos, limites, regras experimentais, inventário) chegam nos passos F2 a F8 da V1.12, cada uma com seus testes. O ritmo já é consumido pela varredura existente (`scan_policy`).

## Alternativas consideradas

- **Flags de CLI para ligar as capacidades.** Rejeitado: flags só reduzem; ligar por flag deixaria o agente ampliar o ataque.
- **Tudo dentro de `scan`.** Rejeitado para limites de consumo e inventário, que não são varredura do ZAP; um bloco próprio deixa claro o que cada aprovação cobre.
- **Subir `FINGERPRINT_VERSION`.** Rejeitado: invalidaria todas as aprovações existentes sem necessidade; a regra "padrão fica de fora" já preserva as antigas.
- **Aceitar `pacing: proxy` só da carta com frase.** Rejeitado: o ritmo não amplia o ataque nem o escopo; a resposta da pessoa basta, como em `include_outcomes`. Continua exigindo aprovação, porque muda a impressão digital.

## Consequências

- A carta ganha seis campos opcionais e o perfil ganha `scan.inject_headers`, `scan.oast` e o bloco `extra_checks`; é mudança aditiva do schema do perfil v1 e da carta v1.
- Aprovações de perfis existentes continuam válidas. Quem ligar uma chave aprova de novo.
- Enquanto F2 a F8 não existem, as chaves são aceitas e entram na aprovação, mas nada as consome: ligá-las hoje não muda o tráfego.
- O resumo da aprovação e os avisos da carta precisam de uma linha por chave nova; capacidades futuras que mudem tráfego repetem este molde.
