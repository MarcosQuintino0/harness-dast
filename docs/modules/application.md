# Pacote `application`

Caminho: `src/harness_dast/application/`. Decisão: [ADR 0004](../adr/0004-portas-e-adaptadores-em-tres-camadas.md).

## Responsabilidade

Orquestrar um caso de uso por arquivo e declarar em `ports.py` as portas de que precisa. O caso de uso recebe as portas no construtor e usa o `domain` para decidir.

Portas previstas no desenho aprovado:

| Porta | Adaptador na V1 | Por que é porta |
| --- | --- | --- |
| `Scanner` | ZAP | Outros motores na V2; casos de uso testados com motor falso |
| `TargetClient` | `httpx` via proxy do ZAP | Ponto único onde o escopo é imposto; dublê nos testes |
| `SpecLoader` | Leitor de OpenAPI 3 | Swagger 2 e outras fontes depois |
| `SecretProvider` | Variáveis de ambiente | Cofre de segredos no CI depois |
| `ReportSink` | JSON e Markdown | SARIF, DefectDojo e Jira depois |
| `CleanupHook` | Script SQL do produto | Limpeza por API ou SQL conforme o produto |
| `RunStore` | Sistema de arquivos | Dublê em memória nos testes |
| `Clock` | Relógio do sistema | Janela de execução testável sem esperar |

Casos de uso previstos: `inspect_spec`, `preflight`, `probe_reachability`, `run_scan`, `build_report`, `cleanup`, `run_pipeline`.

## Pode importar

Somente `domain` (e a biblioteca padrão).

## Nunca deve

- Importar `adapters`, `cli` ou bibliotecas de terceiros de I/O.
- Importar `config` ou `observability` (o contrato do import-linter em `pyproject.toml` proíbe). Configuração e logger chegam aos casos de uso pelo construtor, via `cli`; como exatamente o logger chega ainda não está definido no desenho.
- Importar outro caso de uso. O que é comum desce para o `domain`.
- Decidir escopo, unicidade, severidade ou fingerprint: isso é do `domain`.
- Deixar passar exceção de terceiros. Os adaptadores traduzem na fronteira; o caso de uso só vê `HarnessError`.

## Convenções

- Porta é um `typing.Protocol`, declarada por quem a consome. Porta nova exige ADR.
- Docstring de porta descreve o contrato: o que garante, o que levanta, o que não faz.
- Piso de cobertura de ramos: 85% (veja [../testing.md](../testing.md)).

## Status

Implementado no M2 ([ADR 0015](../adr/0015-portas-do-perfil-e-carregador-de-yaml.md)):

| Módulo | Conteúdo |
| --- | --- |
| `ports.py` | `Clock`, `ProfileRepository` (`load`, `missing_files`) e `ProductScaffolder` (`scaffold`), mais os modelos `ReferencedFile` e `ScaffoldedProduct` usados nas assinaturas |
| `validate_profile.py` | `ValidateProfile`: carrega o perfil e devolve `ProfileReport` (resumo sem segredos, `runnable` e `issues`). Validade estrutural é erro (`ConfigError`); prontidão para executar é dado. Detecta os valores de exemplo do modelo (hosts `exemplo.com.br`, referência `SEC-0000`, segredos `MEU_PRODUTO_*`), arquivos referenciados ausentes, autorização vencida e janela fechada |
| `init_product.py` | `InitProduct`: cria a pasta do produto pela porta `ProductScaffolder` |

Implementado no M3 ([ADR 0018](../adr/0018-probe-httpx-csrf-criterio-de-sucesso-e-trilha-de-execucao.md)):

| Módulo | Conteúdo |
| --- | --- |
| `ports.py` (ampliado) | `Sleeper`, `EntropySource`, `ValueSourceFactory`, `SpecLoader`, `ProductDocuments`, `SecretProvider`, `SecretVault`, `TargetClient` (só aceita `ApprovedRequest`), `ZapControl`, `RunStore` |
| `inspect_spec.py`, `inspect_report.py` | `InspectSpec`: resumo e verificações cruzadas; modelos do resultado |
| `preflight.py`, `preflight_report.py`, `preflight_checks.py` | `Preflight`: verificações como dado (`scope` x `environment`); modelos e auxiliares |
| `probe.py` | `Probe`: orquestra leitura, plano, ZAP, sessão da conta, manifesto e resultado |
| `probe_runner.py`, `runner_settings.py` | O laço do `probe`: um passo nomeado por situação (pular, montar, simular, enviar, classificar) e as paradas antecipadas |
| `run_support.py` | `RunGate` (autorização, janela e prazo a cada requisição), `RateLimiter`, `AuditTrail` e `GuardedSender`, o único caminho de saída |
| `dispatcher.py` | `OperationDispatcher`: envia e repete conforme `domain.retry.next_action` |
| `account_session.py` | `AccountSession`: segredos, login (ou chave fixa), token CSRF; registra tudo no `SecretVault` |
| `preview.py` | Prévia do `--dry-run`: nomes de campos e geradores, nunca valores |

As portas `Scanner`, `ReportSink` e `CleanupHook` **ainda não existem** (M4 e M5).
