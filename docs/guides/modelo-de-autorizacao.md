# Modelo de carta de autorização

Peça este documento ao dono do produto **antes** de cadastrar o produto. Sem ele preenchido e assinado, não há perfil: `scope`, `limits`, `authorization` e as janelas do perfil são **transcritos daqui**, nunca inventados (nem por você, nem pelo agente). Se algum campo ficar em branco, o cadastro para.

Fundamento: [authorization-and-scope.md](../operations/authorization-and-scope.md). Campos do perfil: [target-yml.md](../reference/target-yml.md).

Só ambiente de **teste**, com **dados sintéticos**. Produção e dados de pessoas reais ficam de fora.

## Modelo (copie e preencha)

```text
CARTA DE AUTORIZAÇÃO DE TESTE DE SEGURANÇA

1. Identificação
   Produto / sistema:
   Dono do produto (nome e e-mail):
   Referência desta autorização (ticket, e-mail de aprovação):
   Válida até (AAAA-MM-DD, com folga: a CLI conta a data em UTC):

2. Ambiente
   Nome do ambiente (homologação, teste, laboratório):
   URL base (esquema, host e porta):
   Declaro que é ambiente de teste, sem dados reais de pessoas:  [ ] sim

3. Escopo
   Hosts autorizados:
   Caminhos autorizados (ex.: /api/**):
   Métodos autorizados (liste só os necessários; DELETE só se escrito aqui):
   Caminhos PROIBIDOS, mesmo dentro dos autorizados (ações destrutivas,
   envio de e-mail ou SMS, integrações com terceiros, exclusão de conta):
   Modo de leitura de caminhos pela cerca (marque UM; sem marca vale estrito):
     [ ] estrito (padrão): a cerca recusa caminhos ambíguos (;  %2f  ..  //)
     [ ] amplo: libera mais formas de caminho e nega se QUALQUER leitura do
         caminho casar com um proibido. Risco aceito: um pedido liberado pode
         alcançar outro caminho do mesmo host que não esteja na lista de
         proibidos acima (host e porta nunca mudam). Exige a lista de
         proibidos completa.
   Local do Swagger/OpenAPI (arquivo ou URL de teste):

4. Janela de execução (dias, horário e fuso. Ex.: seg-sex 20:00-06:00 America/Sao_Paulo)

5. Limites de carga
   Requisições por segundo (máximo):
   Duração máxima de uma execução, em minutos:
   Conexões simultâneas do varredor (threads por host):
   O alvo limita logins por minuto? Quanto:

6. Contas de teste (uma por papel necessário)
   Apelido | Papel | Nome da variável de ambiente do usuário | da senha
   (a carta traz os NOMES das variáveis; as senhas são entregues por canal
   seguro direto a quem opera e nunca ao agente)

7. Limpeza dos dados criados
   [ ] Não haverá limpeza automática (ambiente descartável ou recriado)
   [ ] Haverá limpeza por SQL (Oracle). Quem escreve e revisa o script:
       Usuário de banco só da limpeza (SELECT e DELETE nas tabelas abaixo):
       Tabelas permitidas:
       Teto de linhas apagadas:

8. Contato de emergência (nome, telefone, canal) para parar a execução:

9. Assinatura do dono do produto e data:
```

## Como cada campo vira perfil

| Campo da carta | Vira no `target.yml` |
| --- | --- |
| URL base | `environment.base_url` |
| Hosts, caminhos, métodos | `scope.allow` |
| Caminhos proibidos | `scope.deny_paths` |
| Modo de leitura de caminhos | `scope.path_mode`: `strict` (estrito, ou sem marca) ou `wide` (amplo, só se marcado). O agente nunca marca por conta própria |
| Referência e validade | `scope.authorization.reference` e `valid_until` |
| Janela | `scope.windows` |
| Limites | `limits.requests_per_second`, `max_duration_minutes`, `zap_threads_per_host` |
| Logins por minuto | `auth.login_limit.max_per_minute` |
| Contas e variáveis | `auth.accounts` (`alias`, `role`, `secret_ref: "env:NOME"`) |
| Limpeza | bloco `cleanup` (escrito pela pessoa; o agente nunca o inventa) |
| OpenAPI | `openapi` |
| Contato de emergência | fora do perfil: quem para a execução (`hdast stop`) e quem autoriza ampliações |

## Regras

- Se o escopo parecer curto demais, peça ao dono do produto uma carta nova. Ninguém amplia por conta própria.
- Autorização vencida ou janela fechada: a CLI se recusa (saída `3`). Não há flag que contorne.
- Guarde a carta junto da referência; a referência vai em todo relatório.
