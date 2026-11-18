# Abertura do README: a ajuda e o diagnóstico, gravados ao vivo pelo VHS.
# Execute a partir de docs/media: vhs demo.tape. Nenhum dos dois comandos toca alvo.
# A demonstração (hdast demo) NÃO entra aqui: ela pede aprovação digitada, e só uma
# pessoa aprova. Grave essa parte você mesmo, como explica docs/media/README.md.

Output demo.gif
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

Type "uv run hdast --help"
Enter
Sleep 6s

Type "clear && uv run hdast doctor"
Enter
Sleep 8s
