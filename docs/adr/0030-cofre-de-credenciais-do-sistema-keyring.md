# 0030. Cofre de credenciais do sistema operacional (`secret_ref: keyring:NOME`) e o comando `hdast secret`

- **Status:** Aceito
- **Data:** 2026-11-13
- **Origem:** atrito de uso da V1.1; amplia o [ADR 0009](0009-segredos-por-referencia.md) (segredos por referência) e segue a lógica do [ADR 0025](0025-limpeza-confirmacao-so-em-terminal-e-correcoes-do-qa-m2-m5.md) (confirmação só por pessoa, em terminal)

## Contexto

Hoje a senha de uma conta de teste só entra por variável de ambiente (`secret_ref: "env:NOME"`). A pessoa de QA digita várias variáveis a cada terminal aberto, erra com facilidade, e as senhas ficam no histórico do shell. É o maior atrito que sobrou. O cofre de credenciais do próprio sistema (Gerenciador de Credenciais do Windows, Keychain do macOS, Secret Service do Linux) guarda o valor cifrado, ligado à sessão da pessoa, e some do histórico.

Restrições que valem aqui: o agente de IA nunca lê nem grava segredo (CLAUDE.md, parte B); `env:` continua sendo o caminho do CI e da avaliação cega; um valor guardado no cofre tem de ser mascarado como os de ambiente; falha do cofre não pode cair em silêncio para outro lugar.

## Decisão

Vamos:

1. **Nova referência `secret_ref: "keyring:NOME"`**, com NOME no mesmo formato do `env:` (maiúsculas, dígitos e `_`, sem o prefixo `HDAST_`). O valor fica no cofre do sistema sob o serviço fixo `harness-dast` e o nome de usuário NOME. Para não colidir entre produtos, a convenção é a mesma do `env:`: NOME começa pelo produto (`AGENDA_USER_A_SENHA`). A carta de autorização continua listando só nomes.
2. **Biblioteca `keyring` 25.7** (MIT, mantida por jaraco, release recente, tipada, usada há anos pelo pip, twine e poetry). Entram junto `jaraco.classes`, `jaraco.context`, `jaraco.functools`, `more-itertools` e `pywin32-ctypes` (Windows) ou `SecretStorage`/`jeepney` (Linux), todas permissivas e travadas no `uv.lock`. O `pip-audit` do CI cobre todas.
3. **Só backends do próprio sistema.** O adaptador recusa qualquer backend fora de uma lista fixa (`WinVaultKeyring`, `macOS.Keyring`, `SecretService.Keyring`, `libsecret.Keyring`, `kwallet.DBusKeyring`), inclusive quando o `ChainerBackend` os agrupa. Isso barra o backend `fail` (sem cofre), o `null` e, principalmente, um backend de arquivo em texto claro (`keyrings.alt`) que alguém instale ou escolha por `PYTHON_KEYRING_BACKEND` ou `keyringrc.cfg`. O backend é escolhido só na primeira vez que um `keyring:` é usado: quem usa só `env:` (CI, contêiner) nunca toca o cofre.
4. **Sem cofre utilizável é erro, nunca desvio.** Um novo erro `SecretBackendError` (código `SECRET_BACKEND_ERROR`, saída 4, a mesma de `PREFLIGHT_FAILED`; nenhum código de saída novo) diz o que houve e a dica (usar `env:NOME` em contêiner/CI, ou instalar/desbloquear o serviço de segredos). Uma referência `keyring:` nunca é lida de variável de ambiente, e vice-versa. No `preflight` e no `doctor` o erro vira uma verificação reprovada (não aborta o relatório); em `probe`, `scan` e `cleanup` aborta com a dica.
5. **Comando `hdast secret set|list|delete`, para a PESSOA.**
   - `set NOME`: lê o valor por prompt oculto, com confirmação digitada duas vezes, e só em terminal interativo (stdin e stderr). Sem terminal, recusa (`CONFIG_ERROR`, saída 2). Nunca por argumento, variável nem `stdin` redirecionado. O valor nunca é mostrado, nem o tamanho.
   - `delete NOME`: pede para digitar o NOME de novo, só em terminal. Sem terminal, recusa.
   - `list PRODUTO`: para cada `keyring:` citado no perfil, mostra NOME, os campos que o usam e `present: true|false`. Não mostra valor nem tamanho. É leitura e fica liberado ao agente.
   O caso de uso recebe `interactive` (a CLI o calcula; os testes injetam), como no `cleanup`. O agente não grava nem remove porque a permissão do Claude Code nega esses dois subcomandos (camada 0, de conveniência) e porque o código exige terminal (a trava de verdade). Limite honesto, como no ADR 0025: um pseudoterminal ainda cumpriria; e qualquer processo da conta do usuário lê o cofre dele (ver Consequências).
6. **Redação igual à do ambiente.** O valor resolvido passa pelo mesmo caminho (`SecretVault.register`) que o de `env:`: tudo que resolve segredo (login, `preflight`, `doctor`, limpeza) o registra. A mesma regra vale para o valor digitado no `set`.
7. **Evals.** A checagem de fidelidade do perfil aceita só `env:` com os nomes da carta; um `keyring:` é reprovado ali (a avaliação cega é sem pessoa e sem cofre; a carta do caso usa nomes de variável). O caso continua passando só com `env:`.

## Alternativas consideradas

- **Chamar `cmdkey`/DPAPI direto.** Só Windows, exige processo auxiliar ou `ctypes` próprio, e o `cmdkey /add:... /pass:...` põe a senha na linha de comando (histórico, lista de processos): é o problema que queremos eliminar. Descartada.
- **Arquivo cifrado próprio.** A chave teria de morar em algum lugar (outro arquivo, ou uma senha mestra a digitar a cada uso); cripto caseira é o tipo de código que não escrevemos. Descartada.
- **Continuar só com `env:`.** Não resolve o atrito. Continua existindo e continua sendo o caminho de CI.
- **`keyring` com a configuração padrão (qualquer backend).** Em contêiner sem serviço, o `keyring` pode cair para um backend de arquivo em texto claro se `keyrings.alt` estiver instalado. A lista fixa do item 3 elimina isso. Descartada a configuração aberta.
- **Listar tudo que existe no cofre.** O `keyring` não tem API de listagem portável. Por isso `list` parte do perfil (o que o produto cita), que é também o que a pessoa quer saber.
- **Capturar só exceções do `keyring` no adaptador.** O backend do Windows levanta `pywintypes.error` (herda de `Exception`) e cada backend de Linux, outras. O adaptador usa um único `except Exception` justificado em comentário (exceção à regra "sem except genérico", limitada a esse ponto): converte em `SecretBackendError` com o nome da classe da causa, sem repetir a mensagem do backend.

## Consequências

- Em contêiner ou CI sem serviço de segredos, nada muda para `env:`. Quem escrever `keyring:` ali recebe `SECRET_BACKEND_ERROR` com a dica de usar `env:`.
- **O cofre não é um cofre contra o agente.** Qualquer processo na sessão da pessoa lê as credenciais dela (no Windows, o Gerenciador de Credenciais não pede confirmação a um processo do mesmo usuário). Ganhamos: nada no histórico do shell, nada em arquivo do projeto, nada no ambiente de cada terminal, cifrado em repouso. Não ganhamos: isolamento de um agente que rode código arbitrário na mesma conta. A defesa contra isso segue sendo a permissão do Claude Code (só `hdast ...` liberado) e a regra de não tocar segredo (CLAUDE.md, parte B).
- Limites do Windows: o valor guardado no Gerenciador de Credenciais não passa de cerca de 1280 caracteres (2560 bytes em UTF-16). Vale para senha, não para string de conexão longa com muitos parâmetros (que pode seguir em `env:`).
- O `keyring` do Windows guarda a primeira credencial sob o nome `harness-dast` e move as seguintes para `NOME@harness-dast`; isso é interno da biblioteca, mas aparece no Gerenciador de Credenciais.
- Cabe a quem mudar de máquina regravar os segredos (o cofre não viaja).
- Mudança de contrato aditiva: novo formato aceito em `secret_ref` (schema do perfil continua `1`: o campo já era texto), novo código de erro e novo comando `secret` (envelope igual ao dos demais). Teste cego e CI seguem com `env:`.
- Não verificado em máquina real nesta entrega (os testes usam um backend de teste em memória e nunca tocam o cofre da máquina): o roteiro de prova no Windows está no relatório da entrega e em `docs/guides/primeiro-uso.md`.
