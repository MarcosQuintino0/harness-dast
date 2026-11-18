# 0026. A cerca enxerga melhor (motivo granular) e ganha um modo amplo de caminho

- **Status:** Proposto
- **Data:** 2026-11-13
- **Origem:** decisão do dono do projeto depois de três varreduras reais; altera o que os ADRs [0008](0008-escopo-em-tres-camadas.md) e [0024](0024-run-encadeado-trava-de-emergencia-e-oracle-na-pilha.md) assumiam sobre o proxy de escopo (eles seguem imutáveis; este os complementa)

## Contexto

Todo pedido do ZAP passa pelo proxy de escopo, que decide com o `ScopeGuard`. O guarda recusa qualquer caminho "ambíguo" (`%2f`, `;`, `..`, `%25`, `//`, ponto ou espaço final) para que ninguém contorne `scope.deny_paths` com uma forma que o servidor leia diferente do que o texto mostra. Medição em três varreduras reais: de 60% a 65% do tráfego do ZAP é recusado como `malformed_request`. Isso derruba justamente os ataques mais elaborados em segmento de caminho (injeção em caminho, travessia, desvio por `;`), e hoje o relatório não diz isso: só mostra um número agrupado.

Dois problemas, portanto:

1. **Não se enxerga o que se perde.** `classify` adivinha o motivo pelo prefixo da mensagem e tudo que vem da normalização vira `malformed_request`. A auditoria corta o caminho em 120 caracteres, o que impede reproduzir a decisão.
2. **A cerca é mais estreita do que a carta exige.** O dono aceitou um modo opcional, autorizado na carta, que afrouxa a liberação mas continua paranoico com os caminhos proibidos.

Também foi investigado o sufixo de formato: `deny_paths: /api/admin` **não** cobre `/api/admin.json` (a comparação é por segmento inteiro e `admin.json` é outro segmento), embora Spring e outros roteiem os dois para o mesmo handler. O teste `test_strict_guard_does_not_cover_format_suffix` fixa o comportamento atual.

## Decisão

Vamos separar em duas partes. A parte 1 não muda nenhuma decisão de escopo; a parte 2 muda o contrato do perfil e da política do proxy.

### Parte 1. Enxergar

1. **Código estável vindo do domínio.** `domain/scope_reason.py` define `ScopeReason`. Cada `ScopeViolation` da normalização e do `ScopeGuard` passa a carregar `reason` (por exemplo `path_encoded_slash`, `path_matrix_param`, `path_trailing_dot_space`, `path_double_encoding`, `path_empty_segment`, `path_dot_segment`, `path_bad_percent`, `path_invalid_utf8`, `path_control_char`, `url_forbidden_char`, `url_not_ascii`, `url_too_long`, `method_unknown`, `scheme_not_allowed`, `credentials_in_url`, `port_invalid`, `host_invalid`, e os de decisão: `deny_path`, `origin_not_allowed`, `host_not_allowed`, `path_not_allowed`, `method_not_allowed`). O `classify` do proxy deixa de olhar o texto da mensagem.
2. **Agrupador compatível.** O campo `reason` do veredito, do cabeçalho `X-Hdast-Reason` e da linha de auditoria **continua** sendo `malformed_request` para toda recusa por forma, então quem lê o valor antigo não quebra. O código granular vai em um campo novo, `detail`, na linha de auditoria (só quando existe), no `Verdict` e, agregado, em `scan.json` `traffic.denied_by_detail`. `denied_by_reason` não muda.
3. **Caminho inteiro na auditoria.** O limite do caminho sobe de 120 para 2048 caracteres (depois do escape ASCII), igual ao `MAX_URL_LENGTH` do guarda: toda URL que pode ser liberada cabe inteira, então a linha basta para reproduzir a decisão. Acima disso a URL já é recusada (`url_too_long`) e o caminho é cortado com a marca `...[cortado]`, o que mantém a proteção contra linha gigante. Nomes de parâmetro de consulta continuam em 120.
4. **Relatório.** `scan.json` `traffic` ganha `denied_by_detail`, `path_shape_denied`, `allowed_outside_allow` e `path_mode` (campos aditivos; o golden de `findings.json` foi regravado só nisso). O `report.md` mostra o modo e, quando algum pedido foi recusado pela forma do caminho, um AVISO de cobertura parcial de injeção em caminho com a contagem, o percentual e os motivos.
5. **Sufixo de formato.** No modo estrito, documentado e sem mudança: quem precisa negar `/api/admin.json` deve escrever o padrão (`/api/admin.*` não existe, pois curinga parcial é inválido; use `/api/admin.json` ou o padrão exato). No modo amplo o sufixo é tratado como mais uma leitura a conferir (abaixo).

### Parte 2. Modo amplo

1. **Opção.** `scope.path_mode: strict | wide` no perfil, dentro de `scope` ao lado de `authorization`, porque é uma autorização da carta e não um parâmetro de execução (junto de `limits` ela pareceria ajuste de desempenho; em `scope` fica junto do que a carta formaliza). Padrão `strict` (o comportamento de hoje, sem nenhuma mudança). Valor desconhecido, número, lista ou `null` são recusados na validação do perfil. A política do proxy por execução (`policy.json`) carrega o campo `path_mode` (ausente vale `strict`, `schema_version` continua 1; um proxy antigo recusa o campo novo por `extra=forbid`, o que falha fechado).
2. **Só o perfil liga.** Nenhuma flag de linha de comando existe nem existirá para `wide`. O agente nunca escolhe: copia o que a carta diz.
3. **Guarda separado.** O modo amplo vive em `domain/wide_guard.py` (`WideScopeGuard`) e `domain/widepath.py`. O `ScopeGuard` **nunca** lê `path_mode`. Só `adapters/scope_proxy/decision.py` importa o guarda amplo. Motivo: o proxy decide sobre os bytes que o ZAP enviou, e o que ele aprova é o que sai. Na CLI não é assim (o cliente HTTP normaliza a URL, resolve `..` e recodifica), então o que o guarda aprovasse poderia não ser o que vai ao fio. `probe`, `preflight`, `target_client`, redirecionamentos e o plano da CLI continuam estritos; testes provam que o guarda do perfil recusa `;` e `%2f` mesmo com `path_mode: wide` e que nenhum módulo fora do proxy importa o guarda amplo.
4. **Para LIBERAR (modo amplo).** Vale só a **leitura literal** do caminho: cada segmento cru (separado pelas barras cruas) decodificado uma vez, comparado com `scope.allow` e com o método da regra. Aceita `;`, ponto e espaço finais, `%2f` e `%5c` dentro do segmento, dupla codificação, `//` e `%` solto. `*` em `allow` continua não casando segmento vazio.
5. **Para PROIBIR (modo amplo).** Antes de liberar, o guarda gera o conjunto de leituras que um servidor poderia fazer do caminho e, se QUALQUER uma casar com `deny_paths` (sem diferença de caixa, NFKC), recusa com `deny_path`. As leituras são o fecho, sob qualquer ordem e repetição, destas transformações: decodificar uma vez (então `%2f` vira separador, e a decodificação repetida chega ao ponto fixo), barra invertida como separador, remover `;parametro` por segmento, aparar ponto e espaço (preservando `..`), resolver `.` e `..`, colapsar `//`, remover o sufixo de formato do último segmento e normalizar NFKC (que transforma `／` e `％` de largura total em ASCII). Mais a própria leitura literal. Errar para o lado de recusar é aceitável.
6. **Teto de custo.** No máximo 256 leituras distintas por pedido (8 transformações sobre no máximo 2048 caracteres: milissegundos). Se passar disso (dupla codificação absurda), recusa com `path_too_many_readings`.
7. **Continuam recusados no modo amplo:** segmento literal `.` ou `..` (cru ou codificado uma vez), NUL e caracteres de controle ou invisíveis, UTF-8 inválido, barra invertida crua, não-ASCII cru, credenciais na URL, e tudo de host, porta, esquema, método e tamanho da URL (nada disso muda).
8. **Leitura fora de `allow`, sem casar `deny_paths`: LIBERA.** Decisão do dono, escrita sem eufemismo: **neste modo, um pedido liberado pode chegar a um caminho do mesmo host que `scope.allow` não lista.** Exemplo: com `allow: /api/v1/**`, o pedido `/api/v1/..;/interno` tem leitura literal dentro de `allow`, mas um servidor que remove `;` e resolve `..` o roteia para `/api/interno`, fora de `allow` e fora de `deny_paths`. Se esse caminho existir e não estiver em `deny_paths`, será alcançado. Host e porta nunca mudam, então não há saída do host autorizado; mas a promessa "só o que está em `allow`" deixa de valer no nível do caminho. Mitigações: o dono deve listar em `deny_paths` tudo que não pode ser tocado (o modo amplo é só tão seguro quanto essa lista); cada pedido liberado nessa situação é marcado na auditoria (`detail: wide_reading_outside_allow`) e contado em `traffic.allowed_outside_allow` e no relatório, para a pessoa saber quantos foram.
9. **Registro.** `scan.json` `traffic.path_mode` e o `report.md` registram em que modo a varredura rodou.

## Alternativas consideradas

- **Recusar toda leitura fora de `allow`.** É o mais seguro, mas devolve quase todo o tráfego de `..;` e `%2f..%2f` à recusa, e esses são os ataques que o modo amplo existe para deixar passar. O dono aceitou o risco do mesmo host. Descartada (a marca na auditoria é a contrapartida).
- **Tornar o guarda estrito configurável (um único `ScopeGuard` com modo).** Um erro de montagem ligaria o modo na CLI. Descartada; guarda separado e importado só pelo proxy.
- **Flag `--path-mode wide`.** Qualquer flag um agente também passa. Descartada: só o perfil, que vem da carta.
- **Trocar `reason` por código granular.** Quebraria quem lê `malformed_request` e os testes do contrato do proxy. Descartada; agrupador em `reason`, granular em `detail`.
- **Tratar o sufixo de formato também no modo estrito.** Faria `deny_paths: /api/admin` cobrir `/api/admin.json`, o que é mais seguro, mas muda a semântica de padrões já escritos e recusa a mais sem a carta pedir. Fica para a decisão do dono; o modo amplo já cobre.
- **Decodificar também em Latin-1.** Cobriria servidores que leem bytes inválidos como Latin-1. Descartada: o modo amplo recusa UTF-8 inválido.

## Consequências

- Passa a ser possível dizer, por varredura, quanto da injeção em caminho foi perdida e por quê; o relatório avisa.
- No modo estrito nada muda para a decisão; só o campo `detail`, o limite de 2048 do caminho na auditoria e os campos novos de `traffic`.
- Limites que ficam (como no modo estrito): `::$DATA` e nomes 8.3 do IIS, e qualquer reescrita que o servidor faça e que não esteja na lista de transformações. O modo amplo é tão forte quanto essa lista e quanto o `deny_paths` escrito pelo dono.
- A imagem do proxy precisa ser reconstruída para ler `path_mode` na política e gravar `detail`.
- O modo registrado em `scan.json` vem do perfil lido no `scan`; a política vem do perfil lido no `stack up`. Se o perfil for editado entre as duas leituras, os dois podem divergir; o `run` lê o perfil uma vez por etapa e a pilha sobe no começo.
- A prova em laboratório (isca em `deny_paths` alcançada por cada forma) ainda precisa ser feita contra o proxy e o ZAP reais.
