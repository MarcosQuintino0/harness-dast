# 0105. Ponte OAST na pilha do laboratório e verificabilidade do retorno

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** V1.12.1, parte 2; substitui parcialmente o [ADR 0099](0099-oast-na-varredura.md), somente quanto à montagem da ponte e à interpretação de sua ausência; complementa os ADRs [0095](0095-retorno-oast-isolado.md) e [0100](0100-ssrf-guiado-pelo-contrato.md).

## Contexto

A carta do caso `crapi-foco` autoriza `attack.oast`, convertido pela CLI em
`scan.oast: true`. Na rodada cega, o SSRF guiado enviou a URL de
`oast-gateway:8090` para `contact_mechanic`, mas não observou retorno. O ciclo
normal de `stack up crapi` não montava a ponte nem ligava o workshop à sua rede:
essa montagem existia somente no suporte de integração, conforme o ADR 0099.
O agente avaliado não pode alterar a pilha por fora da CLI. Assim, zero retornos
parecia ausência de falha, quando faltava a infraestrutura para verificar.

## Decisão

Vamos incorporar a montagem da ponte ao ciclo gerenciado do alvo de laboratório
crAPI e representar explicitamente quando o retorno não pode ser verificado.

- **Autorização preservada.** Somente o alvo reconhecido como crAPI de laboratório,
  com perfil aprovado e `scan.oast: true`, recebe a ponte. Sem a chave, a montagem
  anterior permanece. Produto comum não recebe serviço nem rede de retorno.
- **Montagem única.** A pilha reutiliza `lab/oast/compose.yaml` e
  `lab/crapi/compose.oast.yaml`. A ponte sobe antes do workshop que depende da rede;
  a descida retira o alvo antes de remover a ponte e sua rede. O suporte de
  integração passa a consumir a mesma montagem, sem repetir a subida e a conexão.
- **Isolamento preservado.** A rede de retorno é interna, sem publicação de porta
  e sem saída à internet. Permanecem usuário sem privilégios, sistema de arquivos
  somente leitura, capacidades removidas e limites de recursos da ponte. O ZAP
  continua saindo para o alvo somente pelo proxy de escopo.
- **Decisão no domínio.** O adaptador fornece fatos sobre a disponibilidade da
  ponte pela porta `OastBridge` de `application/scan_ports.py`; o domínio decide
  em `domain/oast_verification.py` se as duas capacidades dependentes do retorno são
  verificáveis. Chave autorizada sem ponte disponível significa **não verificável**,
  com motivo explícito, para o SSRF guiado e para o OAST do ZAP. Zero observações
  não substitui essa decisão. Nenhum pedido de SSRF guiado deve ser induzido quando
  não há como observar seu retorno.
- **Contrato aditivo.** `scan.json.oast_verification` informa os estados do ZAP e do
  SSRF guiado (`verifiable` ou `unverifiable`) e o motivo da lacuna. Sua presença
  registra a solicitação de OAST; `policy` descreve a política efetiva, reduzida
  quando falta observação. A redução preserva as demais recusas e estreitamentos.
  Relatório e painel exibem o motivo e a cobertura fica parcial. Artefatos antigos
  continuam legíveis; OAST ligado sem esse registro é lacuna desconhecida,
  sem confirmação retroativa. Não mudam carta, schema do perfil, autorização,
  envelope nem códigos de saída.

## Alternativas consideradas

- **Manter a ponte só nos testes.** Rejeitado: não resolve o fluxo normal da CLI
  nem a avaliação cega, que não admite intervenção externa durante o `run`.
- **Subir a ponte para qualquer produto ou sem a chave.** Rejeitado: acrescenta
  infraestrutura sem necessidade e não prova que um produto comum a alcança.
- **Apenas escrever um aviso na skill.** Rejeitado: a decisão e o contrato de
  resultado precisam valer em código testado, inclusive sem agente de IA.
- **Tratar zero retornos como sucesso.** Rejeitado: confunde ausência de observação
  com uma verificação que efetivamente pôde acontecer.

## Consequências

A prova do crAPI passa pelo mesmo `stack up` e `run` disponíveis ao agente avaliado.
Fora dessa montagem, as capacidades de retorno podem permanecer não verificáveis;
esse resultado não demonstra segurança do alvo. Mesmo com ponte disponível, zero
retornos não demonstra ausência de vulnerabilidade. A disponibilidade da topologia
indica uma condição para observar; o achado continua exigindo retorno correlacionado.

Esta decisão substitui a reserva de montagem ao suporte de laboratório do ADR 0099;
a configuração do Callback continua pertencendo ao scan e condicionada à carta.
Não adicionamos técnica, dependência ou autorização. O ADR permanece proposto até
o aceite do dono.

A coordenação permanece no caso de uso `Scan`, arquivo já acima de 300 linhas.
A preparação OAST ultrapassa 40 linhas para manter explícita a ordem entre redução,
configuração, observação e fallback específico; as decisões puras e a inspeção
externa ficam em módulos próprios, com testes separados. Falha geral de política
continua interrompendo a etapa, enquanto a falha específica do Callback registra
a lacuna e mantém as demais verificações possíveis.

## Aceites verificáveis

- CLI `stack up crapi` com OAST autorizado, seguida de `run`, observa retorno no
  SSRF guiado de `contact_mechanic` e produz achado, sem helper montar a ponte.
- O mesmo ciclo com a chave desligada não monta a ponte e não gera tráfego OAST.
- Ponte ausente com a chave ligada produz motivo de não verificabilidade nas duas
  capacidades, no JSON, no relatório e no painel.
- `stack down` remove os recursos das provas, preservando o endurecimento.
- Regressão dirigida e os seis gates passam, com duração registrada no relatório.
