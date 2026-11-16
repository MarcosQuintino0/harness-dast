# ADR 0067: Ritmo único e medição do executor

Status: Proposto. Data: 2026-11-16.

## Contexto

O ZAP aplica um atraso por host enquanto a cerca já limita a taxa de saída. A soma dos tempos de regras não é tempo de parede: regras e outras atividades podem se sobrepor.

## Decisão

O perfil aceita `scan.pacing: legacy | proxy`, com `legacy` por padrão. No modo `proxy`, o atraso configurado no ZAP é zero; as demais opções da política e os limites da carta permanecem iguais. A alteração participa da impressão digital protegida; o valor padrão mantém as aprovações antigas. Não existe flag para ampliar autorização. O modo `proxy` não se torna padrão enquanto a prova exigida pelo plano não for aceita.

A fila mede a soma das esperas individuais desde o início do executor serial. A autenticação mede ativação, troca e renovação de identidade, inclusive a gestão do Replacer. Esses intervalos podem se sobrepor ao tempo de parede de outras varreduras. O atraso configurado não é uma medição do atraso real do ZAP, que permanece indisponível. A CPU acumulada da CLI é amostrada no início e fim; a memória é o pico residente histórico do processo da CLI, não somente durante o scan. ZAP, proxy e processos filhos não entram. Fontes indisponíveis ficam nulas.

## Consequências

O novo modo é uma hipótese para comparação, não uma promessa de velocidade nem evidência de equivalência executada. Os registros de regras continuam separados do tempo de parede; sem intervalos por regra fornecidos pelo ZAP, a sobreposição efetiva por regra não é conhecida. Recuo de 429 e concessões são responsabilidade da cerca, não há repetição cega no executor. Tecnologia declarada não desliga regras nesta versão.
