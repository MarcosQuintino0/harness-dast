# 0091. Observações passivas de confirmação

- **Status:** Proposto
- **Data:** 2026-11-17
- **Origem:** V1.11, confirmação sem tráfego adicional.

## Contexto

Achados guardam provas diferentes conforme sua origem. Status 2xx por si só não demonstra
alteração de estado, equivalência de corpos ou exposição de interface HTML. A classificação
deve ser aditiva, sem alterar severidade ou estado, sem repetir payload ou URL e sem gravar
credenciais ou respostas integrais. As evidências do alvo são dados, nunca instruções.

## Decisão

Vamos oferecer duas funções puras no domínio, sobre `Finding` e `AuthzFinding`, que devolvem
`VerificationEntry` com motivo e resumo fixo de prova. Cabeçalhos HTTP completos e válidos
permitem observar ausência de proteção em resposta HTML; uma resposta JSON não demonstra
vulnerabilidade de interface HTML. Valores de CORS são classificados pela regra existente
somente quando a origem e os cabeçalhos efetivamente constam da mensagem guardada. CORS
de authz guarda um receipt tipado da política, não os cabeçalhos: a prova nomeia esse limite.
Regras passivas sem interpretação segura são recusadas; tipos de receita ativa ficam para
o consumidor. O resultado não é confirmação humana nem avaliação de probabilidade.

Para autorização, serão examinados técnica, status, identidades, papéis, variantes, campos,
origem de candidato e receipt de comparação conforme cada técnica. Receipts antigos de
comparação de corpo dependem de texto produzido pelo construtor: dois status 2xx não bastam.
Escrita horizontal e atribuição em massa exigem receipt de leitura posterior para afirmar
alteração persistida; resposta do próprio POST não comprova persistência. A matriz comprova
resposta de sucesso ao papel proibido, não efeito de escrita. Campos fora do esquema não
provam sensibilidade ou impacto. Nenhum desses resultados autoriza nova escrita.

## Alternativas consideradas

- Repetir pedidos: descartado nesta fronteira por exigir autorização e execução controlada.
- Aceitar todo 2xx como reprodução: descartado por não comprovar o efeito pertinente.
- Inventar headers a partir do nome da política: descartado por atribuir uma captura inexistente.

## Consequências e aceites

Alguns registros antigos ficam não verificáveis; outras observações registram somente uma
propriedade, sem provar impacto. A integração das APIs é responsabilidade de outra frente.
Testes locais devem cobrir provas suficientes, ausentes, inconsistentes e malformadas,
redação e preservação dos achados. A validação operacional e a calibração da V1.11 ficam
para o fechamento autorizado; não há estimativa de acerto nesta proposta.
