#!/bin/sh
# Consultas locais com prazo, inclusive em sistemas sem o utilitário timeout.

run_bounded() (
    seconds=$1
    shift
    "$@" &
    command_pid=$!
    (
        sleep "$seconds" &
        timer_pid=$!
        trap 'kill "$timer_pid" 2>/dev/null; exit 0' TERM
        wait "$timer_pid"
        kill -KILL "$command_pid" 2>/dev/null
    ) </dev/null >/dev/null 2>&1 &
    watchdog_pid=$!
    wait "$command_pid" 2>/dev/null
    status=$?
    kill "$watchdog_pid" 2>/dev/null
    wait "$watchdog_pid" 2>/dev/null
    return "$status"
)

image_refs() (
    command -v uv >/dev/null 2>&1 || return 1
    tool_dir=$(run_bounded 1 uv tool dir) || return 1
    tool_dir=${tool_dir%"$carriage_return"}
    [ -n "$tool_dir" ] || return 1
    # O layout da venv do uv difere entre Windows e Unix.
    set -- "$tool_dir"/harness-dast/Lib/site-packages/harness_dast/adapters/docker/images.lock.json \
        "$tool_dir"/harness-dast/lib/python*/site-packages/harness_dast/adapters/docker/images.lock.json
    for lock do
        [ -f "$lock" ] || continue
        fields=$(run_bounded 1 sed -n \
            -e 's/.*"version": *"\([0-9A-Za-z_.-]*\)".*/\1/p' \
            -e 's|.*"repository": *"\([a-z0-9][a-z0-9._/:-]*\)".*|\1|p' \
            -e 's/.*"tag": *"\([0-9A-Za-z_.-]*\)".*/\1/p' \
            -e 's/.*"digest": *"\(sha256:[a-f0-9]\{64\}\)".*/\1/p' "$lock") || return 1
        # O arquivo da release declara versão, repositório, tag e digest nessa ordem.
        set -f
        set -- $fields
        [ "$#" -eq 7 ] && [ "$1" = "$version" ] &&
            [ "$3" = "$version" ] && [ "$6" = "$version" ] || return 1
        printf '%s\n' "$2:$3@$4" "$5:$6@$7"
        return 0
    done
    return 1
)

check_cli() {
    if ! command -v hdast >/dev/null 2>&1; then
        notice 'hdast não está no PATH.'
    elif ! installed=$(PYTHONDONTWRITEBYTECODE=1 run_bounded 2 hdast --version); then
        notice 'Não foi possível consultar a versão do hdast.'
    elif [ -n "$version" ] && [ "${installed%"$carriage_return"}" != "$version" ]; then
        notice 'A versão do hdast difere da versão do plugin.'
    fi
}

check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        notice 'Docker não está no PATH.'
    elif ! run_bounded 2 docker info >/dev/null; then
        notice 'Docker não responde (pode estar fechado).'
    elif ! refs=$(image_refs); then
        notice 'Imagens não verificadas: digests da versão não encontrados na instalação do uv.'
    else
        set -f
        if ! run_bounded 1 docker image inspect $refs >/dev/null; then
            notice 'Uma ou mais imagens da versão não puderam ser confirmadas no Docker local.'
        fi
        set +f
    fi
}

notice() {
    printf 'hdast: %s\n' "$1"
    missing=yes
}

exec 2>/dev/null
missing=no
carriage_return=$(printf '\r')
version=''
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    version=$(run_bounded 1 sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([0-9][0-9A-Za-z_.-]*\)".*/\1/p' \
        "$CLAUDE_PLUGIN_ROOT/.claude-plugin/plugin.json") || version=''
fi
[ -n "$version" ] ||
    notice 'Não foi possível ler a versão do plugin.'
command -v uv >/dev/null 2>&1 || notice 'uv não está no PATH.'
check_cli
check_docker

if [ "$missing" = yes ]; then
    if [ -n "$version" ]; then
        printf 'hdast: plugin versão %s.\n' "$version"
    fi
    printf '%s\n' 'Rode /hdast:preparar para resolver.'
else
    printf 'hdast: plugin versão %s, ambiente pronto.\n' "$version"
fi
exit 0
