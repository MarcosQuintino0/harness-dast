# Spike do Nuclei no harness-dast

19 de novembro de 2026 · Branch `spike/nuclei`

**Avaliação estática parcial.** A evidência disponível é insuficiente para recomendar a adoção do Nuclei como segundo motor.

O censo identificou **14.101 modelos** no catálogo. **7.852** passaram pelos vetos estruturais e **1.436** tinham todos os pedidos de leitura representáveis como caminhos literais pelo analisador. Desses, o `ScopeGuard` aceitou o modelo inteiro para **53** na Clínica Piloto, **27** no VAmPI e **0** no crAPI. São contagens de modelos compatíveis com as regras dos perfis versionados. Cada um dos seis critérios de adoção que depende de execução ficou sem medição.

## Proveniência

Releases oficiais selecionadas pelo requisito de pelo menos 14 dias em 19 de novembro de 2026. O ZIP do catálogo foi lido diretamente, sem extração. A comparação do SHA-256 foi feita com o arquivo de checksums da mesma release.

| Insumo | Versão e data de publicação | SHA-256 | Verificação |
| --- | --- | --- | --- |
| Pacote oficial Linux amd64 | Nuclei v3.11.1, 2026-08-08 | `ea63d4ae232808cd7c6bc00d0142428e231fab59dae01042246097d195835ab6` | O hash dos bytes baixados coincide com o checksum publicado e com o digest do asset na API do GitHub. |
| Executável dentro do ZIP Linux amd64 | Nuclei v3.11.1 | `c49588140f357cbdddd5436dec11201953a4c5390faeec90777f9ee2cfd70251` | Hash calculado lendo a entrada do ZIP verificado. O executável não foi iniciado. |
| ZIP do catálogo | nuclei-templates v10.5.1, 2026-10-23 | `00184ad496302cd1dd3cf4b0b1c3aa45d6b35057f7bdf17e932318185ba0ac50` | O hash dos bytes baixados coincide com o checksum publicado. |

[Release do Nuclei v3.11.1](https://github.com/projectdiscovery/nuclei/releases/tag/v3.11.1) · [Checksums do Nuclei](https://github.com/projectdiscovery/nuclei/releases/download/v3.11.1/nuclei_3.11.1_checksums.txt) · [Release do catálogo v10.5.1](https://github.com/projectdiscovery/nuclei-templates/releases/tag/v10.5.1) · [Checksums do catálogo](https://github.com/projectdiscovery/nuclei-templates/releases/download/v10.5.1/nuclei-templates-10.5.1_checksums.txt)

## Censo estático

| Medida | Contagem |
| --- | ---: |
| Entradas YAML no ZIP | 14.148 |
| Modelos identificados por `id` e `info` | 14.101 |
| YAMLs legíveis sem esses dois campos | 31 |
| YAMLs que o leitor estrito não classificou | 16 |
| Modelos identificados com metadados inválidos | 1 |
| Modelos que receberam ao menos um veto, incluindo o de metadados inválidos | 6.249 |
| Modelos que passaram pelos vetos | 7.852 |
| Modelos com todos os pedidos de leitura representáveis estaticamente | 1.436 |
| Caminhos literais GET distintos na categoria de exposições, após os filtros por nome | 278 |

Os vetos se sobrepõem. O censo marcou 2.342 modelos por protocolo diferente de HTTP exclusivo, 3.663 por `raw`, 69 por presença de `unsafe`, 960 por `code`, 222 por `headless`, 643 por referência a `interactsh` e 287 por DAST ou fuzz. Por etiqueta foram 11 `dos`, 639 `intrusive`, 1 `bruteforce`, 37 `fuzz` e 2 `default-logins`. A presença do campo `unsafe` aciona o veto mesmo com valor falso. A detecção de OAST por texto também pode contar uma menção documental.

| Perfil | Modelos inteiros aceitos pelo `ScopeGuard` | Taxa configurada no perfil | Taxa observada |
| --- | ---: | ---: | --- |
| Clínica Piloto | 53 | 50 req/s | Não medida |
| VAmPI | 27 | 50 req/s | Não medida |
| crAPI | 0 | 50 req/s | Não medida |
| Alvo de pilha | Sem perfil analisado | — | Não medida |

A comparação usa o método e a URL resultante do caminho literal e da base do perfil. O modelo só entra na contagem se todos os seus pedidos projetados forem aceitos, com precedência de `deny_paths`. O analisador exclui da projeção expressões dinâmicas, caminhos com consulta, métodos de escrita e configurações adicionais de requisição além dos campos analisados. O resultado é um recorte conservador. O valor zero no crAPI se aplica ao recorte, e uma correspondência estática não comprova operação documentada no Swagger, aprovação de execução ou comportamento do motor.

O JSON registra arquivo, hash, protocolos, métodos, número de caminhos, flags e etiquetas. Os caminhos são computados em memória e o JSON contém apenas suas contagens. A função `census` mantém o cálculo do hash e a leitura no mesmo contexto de arquivo, e agrega os totais em uma passagem pelo ZIP. Os 278 caminhos da categoria de exposições excluem `heapdump`, `threaddump` e nomes associados a download ou arquivo volumoso. Volume real da resposta ficou sem medição. A lista literal operacional e as regras adicionais de escopo não foram geradas.

## 1. Ganho real

| Critério | Limiar do plano | Resultado |
| --- | --- | --- |
| Achados reais exclusivos do Nuclei, comparados com ZAP e inventário | Pelo menos 2 | Não medido |
| Achado exclusivo no alvo de pilha | Pelo menos 1 | Não medido |
| Actuator no serviço de identidade do crAPI | Confirmar em execução | A configuração de build da tag `v1.1.6-rc8`, usada pelo Compose do laboratório, não declara Actuator como dependência direta. Isso sugere que o serviço padrão não o oferece. A imagem e a exposição no serviço ficaram sem prova. [Build do serviço de identidade](https://github.com/OWASP/crAPI/blob/v1.1.6-rc8/services/identity/build.gradle.kts) |

## 2. Escopo

| Prova | Resultado |
| --- | --- |
| Pedidos emitidos nesta sessão contra os alvos do laboratório | 0. Nenhuma varredura foi iniciada. |
| Percentual de pedidos vistos na auditoria e tentativas fora da cerca | Não medido. O total observado não tem denominador de execução. |
| DNS na rede interna | Não medido |
| Impacto de `-max-host-error` em recusas da cerca | Não medido |
| Decisão da cerca com destino e `Host` divergentes | Não medida |
| HTTPS com a CA da cerca | Não medido |
| Bloqueio de redirecionamento para fora do escopo | Não medido |
| Telemetria, download de modelos ou rede externa no contêiner | Não medido |

## 3. Ruído

| Alvo | Falsos achados de severidade média ou maior | Limiar |
| --- | --- | ---: |
| VAmPI | Não medido | 0 |
| crAPI | Não medido | 0 |

## 4. Tempo

| Alvo | Acréscimo do Nuclei em LOW usando a taxa do perfil | Limiar |
| --- | --- | --- |
| Clínica Piloto | Não medido | Até 5 min |
| VAmPI | Não medido | Até 5 min |
| crAPI | Não medido | Até 5 min |
| Alvo de pilha | Não medido | Até 5 min |

## 5. Custo-benefício

| Comparação prevista | Resultado |
| --- | --- |
| Nuclei restrito ao Swagger | Não executado |
| Nuclei com a mesma base e exposições literais adicionais | Não executado |
| ZAP com 40034 e 40035 e a mesma lista literal | Não executado |
| Inventário do ADR 0102 nas mesmas condições | Não executado |

O ADR 0102 registra uma prova anterior com 21 pedidos e nenhum achado no crAPI, e uma com 4 pedidos e um achado baixo na Clínica Piloto em modo seguro. Esses dados são históricos e as condições da prova atual não foram reproduzidas. [ADR 0102](../decisoes/0102-inventario-de-versoes-e-documentacao.md)

## 6. Login

| Caminho ou evidência | Resultado |
| --- | --- |
| Injeção pelo Replacer do ZAP restrita à origem | O código existente monta a regra para a origem do alvo. A integração com o Nuclei ficou sem prova. |
| Ruído adicional no passivo do ZAP | Não medido |
| Arquivo de segredos em memória e somente leitura | Não ensaiado |
| Uso exclusivo de GET, HEAD e OPTIONS com conta | Sem ensaio com conta. O filtro de métodos vale para o recorte estático. |
| Token ausente de argumentos, logs e artefatos | Não verificado em execução. Nenhum token de conta foi materializado. |

Por desenho, o Replacer é a opção preliminar porque o segundo motor não precisa receber o token. A adoção desse caminho depende de verificar em execução o escopo da injeção, a retenção de dados e o ruído do passivo. [Código do Replacer](../../src/harness_dast/application/scan_tokens.py)

### Sanitização com dado sintético

Uma prova local montou um registro com um marcador sintético em `curl-command`, `request`, `response` e `extracted-results`. A projeção construiu um objeto novo com tipo conhecido e tamanho em bytes. A verificação confirmou que nenhuma das quatro chaves nem o marcador apareciam no JSON serializado.

```python
from typing import Literal


def summarize_secret(kind: Literal["bearer_token"], value: str) -> dict[str, str | int]:
    return {"secret_type": kind, "secret_length_bytes": len(value.encode("utf-8"))}
```

O JSON serializado continha dois campos.

```json
{"secret_type": "bearer_token", "secret_length_bytes": 19}
```

A prova cobre apenas a projeção final em memória. Não mede o tratamento da saída bruta, dos logs ou de credenciais durante uma execução do motor.

## Reprodução e limites

O comando do censo recebe o caminho do ZIP da tag, o SHA-256 e um caminho de saída novo.

```powershell
uv run python scripts/spike_nuclei_census.py $catalogo 00184ad496302cd1dd3cf4b0b1c3aa45d6b35057f7bdf17e932318185ba0ac50 $saida
```

O JSON gerado ficou em `C:/harness-dast-artefatos/nuclei-v10.5.1-census-2026-11-19-codex.json`. A inspeção usou os três `target.yml` versionados, sem resolver `secret_ref` ou criar aprovação descartável. A checagem de procedência usou `Invoke-RestMethod`, `Invoke-WebRequest` e `Get-FileHash -Algorithm SHA256` contra os releases públicos.

A consulta `docker info --format '{{.ServerVersion}}'` retornou código 1 nas duas tentativas. A conferência com `docker compose ls -a --format json` também retornou código 1, então a listagem ficou indisponível. O suporte de integração adquiriu e liberou a trava exclusiva nas consultas. Nenhuma pilha foi criada ou derrubada.

## Validação

O censo foi validado até o degrau 2 da escada de testes. [Escada de testes](../desenvolver/escada-de-testes.md)

| Comando | Resultado |
| --- | --- |
| `uv run ruff check .` | Passou |
| `uv run ruff format --check .` | Passou |
| `uv run mypy` e `uv run mypy --platform linux` | Passaram |
| `uv run lint-imports` | 6 contratos preservados |
| `uv run vulture` | Passou |
| `uv run pytest` | 12.528 passaram, 8 pulados e 334 desmarcados pelo filtro padrão, em 7 min 12 s |

O [censo](../../scripts/spike_nuclei_census.py), os [testes unitários](../../tests/unit/scripts/test_spike_nuclei_census.py), o JSON de metadados e este relatório compõem a entrega. O [changelog](../../CHANGELOG.md) registra o censo. A imagem, o override, um novo alvo de pilha e as provas de execução ficaram fora desta entrega.
