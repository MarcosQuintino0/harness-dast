# Vídeo de apresentação

Projeto [Remotion](https://www.remotion.dev/) que gera o vídeo de abertura do README (`docs/media/apresentacao.gif` e `docs/media/apresentacao.mp4`). Não faz parte da CLI nem dos gates do projeto.

## Usar

```bash
npm install
npm run dev
```

O `npm run dev` abre o Remotion Studio para ajustar textos e tempos. Para gerar os arquivos do README:

```bash
npx remotion render Apresentacao ../docs/media/apresentacao.mp4 --crf=30
npx remotion render Apresentacao ../docs/media/apresentacao.gif --codec=gif --every-nth-frame=4 --scale=0.4
```

## O que é real e o que é recriação

- `public/real/` tem capturas do painel de uma execução no laboratório (Clínica Piloto, dados sintéticos).
- `public/painel/live.png` é a tela "Ao vivo" do protótipo em `docs/desenvolver/design/execution-panel/`. O painel gerado pela CLI não tem essa página.
- As telas do Claude Code e do terminal são desenhadas no vídeo, não gravadas.

## Licença do Remotion

O Remotion é gratuito para uso individual e para empresas de até três pessoas. Acima disso, veja a [licença](https://www.remotion.dev/docs/license).
