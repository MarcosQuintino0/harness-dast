# ADR 0056: Dicas de encadeamento e contas pares

Estado: Proposto. Data: 2026-11-15.

## Contexto

O contrato pode indicar que uma lista fornece valor para uma leitura de detalhe. Um perfil também pode ter duas contas do mesmo papel enquanto todas as leituras de objeto daquele papel são roteadas para uma só.

## Decisão

`spec inspect` retorna hipóteses `flow` e `peer_account`, também mostradas na saída humana. A inspeção só considera operações que o plano permite enviar; não acessa o alvo nem muda perfil ou autorização. Nomes e formatos de campos são dados não confiáveis; em mensagens passam por sanitização.

Para listas de objetos, nomes de campo e parâmetro iguais ou formato UUID compatível sugerem relação; para listas de strings, um parâmetro de arquivo em caminho descendente pode ser candidato. O primeiro item é representado por `0`, inclusive em listas envolvidas em objetos. Essas relações não provam que o valor existe nem que a ligação é correta. Há tetos de 250 operações, 100 nós de esquema, profundidade 5 e 40 dicas; ausência de dica não prova ausência de relação.

Uma sugestão de contas exige duas contas do mesmo papel e leituras de objeto atribuídas a uma só delas. A distribuição proposta é entre operações distintas e depende das permissões informadas pelo dono. Com apenas uma operação, o mapa aceita só uma conta; execuções separadas não são reunidas automaticamente.

## Consequências

A saída JSON recebe `hints` como campo aditivo. As sugestões exigem revisão humana ou do agente contra o contrato e os dados, podem ter falsos positivos e não substituem o `probe` ou os critérios de autorização.
