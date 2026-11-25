# hdast

**Uma CLI para agentes de IA operarem ferramentas de teste de segurança de API.** Você pede o teste ao agente, ele lê o Swagger e as regras de negócio do produto, monta o plano e conduz o ZAP e o Nuclei. Uma pessoa aprova o escopo antes do primeiro pedido, e a CLI não deixa nada sair dele.

<!-- O vídeo é gerado pelo projeto Remotion em video/ (veja docs/media/README.md). -->
<p align="center">
  <a href="docs/media/apresentacao.mp4">
    <img src="docs/media/apresentacao.gif" alt="Apresentação do hdast: o pedido ao agente, a varredura, o Nuclei e o painel" width="100%">
  </a>
</p>
<p align="center">
  <b>▶ <a href="docs/media/apresentacao.mp4">Assistir ao vídeo em tamanho cheio (44 s)</a></b>
</p>

> Ferramenta defensiva (repositório `harness-dast`). Use só no laboratório local ou em ambiente de teste com dados sintéticos e autorização escrita do dono do produto. [Aviso de uso autorizado](#aviso-de-uso-autorizado)

## Índice

- [Como funciona](#como-funciona)
- [O que ele encontra](#o-que-ele-encontra)
- [Ver funcionando em 3 passos](#ver-funcionando-em-3-passos)
- [Testar o seu produto](#testar-o-seu-produto)
- [Achar, corrigir, retestar](#achar-corrigir-retestar)
- [Por que dá para confiar](#por-que-dá-para-confiar)
- [Documentação](#documentação)

## Como funciona

| Etapa | Quem faz | O que acontece |
| --- | --- | --- |
| 1. Pedido | Você | Pede o teste ao agente no Claude Code e indica o Swagger, as contas de teste e a carta de autorização. |
| 2. Plano | Agente | As skills ensinam o passo a passo. O agente lê o Swagger e as regras de negócio e prepara o perfil de teste pela CLI. |
| 3. Aprovação | Você | Confere o resumo e aprova o escopo no seu terminal. Sem isso, nenhum comando toca o alvo. |
| 4. Ataque | CLI, ZAP e Nuclei | A CLI conduz a varredura do ZAP, o teste de acesso entre contas e, se a carta ligar, o Nuclei. Cada pedido passa pela cerca de escopo. |
| 5. Resultado | CLI | Gera o relatório e o painel, com cada falha explicada, a prova e o passo a passo para repetir. |

O agente só age por comandos `hdast`. As regras, as validações e as travas ficam no código da CLI, não no prompt.

## O que ele encontra

Falhas plantadas nos alvos do laboratório que a regressão dirigida confere a cada versão:

| Tipo de falha | Em linguagem simples | No laboratório |
| --- | --- | --- |
| Injeção de SQL, inclusive a que só aparece pelo tempo de resposta | Alguém lê o banco de dados pela URL | Clínica Piloto (H1, H8, H10) e VAmPI (V1) |
| Travessia de caminho | Alguém baixa arquivos do servidor que não deveria ver | Clínica Piloto (H4, H9) |
| Acesso a objeto de outra conta (BOLA) | Um usuário vê os dados de outro | Clínica Piloto (H5) e VAmPI (V3) |
| Atribuição em massa | Um usuário altera campos que não deveria poder alterar | Clínica Piloto (H6) |
| Exposição excessiva de dados | A resposta traz campos internos, como o hash da senha | Clínica Piloto (H7) |
| Erro 500 com detalhe interno | O erro revela como o sistema é por dentro | Clínica Piloto (H2) |
| Cabeçalhos de segurança ausentes e CORS permissivo | Outros sites conseguem ler respostas da API | Clínica Piloto (H3) |

Isso é prova de laboratório, não de produto real. [Varredura](docs/referencia/scan.md) · [Escada de testes](docs/desenvolver/escada-de-testes.md)

- **ZAP:** ataca cada operação do Swagger. [Uso do ZAP](docs/referencia/uso-do-zap.md)
- **Nuclei:** segundo motor, procura falhas já conhecidas e configurações expostas. Só roda quando a carta o liga. [ADR 0122](docs/decisoes/0122-nuclei-como-segundo-motor.md)
- **Acesso entre contas:** o `run` já inclui `authz` por padrão e aceita `--authz`. A verificação entre contas do mesmo papel exige duas contas do mesmo papel. [Autorização entre contas](docs/referencia/authz.md)

[Cobertura e limites de prova](docs/roadmap.md#estado-atual)

## Ver funcionando em 3 passos

1. Com Git e `uv` instalados, clone o repositório e rode `uv sync --locked` na raiz. [Instalar a CLI](docs/comecar/instalar.md)
2. Inicie o Docker. Use `uv run hdast stack pull` quando as imagens do ZAP e do proxy estiverem no GHCR. Enquanto aguardam publicação, faça o build local. Prepare também a imagem do VAmPI e as auxiliares, depois rode `uv run hdast doctor`. [Preparar as imagens da demo](docs/comecar/docker.md#preparar-as-imagens-da-demo)
3. No seu terminal, rode `uv run hdast demo`. Leia o resumo e digite `demo` para aprovar o VAmPI local. Ao final, a CLI mostra onde abrir o relatório HTML, se ele foi gerado. [Primeiro uso](docs/comecar/primeiro-uso.md)

A ajuda `uv run hdast --help` reúne os comandos iniciais no painel **Comece por aqui**.

## Testar o seu produto

Abra o Claude Code na raiz do repositório e faça um pedido de cadastro.

```text
Prepare o perfil de teste de <produto> para minha revisão.
Swagger/OpenAPI em <caminho> e carta assinada em <caminho>.
Contas de teste e papéis em <lista de apelidos e papéis, sem senhas>.
Use o escopo da carta e me mostre o resumo antes de qualquer teste.
```

Quando o perfil estiver pronto, rode `uv run hdast setup <produto>` no seu terminal. O comando grava as senhas que faltam no cofre e pede que você aprove o escopo. Depois da execução autorizada, abra `runs/<run_id>/report.html` para consultar achados e lacunas de cobertura. [Cadastro do produto](docs/usar/cadastrar-um-produto.md) · [Carta curta](docs/usar/carta-curta.md)

## Achar, corrigir, retestar

Depois da correção, use `hdast retestar` para repetir as operações dos achados selecionados da execução anterior.<br>
O `retest.json` indica quais achados reapareceram, quais ficaram ausentes e quais ficaram sem teste. [Referência do reteste](docs/referencia/cli.md#hdast-retestar)

## Por que dá para confiar

- **O agente propõe, a CLI executa.** A CLI aplica as regras e os limites da carta.
- A cerca de escopo tem três camadas. A CLI usa o `ScopeGuard`, o ZAP roda em modo protegido e o proxy de saída bloqueia tráfego fora do escopo. [Como funciona a cerca](docs/como-funciona/operacao/authorization-and-scope.md)
- Uma pessoa aprova o escopo em terminal interativo antes do teste.
- O agente usa referências de credenciais, sem receber senhas nem enviar HTTP ao alvo. O hook do Claude Code reforça essas permissões. [Hook de proteção](docs/decisoes/0111-hook-pretooluse-segunda-camada.md)

## Aviso de uso autorizado

Use apenas o laboratório local ou um ambiente de teste com dados sintéticos e autorização escrita do dono do produto. Respeite o escopo, a janela e os limites de carga da carta. [Política de segurança](SECURITY.md) · [Finalidade e uso responsável](docs/como-funciona/finalidade-e-uso-responsavel.md)

## Documentação

| Quero… | Vá para |
| --- | --- |
| Instalar e conhecer o laboratório | [Começar](docs/comecar/) |
| Cadastrar um produto ou resolver um problema | [Guias de uso](docs/usar/) |
| Entender a arquitetura e as travas | [Como funciona](docs/como-funciona/) |
| Consultar comandos e formatos | [Referência](docs/referencia/) |
| Contribuir para o projeto | [Desenvolvimento](docs/desenvolver/) |
| Consultar decisões de arquitetura | [Decisões](docs/decisoes/README.md) |
| Consultar provas e revisões anteriores | [Arquivo](docs/arquivo/) |
| Navegar por toda a documentação | [Índice](docs/README.md) |

## Licença

O projeto usa a [licença MIT](LICENSE).
