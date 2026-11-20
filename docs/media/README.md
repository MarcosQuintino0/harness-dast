# Gravar o terminal

## Vídeo de apresentação do README

O `apresentacao.gif` e o `apresentacao.mp4` saem do projeto Remotion na pasta [`video/`](../../video/). A cena do painel usa capturas de uma execução no laboratório (Clínica Piloto); as telas do Claude Code, do terminal e da varredura ao vivo são recriações desenhadas no vídeo.

```bash
cd video
npm install
npx remotion render Apresentacao ../docs/media/apresentacao.mp4 --crf=30
npx remotion render Apresentacao ../docs/media/apresentacao.gif --codec=gif --every-nth-frame=4 --scale=0.4
```

Tudo aqui usa só o laboratório local (VAmPI). Nada sai da máquina.

## O que o VHS grava sozinho

O [VHS](https://github.com/charmbracelet/vhs#installation) grava um terminal a partir de um roteiro `.tape`. Ele só grava comandos que não pedem uma pessoa:

| Roteiro | O que mostra | Saída |
| --- | --- | --- |
| [`demo.tape`](demo.tape) | `hdast --help` (painel "Comece por aqui") e `hdast doctor` | `demo.gif` |
| [`retestar.tape`](retestar.tape) | `hdast retestar` sobre uma execução anterior do VAmPI | `retestar.gif` |

```bash
cd docs/media
vhs demo.tape
vhs retestar.tape
```

O `retestar.tape` precisa de duas coisas antes:
- o perfil `vampi` aprovado por você;
- o `<RUN_ID>` trocado pelo de uma execução anterior.

As instruções estão no próprio arquivo.

## O que só você grava

`hdast demo` pede que uma pessoa leia o resumo e digite `demo`. Um roteiro automático não pode fazer essa aprovação, nem fingir que fez. Grave essa parte no seu terminal:
- No Windows: abra o Terminal, aperte **Win+Alt+R** (Barra de Jogo) para começar e parar a gravação, e rode `uv run hdast demo`. O vídeo vai para `Vídeos\Capturas`.
- No macOS: use **Cmd+Shift+5** e grave a janela do terminal.

Guarde o vídeo bruto fora do repositório. A edição junta essa gravação com os GIFs e as capturas do relatório.

## Revisar antes de publicar

Confira que nenhuma gravação mostra:
- caminho pessoal;
- nome de máquina;
- token;
- endereço que não seja o do laboratório.
