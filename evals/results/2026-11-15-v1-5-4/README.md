# Recálculo da régua V1.5.4

A rodada Terra de 15/11 passa de **6,29 para 5,79**, com (f) de 0,75 para 0,50. A referência Sonnet passa de **9,16 para 9,16**, com (f) inalterado em 0,875. Não houve nova rodada nem alteração das evidências originais.

O script `recalcular.py` lê o `score.json` público e o `trace` sanitizado das duas rodadas externas, calcula novamente apenas o componente (f) e usa os demais componentes, custos, resultado de segurança e limite de perfil do score histórico. Não reclassifica o probe histórico: isso isola a correção de vacuidade E. O JSON registra os checks e o SHA-256 do score público utilizado; não copia diários ou evidências do alvo. O modo e o caso são os registrados no score histórico; não há leitura de arquivos lacrados. Arquivos externos permanecem somente leitura.

Reproduzir na raiz do repositório, com os dois diretórios externos nos caminhos indicados no script:

```powershell
uv run python -m evals.results.2026-11-15-v1-5-4.recalcular
```

Os quatro checks sem arquivo de achados tornam-se `null` (não aplicáveis), mas relatório, triagem válida e ambos os checks do diário continuam na média. A presença de `findings.json` vazio mantém todos os checks aplicáveis.
