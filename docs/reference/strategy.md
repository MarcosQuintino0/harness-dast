# Estratégia e prévia local

**Status:** comandos implementados na V1.8. A prévia descreve trabalho previsto e não prova cobertura executada ou detecção. Contexto e passos de cadastro: [guia de personalização](../guides/personalizacao.md). Contratos: [ADR 0071](../adr/0071-estrategia-versionada.md), [ADR 0072](../adr/0072-compilacao-sem-trafego.md) e [ADR 0074](../adr/0074-migracao-estrategia.md).

## Comandos e opções

```text
hdast [--json] strategy validate <produto> [--products-dir <pasta>]
hdast [--json] strategy diff <produto> [--products-dir <pasta>]
hdast [--json] strategy migrate <produto> [--output <nome>] [--products-dir <pasta>]
hdast [--json] strategy capture <produto> [--output <nome>] [--products-dir <pasta>]
hdast [--json] plan <produto> --dry-run [--products-dir <pasta>]
```

- `--json` é opção global, antes do comando; seleciona o envelope JSON versionado da CLI.
- `--products-dir <pasta>` escolhe a pasta de produtos para o comando; pode ser omitida quando configurada no ambiente.
- `--output <nome>` escolhe o nome da cópia: o padrão é `strategy.migrated.yml` na migração e `strategy.captured.yml` na captura. O nome segue `strategy.<nome>.yml`, com minúsculas, dígitos e hífen no trecho intermediário. Arquivo existente não é sobrescrito.
- `--dry-run` é obrigatório no comando `plan`; sem ele, a CLI retorna erro de configuração.
- `--help` mostra a ajuda da CLI ou do comando indicado.

`strategy validate` retorna presença e estado da estratégia, estado da aprovação e resumo do envelope derivado do perfil. `strategy diff` acrescenta alterações estruturais em relação ao perfil legado e a classificação `automatic` ou `pending`; não compara a cobertura item por item. Ambos são consultas locais, sem tráfego e sem exigir aprovação. O estado da estratégia não é aprovação do perfil.

`plan --dry-run` produz prévia local sem tráfego. A resposta inclui `executed: false` e `preview`, com operações, contas, dependências, entradas declaradas e política. `body_entries_complete: false` indica que as entradas do corpo são incompletas; `scope_check: template_only` limita a conferência ao modelo do caminho. O catálogo de regras do ZAP, a cobertura e o resultado efetivo do scan permanecem pendentes. Na consulta seca o motor não é consultado e uma escolha preenchida impede a compilação da prévia. Na execução ativa a versão do ZAP é consultada antes do primeiro pedido ao alvo: escolha válida e `basis` igual às fontes e ao motor observados pode seguir; divergência ou indisponibilidade recusa. Cleanup sem provedor de identidade recusa escolha preenchida. `choices: []` ou estratégia ausente não geram consulta adicional ao motor.

`strategy migrate` cria a cópia neutra sem alterar o perfil ou a aprovação e sem ativar a estratégia. Uma estratégia já existente impede a migração. Revise a cópia antes de ativá-la explicitamente como `strategy.yml`. O comando devolve `copy`, `changes`, `classification` e `approval_changed` no resultado.

`strategy capture` cria uma cópia vinculada ao contexto atual: exige perfil formal aprovado e vigente, pilha gerenciada ativa do mesmo produto e estado, execução e endpoint coerentes, sem `KILL`. Sob `stack.lock`, usa somente o endpoint local e a chave publicados pela pilha, ignorando override de URL; recusa controle fora do loopback ou na mesma porta do alvo local. Consulta somente a versão do controle ZAP, sem enviar pedido ao alvo, e revalida perfil, aprovação e documentos depois. Pilha ocupada retorna `STACK_BUSY`, saída 8. Não usa execução antiga.

Aceita estratégia ausente ou com `choices: []`; escolha existente preenchida é recusada. Produz `strategy.captured.yml` com escolha `coverage/preserve`, origem `observation`, validade limitada à autorização e `basis` atual. A cópia é exclusiva e não é ativada nem sobrescreve estratégia; reveja-a e ative-a explicitamente se desejar. Em JSON de sucesso, `data` contém `product`, `copy`, `changes: ["strategy_bound"]`, `classification: "automatic"`, `approval_changed: false` e `activated: false`. Capturar não altera o perfil ou a aprovação; não é preciso repetir uma aprovação cujo fingerprint continua igual. A captura não concede permissão.

Uma estratégia mínima usa `schema_version: 1`, referências a `target.yml`, `data-rules.yml` e `flows.yml`, e `choices: []`. A escolha opcional de preservação de cobertura tem campos tipados e não autoriza novo escopo, mudança de ritmo ou redução de cobertura. A escolha aceita `basis` com resumos SHA-256 de `environment`, `authorization`, `accounts`, `planning`, `openapi`, `data_rules`, `flows` e `engine`. Para escolha preenchida, `validate` e `diff` retornam `strategy_state: review_required`, `basis_status: engine_unavailable` e `basis_context` com `engine: null`. O vínculo completo é necessário para compilação; o estudo de reutilização V1.9 ainda não foi executado. Veja o formato no [guia](../guides/personalizacao.md) e os limites do [conhecimento](knowledge.md).

Com `--json`, sucesso usa `schema_version: 1`, `ok: true` e `data`, com saída 0. Entrada inválida, escolha não compilável ou destino recusado usam `CONFIG_ERROR`, saída 2. Consultar ou compilar não aprova o produto: os comandos com tráfego continuam sujeitos à aprovação humana e às verificações de escopo. Para os demais erros, consulte [códigos de saída](exit-codes.md).

O controle e o scanner usam o mesmo endpoint configurado, sem prova de identidade criptográfica, do processo ou proteção contra reinício, proxy reverso ou alteração após a consulta. Preparar transporte usa perfil formal aprovado, sem aplicar a escolha nem enviar ao alvo. Na pilha gerenciada, mesmo sem escolhas de estratégia, uma vigia verifica por hash completo aprovação e perfil vinculados e verifica o arquivo de parada. Após verificação inicial síncrona, ela espera 50 ms após cada verificação antes de iniciar outra; a duração da E/S se soma à espera. Cada concessão consulta o estado publicado e verifica autorização, janela e prazo. Estado com mais de 200 ms desde o início da última verificação bem-sucedida, erro ou encerramento fecha e trava a saída; alteração detectada das fontes recusa com `approval_changed`. O limite de idade não garante prazo rígido para o sistema operacional ou sistema de arquivos revelar uma alteração. Uma concessão já encaminhada não é cancelada. A verificação pressupõe raízes dos diretórios montados estáveis: detecta substituição de arquivos dentro delas, não necessariamente a substituição do próprio diretório. Alterar ou renovar os arquivos vinculados exige recriar a pilha, mesmo quando o fingerprint continua válido e não exige nova aprovação. A coordenação também observou recusa após revogação na rodada 3, sem concessão posterior; a reprodução independente de T2 e revogação passou, com parecer global corrigir por lacuna de equivalência. Veja o [protocolo](../plans/2026-11-16-v1-8-rodada3.md).
