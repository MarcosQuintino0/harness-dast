# Reteste ao vivo de uma execução anterior do VAmPI local.
# Antes de gravar:
#   1. tenha o perfil vampi aprovado por você (hdast profile approve vampi) e a pilha de pé;
#   2. troque <RUN_ID> pelo run_id de uma execução anterior com achados.
# Execute a partir de docs/media: vhs retestar.tape. O retestar não pede aprovação: ele usa
# a aprovação que você já deu e todos os controles do run.

Output retestar.gif
Require uv

Set Shell "bash"
Set Width 1200
Set Height 1150
Set FontSize 16
Set Theme "Dracula"
Set TypingSpeed 55ms

Sleep 1500ms
Hide
Type "cd ../.. && clear"
Enter
Sleep 500ms
Show

Type "uv run hdast retestar vampi --run <RUN_ID> --max 3 --max-minutes 6"
Enter
Wait+Screen@15m /saída|Reteste/
Sleep 8s
