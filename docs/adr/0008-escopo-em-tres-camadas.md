# 0008. Escopo em três camadas

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** AD-11, P-03

## Contexto

Os incidentes públicos de 2026 tiveram a mesma causa: escopo só em instrução, com saída de rede aberta. A ferramenta ataca sistemas de propósito; sair do escopo pode causar dano a terceiros.

## Decisão

Vamos impor o escopo em três camadas independentes, falhando fechado (na dúvida, a execução para).

1. **`ScopeGuard` no domínio** valida toda requisição e todo plano de varredura contra a lista permitida.
2. **ZAP em modo protegido**, com contexto restrito aos mesmos hosts e caminhos.
3. **Rede interna do Docker e proxy de saída** com lista de hosts permitidos: o contêiner do ZAP só sai por esse proxy.

Cronograma decidido (P-03): camadas 1 e 2 desde o início; a camada 3 é obrigatória antes de qualquer execução contra ambiente da empresa e opcional contra o lab.

Flags de linha de comando só reduzem escopo e limites, nunca ampliam. O perfil carrega a referência da autorização formal e a validade; sem isso, ou fora da janela, a CLI recusa.

## Alternativas consideradas

- **Só a camada 1.** Um defeito nosso libera tudo.
- **Só o prompt.** Nenhuma garantia.

## Consequências

- O proxy de saída é um contêiner a mais no `compose.yaml`.
- Cada camada cobre a falha da outra.
- As permissões do Claude Code (negar `curl` e leitura de `.env`) são barreira de conveniência, não isolamento; a garantia vem das três camadas.
- O `ScopeGuard` é o componente de maior risco e tem casos de teste obrigatórios ([../testing.md](../testing.md)).
- Estado em 2026-11-13 (nota de estado, antes do primeiro commit): a camada 1 existe como código de domínio (`ScopeGuard`, sem uso por nenhum comando ainda); a camada 3 existe como configuração (`compose.yaml` e `docker/egress-proxy/`), verificada no lab, mas sem tráfego de varredura real provado; a camada 2 (ZAP protegido) não existe, prevista para o M4. O proxy de saída continua sendo condição para o piloto do M7.
