# 0093. Diagnóstico sanitizado da vigia do proxy

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** investigação V1.12 L de `STACK_STALE` sem mudança observada das fontes

## Contexto

A recusa `approval_changed` agrega causas diferentes: alteração ou falha das fontes,
interrupção da vigia e snapshot vencido. A informação atual não permite identificar o primeiro
motivo no processo que recusou a concessão. A vigia independente não observa seu estado interno.

## Decisão

Vamos emitir em stderr uma única linha JSON por primeira trava de cada vigia, com exatamente as
chaves `event` e `category`.
`event` vale `gate_watch_latch`. `category` pertence ao catálogo fechado: `age`, `clock`,
`no_snapshot`, `close`, `detect_error`, `detect_denied`, `stop_or_inaccessible`, `access`,
`unstable`, `identity`, `metadata`, `hash`, `size_or_type` ou `approval_invalid`.

A categoria identifica o primeiro fato observado, não prova a causa externa. `unstable` cobre
divergência durante a leitura inicial ou entre os dois metadados do descritor; `identity` e
`metadata` distinguem divergência de identidade e dos demais metadados nas comparações posteriores.
Não há nome ou tipo de fonte, caminho, conteúdo, hash, valor de metadado, exceção ou ambiente.
O evento é separado da auditoria de requisições, não muda seus campos, a resposta HTTP ou a CLI.
É emitido por thread daemon após marcar a trava, sem fazer E/S de log sob o lock ou aguardar
o log na concessão/encerramento. A emissão é de melhor esforço: interrupção imediata do processo,
falha de início, escrita parcial ou falha de escrita ou coleta externa podem perder o evento;
ausência não prova ausência de trava. O estado interno consultável distingue `pending`, `sent`,
`start_failed` e `write_failed`, sem incluir a exceção. A emissão usa `os.write` com bytes fixos,
sem handlers de logger que possam lançar exceções arbitrárias ou registrar dados externos. Uma
escrita parcial pode produzir trecho incompleto; coletores devem aceitar apenas JSON completo do
catálogo. `sent` confirma apenas a escrita local, não a coleta externa.

O limite de 200 ms desde o início, a espera periódica, as leituras e hashes completos, a trava
permanente, as recusas e a verificação de autorização, janela e prazo permanecem iguais.

## Alternativas consideradas

- Vigia adicional: pode observar outra sequência de eventos e não identifica o primeiro latch real.
- Gravar conteúdo, nomes de fonte ou valores: desnecessário e incompatível com a sanitização.
- Imprimir sob o lock: E/S bloqueada poderia prender concessões e o encerramento.
- Alterar o limite ou renovar no fim da leitura: mudaria a garantia do ADR 0072 sem evidência.

## Consequências e aceite

O coordenador precisa reconstruir a imagem e capturar somente eventos do catálogo, antes de o
contêiner encerrar. O diagnóstico sozinho não prova a causa externa; uma reprodução e comparação
com metadados sanitizados adicionais podem ser necessárias. Aceite exige testes de primeiro latch,
categorias, ausência de dados, log bloqueado, falha de fontes e regressões de revogação, além de
prova no processo real e revisão humana da área de segurança. Solicita-se ao coordenador indexar
este ADR e atualizar a documentação compartilhada ao integrar. O ADR não é uma correção do defeito.
