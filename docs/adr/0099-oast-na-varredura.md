# 0099. OAST na varredura do ZAP

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** F2 da V1.12 ([plano](../plans/2026-11-17-v1-12-mais-achados.md)); [ADR 0095](0095-retorno-oast-isolado.md); [ADR 0096](0096-bloco-attack-da-carta-liga-capacidades-v1-12.md)

## Contexto

O ADR 0095 deixou pronta, só como infraestrutura, a ponte interna que leva um acesso do alvo ao serviço Callback do complemento OAST do ZAP. A carta liga `attack.oast`, que vira `scan.oast` no perfil (ADR 0096), mas nada o consumia. A política de varredura mantinha desligada, por padrão, a regra Log4Shell (40043), que só acha algo com retorno fora de banda.

## Decisão

Vamos consumir `scan.oast` na política de varredura (`domain/scan_policy.py`), sem mudar nada quando a chave está desligada:

- **Decisão no domínio.** `ScanPolicy` ganha `oast` e `oast_rules`. Com a chave, `OAST_RULES` (as regras da imagem fixada que usam o OAST) ficam ligadas e saem da lista de desligadas por padrão; um id citado em `scan.disable_rules` continua desligado (o dono do perfil sempre pode recusar). Sem a chave, a política é idêntica à de antes (teste de regressão em `tests/unit/domain/test_scan_policy_oast.py`).
- **Tradução no adaptador.** Só com a chave, `ZapScanClient.apply_policy` chama `oast/action/setCallbackOptions` (escuta em `0.0.0.0`, endereço anunciado `oast-gateway`, porta 8090, os valores do ADR 0095) e `oast/action/setActiveScanService` (`Callback`), liga as regras com `ascan/action/enableScanners` e confere que ficaram ligadas. Regra que não existe na imagem é ignorada com aviso. Sem a chave, nenhuma chamada `oast/*` é feita.
- **Regras da imagem** (`zap-stable` 2.17.0, `ascanrules` 84; ids lidos de `ascan/view/scanners` no ZAP real e conferidos nos pacotes da imagem): Log4Shell (40043), XML External Entity Attack (90023, usa o OAST quando há serviço ativo) e Server Side Template Injection (Blind) (90036). **Não existem na imagem** uma regra de SSRF (40046 fica no `ascanrulesBeta`, que não está instalado) nem de injeção de comando cega (só há `Remote OS Command Injection` por eco e por tempo, sem OAST). Esses dois casos ficam cobertos pelo SSRF guiado do [ADR 0100](0100-ssrf-guiado-pelo-contrato.md); instalar o `ascanrulesBeta` exigiria dependência nova e ADR próprio.
- **Isolamento preservado.** O ZAP continua só na rede interna e sai apenas pelo proxy de escopo. O retorno só chega pela ponte auditada do ADR 0095 (o ZAP não entra na rede do alvo nem o alvo ganha rota externa). Subir a ponte e ligar o workshop a ela segue sendo suporte do laboratório (`lab/oast/compose.yaml`, `lab/crapi/compose.oast.yaml`); esta decisão não muda a pilha de produto.
- **Contrato.** `scan.json` ganha `policy.oast` e `policy.oast_rules` (com padrão; arquivos antigos continuam válidos). O envelope, o schema do perfil e os códigos de saída não mudam.

## Alternativas consideradas

- **Ligar o OAST por padrão.** Descartado: induz o alvo a fazer uma requisição de saída; só a carta liga.
- **Instalar `ascanrulesBeta` para ter a regra de SSRF.** Descartado aqui: dependência nova, imagem maior e regra beta; o SSRF guiado pelo contrato cobre o caso com mais controle (ADR 0100).
- **Configurar o Callback no `stack up`.** Descartado: a escolha de usar retorno é da varredura (e da carta), não da pilha.

## Consequências

- Com a chave, Log4Shell, XXE e SSTI cega passam a ter retorno para confirmar; nenhuma delas foi provada contra uma falha real no laboratório (o crAPI não as planta). A prova desta versão é a política e o tráfego (ver ADR 0100 para o SSRF).
- O Callback fica configurado no ZAP até ele ser descartado com a pilha; a política da varredura é removida ao fim, como antes.
- O ZAP precisa conseguir resolver `oast-gateway`: sem a ponte de retorno no laboratório as regras apenas não confirmam nada.
