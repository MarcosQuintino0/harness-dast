# 0090. Recibo de semente e interrupção da confirmação

- **Status:** Proposto
- **Data:** 2026-11-17

## Contexto

Operação e modelo de caminho não provam que a conta e o alvo concretos foram varridos. A confirmação precisa permitir auditoria da comparação e preservar o motivo de uma parada sem gerar tráfego adicional.

## Decisão

Vamos acrescentar a `ScanEntry` um recibo opcional com alias e SHA-256 de uma serialização canônica da operação, método, URL integral e alias efetivamente usados no início da varredura. O runner registra a conta efetiva após fixação. Na confirmação, a URL é recomposta com o ambiente atual e a troca do probe; o recibo, o caminho, o método, o template, o scan iniciado e pelo menos um pedido devem corresponder. Só uma combinação alvo e conta é elegível. A conta do recibo precisa existir no perfil atual. Registros antigos sem recibo são `not_verifiable`, sem tráfego; não há prova retroativa.

A prova guarda resumo do pedido GET com alvo representado por digest, receita e parâmetro de consulta, e status, duração, tamanho e digest curto do corpo em grupos de ataque e controle, inclusive em resultados parciais. Não grava corpos, valores da consulta ou cabeçalhos. O digest possibilita comparar igualdade, não recuperar ou inspecionar o conteúdo; respostas pequenas podem ser adivinháveis. Redação do armazenamento segue vigente.

Erros `HarnessError` e interrupção preservam a prova parcial e seguem com o código original após a gravação. As travas são conferidas antes de abrir sessão e em cada envio. O teto de doze inclui a sessão e os pedidos da receita; no máximo trinta achados são selecionados. A gravação não altera achados nem severidade.

## Alternativas consideradas

Metadados de operação e template não identificam o alvo concreto. Salvar a URL ou resposta integral acrescentaria exposição desnecessária. Migrar execuções antigas inventaria uma prova inexistente.

## Consequências e aceites

Execuções anteriores precisam de nova varredura autorizada para confirmação ativa. Testes locais devem cobrir divergência de conta, alvo, ambiente, método, recibo ausente e scan sem pedidos; teste de prova distingue corpos de mesmo status sem expor conteúdo. Testes de parada devem comprovar preservação do erro e prova parcial sem tráfego indevido. A prova operacional e calibração dependem de aprovação humana e laboratório.
