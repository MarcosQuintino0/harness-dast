"""Catálogo fixo de explicação de falha, em português simples (aba "Falhas" do painel).

Cada tipo de falha tem texto escrito aqui, no código, para quem não domina segurança: um título
que conta o que houve, o que aconteceu, por que importa, o que fazer (passos, cada um com quem
faz) e o nome técnico (que vai numa etiqueta cinza). A chave é o que já identifica o tipo no
projeto: a regra do ZAP (`plugin_id`), o CWE e, para o teste de autorização entre contas, a
técnica (`authz_*`).

Regras do desenho, garantidas por teste:

- nada de "seguro" nem "aprovado", e nenhuma promessa de que a correção resolve;
- a explicação nunca muda severidade, confiança nem status do achado (ela só descreve);
- nenhum texto do alvo entra no catálogo; só um tipo DESCONHECIDO ecoa o nome da regra do ZAP
  (limpo e cortado), na explicação genérica e honesta;
- o `fix_hints` continua existindo: é a direção SUGERIDA para quem corrige (código Spring) e é
  usada pelo `report.md` e `report.html`; este catálogo é a explicação para quem lê o painel.

Este módulo é puro. Passa de 300 linhas por ser, na maior parte, o texto do catálogo (dados,
sem lógica): cada entrada é uma constante.
"""

import re
from typing import Final, Literal

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.authz_result import AuthzTechnique
from harness_dast.domain.finding import Finding
from harness_dast.domain.manual_repro import is_time_based
from harness_dast.domain.redaction import strip_control

Who = Literal["QA", "dono do produto", "time de desenvolvimento"]
WHO_VALUES: Final[tuple[Who, ...]] = ("QA", "dono do produto", "time de desenvolvimento")

_QA: Final[Who] = "QA"
_OWNER: Final[Who] = "dono do produto"
_DEV: Final[Who] = "time de desenvolvimento"

GENERIC_KEY: Final = "desconhecido"
_TITLE_CAP: Final = 80
_RULE_ID: Final = re.compile(r"[A-Za-z0-9_.-]{1,20}")


class ActionStep(ApiModel):
    """Um passo do "o que fazer".

    Attributes:
        who: Quem faz o passo.
        text: O passo, em português simples.
    """

    who: Who
    text: str


class FindingExplanation(ApiModel):
    """Explicação de um tipo de falha.

    Attributes:
        key: Identificador estável da entrada do catálogo (`sql_injection`, `desconhecido`).
        known: `False` para a explicação genérica de um tipo que o catálogo não conhece.
        title: Frase que conta o que houve.
        what_happened: O que o teste fez e observou, sem afirmar mais do que a prova mostra.
        why_it_matters: Por que isso importa, sem exagero e sem promessa.
        what_to_do: Passos, cada um com quem faz.
        who: Quem conduz o assunto (um dos três papéis).
        technical_name: Nome técnico, para a etiqueta cinza.
    """

    key: str
    known: bool = True
    title: str
    what_happened: str
    why_it_matters: str
    what_to_do: tuple[ActionStep, ...]
    who: Who
    technical_name: str


def _steps(*items: tuple[Who, str]) -> tuple[ActionStep, ...]:
    return tuple(ActionStep(who=who, text=text) for who, text in items)


def _open_ticket() -> tuple[Who, str]:
    return (_QA, "Abrir um chamado com o código da falha e a prova mostrada nesta página.")


def _retest() -> tuple[Who, str]:
    return (_QA, "Pedir o mesmo teste depois que o time mexer, para comparar o resultado.")


_SQL = FindingExplanation(
    key="sql_injection",
    title="Um texto digitado pode estar virando parte do comando que o sistema manda ao banco",
    what_happened=(
        "O teste mandou um texto montado de propósito (por exemplo, um apóstrofo) num campo de "
        "busca ou num dado do pedido. A resposta indica que o sistema colocou esse texto "
        "dentro do comando que envia ao banco de dados, em vez de tratá-lo só como um valor."
    ),
    why_it_matters=(
        "Se isso for real, quem souber montar o texto certo consegue mudar o comando do banco: "
        "ler dados de outras pessoas ou alterar informações sem ter permissão."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_DEV, "Montar o comando do banco com parâmetros, nunca juntando o texto digitado."),
        (_DEV, "Não devolver na resposta a mensagem de erro interna do banco."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Injeção de SQL (CWE-89)",
)

_PATH = FindingExplanation(
    key="path_traversal",
    title="O sistema pode estar aceitando um caminho de arquivo montado por quem chama",
    what_happened=(
        "O teste trocou parte do endereço ou de um campo por um caminho que sobe de pasta "
        "(com `../`) e observou na resposta sinais de que o sistema tentou abrir um arquivo "
        "fora da pasta prevista."
    ),
    why_it_matters=(
        "Se isso for real, alguém pode ler arquivos do servidor que nunca deveriam ser "
        "entregues, como configurações e senhas."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_DEV, "Não montar caminho de arquivo com texto recebido; aceitar só nomes de uma lista."),
        (_DEV, "Conferir que o caminho final continua dentro da pasta permitida."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Travessia de caminho (Path Traversal, CWE-22)",
)

_XSS = FindingExplanation(
    key="xss",
    title="Um texto digitado volta na página como se fosse parte dela",
    what_happened=(
        "O teste enviou um texto com marcas de página (como `<script>`) e ele voltou na "
        "resposta sem ser neutralizado, de modo que o navegador poderia tratá-lo como código."
    ),
    why_it_matters=(
        "Se isso for real, um texto malicioso pode rodar no navegador de outra pessoa que "
        "abra a página, e agir em nome dela."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_DEV, "Neutralizar o texto digitado antes de mostrá-lo e validar formato e tamanho."),
        (_DEV, "Responder com o tipo de conteúdo correto, para o navegador não adivinhar."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Script entre sites (Cross-Site Scripting, XSS, CWE-79)",
)

_OS_COMMAND = FindingExplanation(
    key="os_command_injection",
    title="Um texto digitado pode estar virando comando no servidor",
    what_happened=(
        "O teste enviou um texto com um comando do sistema operacional e a resposta indica "
        "que o servidor pode ter executado esse comando."
    ),
    why_it_matters=(
        "Se isso for real, é uma das falhas mais graves: quem explora controla o que o "
        "servidor executa."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_DEV, "Parar de passar texto recebido para comandos do sistema."),
        (_DEV, "Se for inevitável, aceitar só valores de uma lista fechada."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Injeção de comando do sistema (CWE-78)",
)

_CODE_INJECTION = FindingExplanation(
    key="code_injection",
    title="Um texto digitado pode estar sendo executado como código pelo sistema",
    what_happened=(
        "O teste enviou um texto que parece código e a resposta indica que o sistema pode "
        "tê-lo interpretado em vez de tratá-lo só como dado."
    ),
    why_it_matters=(
        "Se isso for real, quem explora consegue fazer o sistema executar o que quiser, com "
        "as permissões dele."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_DEV, "Tratar todo texto recebido como dado e nunca como código ou modelo de página."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Injeção de código (CWE-94)",
)

_XXE = FindingExplanation(
    key="xml_external_entity",
    title="O sistema pode estar lendo referências externas escondidas em arquivos XML",
    what_happened=(
        "O teste enviou um arquivo XML com uma referência a um recurso de fora e a resposta "
        "indica que o sistema pode ter tentado buscá-lo."
    ),
    why_it_matters=(
        "Se isso for real, alguém pode usar o sistema para ler arquivos internos ou alcançar "
        "outros sistemas da rede."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_DEV, "Desligar referências externas e definições de tipo na leitura de XML."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Entidade externa de XML (XXE, CWE-611)",
)

_SSRF = FindingExplanation(
    key="server_side_request_forgery",
    title="O sistema pode estar acessando endereços escolhidos por quem chama",
    what_happened=(
        "O teste passou um endereço de teste num campo e a resposta indica que o próprio "
        "servidor pode ter feito um pedido a esse endereço."
    ),
    why_it_matters=(
        "Se isso for real, o servidor pode ser usado para alcançar sistemas internos que não "
        "ficam abertos para fora."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_DEV, "Aceitar só destinos de uma lista permitida e recusar endereços internos."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Requisição forjada no servidor (SSRF, CWE-918)",
)

_CSRF = FindingExplanation(
    key="csrf",
    title="Uma ação do sistema pode ser disparada de fora por quem estiver logado",
    what_happened=(
        "A página ou a ação não traz um código de proteção que prove que o pedido saiu do "
        "próprio sistema."
    ),
    why_it_matters=(
        "Se isso for real, um site malicioso pode fazer o navegador de uma pessoa logada "
        "executar uma ação sem que ela perceba."
    ),
    what_to_do=_steps(
        (_QA, "Conferir com o time se a ação usa login por cookie (um arquivo do navegador)."),
        (_DEV, "Exigir um código de proteção por pedido nas ações que alteram dados."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Falsificação de pedido entre sites (CSRF, CWE-352)",
)

_REDIRECT = FindingExplanation(
    key="open_redirect",
    title="O sistema pode mandar a pessoa para um endereço escolhido por quem chama",
    what_happened=(
        "O teste trocou o endereço de destino de um redirecionamento e a resposta indica "
        "que o sistema aceitou mandar a pessoa para fora."
    ),
    why_it_matters=(
        "Se isso for real, um link com a aparência do sistema pode levar a pessoa a um site falso."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_DEV, "Redirecionar só para destinos de uma lista conhecida."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Redirecionamento aberto (CWE-601)",
)

_CORS = FindingExplanation(
    key="cors_misconfiguration",
    title="O sistema deixa sites de fora ler as respostas dele",
    what_happened=(
        "A resposta diz ao navegador que páginas de qualquer origem, ou de uma origem "
        "escolhida pelo pedido, podem ler o conteúdo devolvido."
    ),
    why_it_matters=(
        "Se isso for real, uma página de outro site pode ler dados da pessoa logada no sistema."
    ),
    what_to_do=_steps(
        (_QA, "Perguntar ao time quais sites precisam mesmo ler as respostas."),
        (_DEV, "Liberar só essas origens, e não usar o curinga `*` onde há login."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Compartilhamento entre origens mal configurado (CORS, CWE-942)",
)

_COOKIE_HTTPONLY = FindingExplanation(
    key="cookie_no_httponly",
    title="Um cookie pode ser lido por scripts da página",
    what_happened=(
        "O sistema devolveu um cookie (um pequeno arquivo que o navegador guarda) sem a "
        "marca que o esconde dos scripts da página."
    ),
    why_it_matters=(
        "Se o cookie for o da sessão, uma falha que rode script na página poderia roubá-lo. "
        "Cookie que a própria página precisa ler, como o de proteção contra pedidos "
        "forjados, costuma ser assim de propósito."
    ),
    what_to_do=_steps(
        (_QA, "Anotar o nome do cookie e perguntar ao time se a página precisa lê-lo."),
        (_DEV, "Marcar como ocultos para scripts os cookies que a página não precisa ler."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Cookie sem HttpOnly (CWE-1004)",
)

_COOKIE_SECURE = FindingExplanation(
    key="cookie_no_secure",
    title="Um cookie pode viajar por conexão sem proteção",
    what_happened=(
        "O sistema devolveu um cookie (um pequeno arquivo que o navegador guarda) sem a "
        "marca que o limita a conexões protegidas."
    ),
    why_it_matters=(
        "Se o sistema também atender por conexão sem proteção, o cookie pode ser visto por "
        "quem estiver na mesma rede."
    ),
    what_to_do=_steps(
        (_QA, "Perguntar ao time se o sistema é acessado só por conexão protegida."),
        (_DEV, "Marcar os cookies para viajar só por conexão protegida."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Cookie sem Secure (CWE-614)",
)

_COOKIE_SAMESITE = FindingExplanation(
    key="cookie_no_samesite",
    title="Um cookie não limita em quais situações o navegador o envia",
    what_happened=(
        "O sistema devolveu um cookie (um pequeno arquivo que o navegador guarda) sem dizer "
        "se ele pode ser enviado em pedidos que partem de outros sites."
    ),
    why_it_matters=("Isso facilita que um site de fora provoque ações em nome da pessoa logada."),
    what_to_do=_steps(
        (_DEV, "Definir a regra de envio do cookie entre sites (SameSite) nos cookies de sessão."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Cookie sem SameSite (CWE-1275)",
)

_NOSNIFF = FindingExplanation(
    key="missing_nosniff",
    title="O navegador pode interpretar uma resposta de um jeito que o sistema não previu",
    what_happened=(
        "As respostas do sistema não trazem a instrução que manda o navegador respeitar o "
        "tipo de conteúdo informado, sem tentar adivinhar."
    ),
    why_it_matters=(
        "É uma proteção extra e costuma ser de baixa gravidade; sozinha não abre acesso a "
        "dados, mas facilita outros problemas."
    ),
    what_to_do=_steps(
        (_QA, "Anotar que o aviso se repete em várias funções: costuma ser uma configuração só."),
        (_DEV, "Ligar a instrução `X-Content-Type-Options: nosniff` em todas as respostas."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Cabeçalho X-Content-Type-Options ausente (CWE-693)",
)

_CSP = FindingExplanation(
    key="missing_csp",
    title="Falta a regra que limita o que a página pode carregar",
    what_happened=(
        "As respostas não trazem a política que diz ao navegador de onde a página pode "
        "carregar scripts e imagens."
    ),
    why_it_matters=(
        "É uma proteção extra: ela reduz o estrago se outra falha deixar rodar um script indevido."
    ),
    what_to_do=_steps(
        (_DEV, "Definir uma política de conteúdo (Content-Security-Policy) adequada ao sistema."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Política de segurança de conteúdo ausente (CSP, CWE-693)",
)

_CLICKJACKING = FindingExplanation(
    key="missing_clickjacking_protection",
    title="A página pode ser escondida dentro de outra para enganar quem clica",
    what_happened=(
        "As respostas não impedem que outro site as mostre dentro de um quadro invisível."
    ),
    why_it_matters=(
        "Se isso for real, um site falso pode levar a pessoa a clicar em botões do sistema "
        "sem perceber."
    ),
    what_to_do=_steps(
        (_DEV, "Impedir que as páginas sejam abertas dentro de quadros de outros sites."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Proteção contra clickjacking ausente (CWE-1021)",
)

_HSTS = FindingExplanation(
    key="missing_hsts",
    title="O sistema não obriga o navegador a usar sempre a conexão protegida",
    what_happened=(
        "As respostas não trazem a instrução que manda o navegador usar só conexão "
        "protegida com este sistema."
    ),
    why_it_matters=(
        "Sem ela, uma pessoa numa rede aberta pode ser levada a usar uma conexão sem "
        "proteção na primeira visita."
    ),
    what_to_do=_steps(
        (_QA, "Conferir com o time se o sistema deve ser acessado só por conexão protegida."),
        (_DEV, "Ligar a instrução Strict-Transport-Security nas respostas."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Cabeçalho Strict-Transport-Security ausente (HSTS, CWE-319)",
)

_CACHE = FindingExplanation(
    key="cache_control",
    title="Respostas podem ficar guardadas no navegador ou em intermediários",
    what_happened=(
        "As respostas não dizem de forma clara se podem ser guardadas para uso posterior."
    ),
    why_it_matters=(
        "Se a resposta tiver dado pessoal, outra pessoa que use o mesmo computador ou "
        "intermediário poderia vê-la."
    ),
    what_to_do=_steps(
        (_QA, "Anotar quais respostas têm dado pessoal."),
        (_DEV, "Marcar essas respostas para não serem guardadas (Cache-Control)."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Controle de cache inadequado (CWE-525)",
)

_VERSION_LEAK = FindingExplanation(
    key="server_version_leak",
    title="O sistema revela qual programa e qual versão roda no servidor",
    what_happened=(
        "As respostas trazem o nome ou a versão do programa do servidor, num campo que "
        "ninguém precisa ver."
    ),
    why_it_matters=(
        "Quem procura falhas conhecidas usa essa informação para escolher o ataque. Por si "
        "só não abre acesso."
    ),
    what_to_do=_steps(
        (_DEV, "Remover ou esconder as informações de versão das respostas."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Vazamento de versão do servidor (CWE-200)",
)

_ERROR_DISCLOSURE = FindingExplanation(
    key="error_disclosure",
    title="Quando algo dá errado, o sistema mostra detalhes internos",
    what_happened=(
        "Uma resposta de erro trouxe informação interna, como o caminho de arquivos, o nome "
        "de uma tabela ou o trecho de código que falhou."
    ),
    why_it_matters=(
        "Esses detalhes ajudam quem ataca a entender como o sistema é por dentro e a "
        "escolher o próximo passo."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (
            _DEV,
            "Devolver uma mensagem de erro genérica e guardar o detalhe só no registro interno.",
        ),
        _retest(),
    ),
    who=_DEV,
    technical_name="Mensagem de erro com detalhes internos (CWE-209)",
)

_INFO_EXPOSURE = FindingExplanation(
    key="information_exposure",
    title="O sistema mostra mais informação do que o necessário",
    what_happened=(
        "A resposta trouxe uma informação que a ferramenta considera desnecessária para quem chama."
    ),
    why_it_matters=(
        "Depende do que foi mostrado: pode ser inofensivo ou pode ajudar quem ataca. Só "
        "quem conhece o sistema sabe dizer."
    ),
    what_to_do=_steps(
        (_QA, "Ler a prova e perguntar ao time se aquela informação precisa mesmo aparecer."),
        (_DEV, "Devolver só os campos necessários."),
        _retest(),
    ),
    who=_QA,
    technical_name="Exposição de informação (CWE-200)",
)

_MISCONFIGURATION = FindingExplanation(
    key="security_misconfiguration",
    title="Uma configuração do servidor merece revisão",
    what_happened=(
        "A ferramenta encontrou uma configuração do servidor ou das respostas que foge do "
        "que costuma ser recomendado."
    ),
    why_it_matters=(
        "Configuração fora do recomendado costuma ser uma proteção extra que faltou; o "
        "efeito depende do caso."
    ),
    what_to_do=_steps(
        (_QA, "Ler a descrição original da ferramenta, que aparece junto da falha."),
        (_DEV, "Revisar a configuração apontada e decidir se precisa mudar."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Configuração fora do recomendado (CWE-16 e CWE-693)",
)

_AUTH_REQUEST = FindingExplanation(
    key="authentication_request_identified",
    title="A ferramenta reconheceu o pedido de login do sistema",
    what_happened=(
        "Durante o teste, a ferramenta identificou qual pedido faz o login. É só um registro "
        "do que ela viu."
    ),
    why_it_matters=(
        "Não é uma falha: é informativo. Serve para conferir se o login foi entendido do "
        "jeito certo."
    ),
    what_to_do=_steps(
        (_QA, "Nenhuma ação é necessária; use só para conferência."),
    ),
    who=_QA,
    technical_name="Pedido de autenticação identificado (informativo)",
)

_SESSION_RESPONSE = FindingExplanation(
    key="session_response_identified",
    title="A ferramenta reconheceu como o sistema mantém a pessoa logada",
    what_happened=(
        "Durante o teste, a ferramenta identificou a resposta que carrega a sessão da "
        "pessoa. É só um registro do que ela viu."
    ),
    why_it_matters=(
        "Não é uma falha: é informativo. Aparece em várias funções porque todas usam a "
        "mesma sessão."
    ),
    what_to_do=_steps(
        (_QA, "Nenhuma ação é necessária; use só para conferência."),
    ),
    who=_QA,
    technical_name="Resposta de gerenciamento de sessão identificada (informativo)",
)

_AUTHZ_HORIZONTAL = FindingExplanation(
    key="authz_horizontal",
    title="Uma pessoa consegue ver dados que pertencem a outra pessoa do mesmo tipo de conta",
    what_happened=(
        "O teste repetiu, com outra conta do mesmo papel, o pedido que a primeira conta fez, "
        "trocando só o identificador do dado. A outra conta recebeu o mesmo conteúdo."
    ),
    why_it_matters=(
        "Se isso for real, qualquer pessoa com login consegue ler os dados de todas as "
        "outras, bastando mudar o número no endereço."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_DEV, "Conferir no servidor que o dado pertence a quem pede antes de devolvê-lo."),
        (_OWNER, "Avaliar se houve acesso indevido real e se é preciso avisar alguém."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Acesso indevido a dado de outra conta (BOLA, IDOR, CWE-639)",
)

_AUTHZ_HORIZONTAL_WRITE = FindingExplanation(
    key="authz_horizontal_write",
    title="Uma pessoa consegue alterar dados que pertencem a outra pessoa do mesmo tipo de conta",
    what_happened=(
        "O teste mandou, com outra conta do mesmo papel, a gravação que a primeira conta fez, "
        "trocando só o identificador do dado e um campo. A primeira conta leu depois e o campo "
        "tinha mudado."
    ),
    why_it_matters=(
        "Se isso for real, qualquer pessoa com login consegue alterar os dados de todas as "
        "outras, bastando mudar o número no endereço."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_DEV, "Conferir no servidor que o dado pertence a quem grava antes de salvar."),
        (_OWNER, "Conferir no ambiente de teste se o valor foi mesmo restaurado."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Alteração indevida de dado de outra conta (BOLA, IDOR, CWE-639)",
)

_AUTHZ_VERTICAL = FindingExplanation(
    key="authz_vertical",
    title="Uma conta comum consegue fazer uma função reservada a um papel maior",
    what_happened=(
        "O teste repetiu, com uma conta de papel menor, um pedido que o perfil reserva a um "
        "papel maior. O sistema aceitou."
    ),
    why_it_matters=(
        "Se isso for real, quem tem uma conta comum consegue executar funções de administração."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_OWNER, "Confirmar quais papéis podem usar essa função."),
        (_DEV, "Exigir o papel necessário na própria função e recusar os demais."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Acesso indevido a função de outro papel (BFLA, CWE-285)",
)

_AUTHZ_ACCESS_MATRIX = FindingExplanation(
    key="authz_access_matrix",
    title="Um tipo de conta que a tabela proíbe conseguiu fazer a função",
    what_happened=(
        "O dono do produto escreveu, na tabela quem pode o quê, que um tipo de conta não pode "
        "usar esta função. O teste repetiu o pedido com uma conta desse tipo e o sistema o "
        "aceitou (ou o teste anterior já tinha mostrado isso)."
    ),
    why_it_matters=(
        "Se isso for real, quem tem esse tipo de conta consegue executar uma função que o "
        "próprio dono do produto disse que não deveria estar ao alcance dele."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_OWNER, "Conferir se a tabela está certa para esta função e este tipo de conta."),
        (_DEV, "Exigir o papel necessário na própria função e recusar os demais."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Acesso indevido a função de outro papel (BFLA, CWE-285), pela tabela",
)

_AUTHZ_EXCESSIVE = FindingExplanation(
    key="authz_excessive_data",
    title="O sistema devolve campos que a documentação dele não prevê",
    what_happened=(
        "A resposta trouxe campos que não constam no Swagger do sistema. O teste guarda só "
        "os nomes dos campos, nunca os valores."
    ),
    why_it_matters=(
        "Se os campos forem internos ou pessoais (como senha ou observações internas), "
        "chegam a quem não deveria vê-los."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_OWNER, "Dizer se esses campos podem mesmo aparecer para quem chama."),
        (_DEV, "Devolver só os campos previstos, por meio de um modelo de resposta próprio."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Exposição excessiva de dados (CWE-213)",
)

_AUTHZ_MASS = FindingExplanation(
    key="authz_mass_assignment",
    title="O sistema aceita um campo que a pessoa não deveria poder mudar",
    what_happened=(
        "O teste mandou um campo extra, que o Swagger não prevê para quem chama, e o sistema "
        "o aceitou. O campo vinha da lista do perfil ou do próprio Swagger (campo que só aparece "
        "na resposta, marcado como somente leitura ou com nome de privilégio); o achado diz de "
        "onde. O teste guarda só o nome do campo. Num cadastro, o recurso criado fica no "
        "ambiente de teste."
    ),
    why_it_matters=(
        "Se o campo for sensível (como o papel da conta), uma pessoa pode dar a si mesma "
        "permissões que não tem."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_DEV, "Aceitar só os campos previstos e ignorar ou recusar o resto."),
        (_QA, "Conferir, com o time, se o ambiente de teste foi restaurado depois do teste."),
        (_QA, "Apagar os recursos que o teste de cadastro criou (`hdast cleanup` ou o reset)."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Atribuição em massa (Mass Assignment, CWE-915)",
)

_AUTHZ_CORS = FindingExplanation(
    key="authz_cors",
    title="A política CORS permite acesso de outras origens",
    what_happened="Uma origem de teste recebeu permissão de acesso à resposta.",
    why_it_matters="Um site externo pode ler dados expostos conforme a política observada.",
    what_to_do=_steps(
        _open_ticket(),
        (_DEV, "Limitar origens confiáveis e o uso de credenciais."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Configuração CORS permissiva (CWE-942)",
)

_AUTHZ_ANONYMOUS = FindingExplanation(
    key="authz_anonymous_access",
    title="O sistema responde a quem não fez login",
    what_happened=(
        "O teste repetiu um pedido de leitura sem enviar nenhuma credencial e o sistema "
        "devolveu o mesmo conteúdo que entregou a quem estava logado."
    ),
    why_it_matters=(
        "Se a função devia ser protegida, qualquer pessoa na internet (ou na rede) lê esses "
        "dados sem precisar de conta. Se ela é pública de propósito, é só registrar isso."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_OWNER, "Dizer se essa função deve ser pública; se for, registrá-la como pública."),
        (_DEV, "Exigir login na função e responder 401 a quem não enviou credencial válida."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Acesso sem autenticação (Broken Authentication, CWE-306)",
)

_AUTHZ_TAMPERED = FindingExplanation(
    key="authz_tampered_token",
    title="O sistema aceita uma credencial de login que foi estragada de propósito",
    what_happened=(
        "O teste pegou a credencial de uma conta, tirou ou estragou a parte que a protege "
        "(a assinatura, ou o próprio texto) e repetiu um pedido de leitura. O sistema aceitou. "
        "A credencial estragada nunca é gravada."
    ),
    why_it_matters=(
        "Se o sistema não confere a credencial de verdade, qualquer pessoa consegue fabricar "
        "uma e entrar como outra."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (_DEV, "Conferir a assinatura e o algoritmo da credencial em toda requisição."),
        (_DEV, "Recusar credencial sem assinatura ou com algoritmo none, com resposta 401."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Token adulterado aceito (Broken Authentication, CWE-347 ou CWE-287)",
)

_SQL_TIME = FindingExplanation(
    key="sql_injection_time",
    title="Um texto digitado pode estar virando parte do comando que o sistema manda ao banco",
    what_happened=(
        "O teste mandou um texto montado de propósito que, se virasse parte do comando do banco "
        "de dados, o faria esperar alguns segundos. A ferramenta de ataque anotou que a resposta "
        "demorou. A resposta gravada não mostra a falha: o que indica é só a demora, e demora "
        "também acontece por acaso."
    ),
    why_it_matters=(
        "Se isso for real, quem souber montar o texto certo consegue mudar o comando do banco: "
        "ler dados de outras pessoas ou alterar informações sem ter permissão."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (
            _QA,
            "Repetir o pedido à mão 3 vezes, medindo o tempo de cada uma, como mostra o passo "
            "a passo desta falha.",
        ),
        (_DEV, "Montar o comando do banco com parâmetros, nunca juntando o texto digitado."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Injeção de SQL por tempo (Time Based, CWE-89)",
)

_OS_COMMAND_TIME = FindingExplanation(
    key="os_command_injection_time",
    title="Um texto digitado pode estar virando comando no servidor",
    what_happened=(
        "O teste mandou um texto com um comando do sistema operacional que faria o servidor "
        "esperar alguns segundos. A ferramenta de ataque anotou que a resposta demorou. A "
        "resposta gravada não mostra a falha: o que indica é só a demora, e demora também "
        "acontece por acaso."
    ),
    why_it_matters=(
        "Se isso for real, é uma das falhas mais graves: quem explora controla o que o "
        "servidor executa."
    ),
    what_to_do=_steps(
        _open_ticket(),
        (
            _QA,
            "Repetir o pedido à mão 3 vezes, medindo o tempo de cada uma, como mostra o passo "
            "a passo desta falha.",
        ),
        (_DEV, "Parar de passar texto recebido para comandos do sistema."),
        _retest(),
    ),
    who=_DEV,
    technical_name="Injeção de comando do sistema por tempo (Time Based, CWE-78)",
)

_TIME_VARIANT: Final[dict[str, FindingExplanation]] = {
    "sql_injection": _SQL_TIME,
    "os_command_injection": _OS_COMMAND_TIME,
}
"""Variante "por tempo" de cada tipo: a prova é a demora, e o corpo da resposta não a mostra."""

_SQL_PLUGINS: Final = frozenset(
    {"40018", "40019", "40020", "40021", "40022", "40024", "40027", "90018"}
)

# Regra do ZAP -> entrada. A busca começa por aqui; o CWE só vale se a regra não casar.
_BY_PLUGIN: Final[dict[str, FindingExplanation]] = {
    **dict.fromkeys(_SQL_PLUGINS, _SQL),
    "6": _PATH,
    **dict.fromkeys(("40012", "40014", "40016", "40017", "40026"), _XSS),
    "90020": _OS_COMMAND,
    "90019": _CODE_INJECTION,
    "90023": _XXE,
    "40046": _SSRF,
    "10202": _CSRF,
    "20012": _CSRF,
    "20019": _REDIRECT,
    "40040": _CORS,
    "10098": _CORS,
    "10010": _COOKIE_HTTPONLY,
    "10011": _COOKIE_SECURE,
    "10054": _COOKIE_SAMESITE,
    "10021": _NOSNIFF,
    "10038": _CSP,
    "10020": _CLICKJACKING,
    "10035": _HSTS,
    "10015": _CACHE,
    "10036": _VERSION_LEAK,
    "10037": _VERSION_LEAK,
    "90022": _ERROR_DISCLOSURE,
    "10111": _AUTH_REQUEST,
    "10112": _SESSION_RESPONSE,
}

_BY_CWE: Final[dict[int, FindingExplanation]] = {
    89: _SQL,
    22: _PATH,
    79: _XSS,
    78: _OS_COMMAND,
    94: _CODE_INJECTION,
    611: _XXE,
    918: _SSRF,
    352: _CSRF,
    601: _REDIRECT,
    942: _CORS,
    1004: _COOKIE_HTTPONLY,
    614: _COOKIE_SECURE,
    1275: _COOKIE_SAMESITE,
    1021: _CLICKJACKING,
    319: _HSTS,
    525: _CACHE,
    209: _ERROR_DISCLOSURE,
    200: _INFO_EXPOSURE,
    693: _MISCONFIGURATION,
    16: _MISCONFIGURATION,
}

_BY_TECHNIQUE: Final[dict[AuthzTechnique, FindingExplanation]] = {
    "authz_horizontal": _AUTHZ_HORIZONTAL,
    "authz_horizontal_write": _AUTHZ_HORIZONTAL_WRITE,
    "authz_vertical": _AUTHZ_VERTICAL,
    "authz_access_matrix": _AUTHZ_ACCESS_MATRIX,
    "authz_excessive_data": _AUTHZ_EXCESSIVE,
    "authz_mass_assignment": _AUTHZ_MASS,
    "authz_cors": _AUTHZ_CORS,
    "authz_anonymous_access": _AUTHZ_ANONYMOUS,
    "authz_tampered_token": _AUTHZ_TAMPERED,
}


def catalog_entries() -> tuple[FindingExplanation, ...]:
    """Todas as entradas distintas do catálogo (sem a genérica), em ordem estável."""
    seen: dict[str, FindingExplanation] = {}
    every = (
        *_BY_PLUGIN.values(),
        *_BY_CWE.values(),
        *_BY_TECHNIQUE.values(),
        *_TIME_VARIANT.values(),
    )
    for entry in every:
        seen.setdefault(entry.key, entry)
    return tuple(seen.values())


def _generic(name: str, rule: str) -> FindingExplanation:
    clean = strip_control(name, keep_newlines=False).strip()
    shown = clean if len(clean) <= _TITLE_CAP else clean[: _TITLE_CAP - 1] + "…"
    shown = shown or "um item sem nome"
    rule_label = rule if _RULE_ID.fullmatch(rule) else "desconhecida"
    return FindingExplanation(
        key=GENERIC_KEY,
        known=False,
        title=f"A ferramenta apontou: {shown}",
        what_happened=(
            f"A ferramenta apontou «{shown}»; não temos explicação simples para este tipo. "
            "Leia a descrição original dela, que aparece junto da falha."
        ),
        why_it_matters=(
            "Sem uma explicação conhecida, não dá para dizer o quanto isso importa para o "
            "seu sistema. A gravidade mostrada é a que a própria ferramenta propôs."
        ),
        what_to_do=_steps(
            (_QA, "Ler a descrição e a solução originais que a ferramenta trouxe."),
            (_QA, "Levar a falha ao time de desenvolvimento para uma avaliação."),
        ),
        who=_QA,
        technical_name=f"{shown} (regra {rule_label})",
    )


def explain_zap_alert(*, plugin_id: str, cwe: int | None, title: str) -> FindingExplanation:
    """Explicação de uma falha apontada pelo ZAP.

    A busca vai da regra (`plugin_id`) para o CWE. Sem nenhum dos dois no catálogo, devolve a
    explicação genérica e honesta (`known=False`), que cita só o nome da regra (limpo e cortado).

    Args:
        plugin_id: Regra do ZAP.
        cwe: CWE do achado, se houver.
        title: Nome do alerta; só aparece na explicação genérica.

    Returns:
        A explicação. Nunca altera severidade, confiança nem status do achado.
    """
    entry = _BY_PLUGIN.get(plugin_id.strip())
    if entry is None and cwe is not None:
        entry = _BY_CWE.get(cwe)
    if entry is None:
        return _generic(title, plugin_id.strip())
    return _TIME_VARIANT.get(entry.key, entry) if is_time_based(title) else entry


def explain_authz_technique(technique: AuthzTechnique) -> FindingExplanation:
    """Explicação de uma técnica do teste de autorização entre contas."""
    return _BY_TECHNIQUE[technique]


def explain_finding(finding: Finding) -> FindingExplanation:
    """Atalho: explica um achado do ZAP pela regra, CWE e título dele."""
    return explain_zap_alert(
        plugin_id=finding.plugin_id, cwe=finding.classification.cwe, title=finding.title
    )
