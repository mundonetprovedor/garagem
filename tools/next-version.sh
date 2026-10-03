#!/usr/bin/env bash
# Diz qual versão o SemVer pede, a partir dos commits desde o último release.
#
#   tools/next-version.sh           # a próxima versão
#   tools/next-version.sh --why     # também lista os commits que decidiram
#
# Os tipos de Conventional Commit decidem: um "!" ou um rodapé BREAKING CHANGE é
# MAJOR, um feat é MINOR, qualquer outra coisa (fix, perf, revert) é PATCH. Commits
# que não mudam nada que o usuário vê (docs, test, ci, style, chore, build,
# refactor) não forçam release nenhum. O CONTRIBUTING.md tem as decisões de julgamento
# que isto não consegue tomar: uma mudança de schema que uma versão antiga não consegue
# ler é MAJOR, independente de como o commit foi classificado.
set -euo pipefail
cd "$(dirname "$0")/.."

WHY=0
for arg in "$@"; do
    case "$arg" in --why) WHY=1 ;; *) echo "desconhecido: $arg" >&2; exit 1 ;; esac
done

last=$(git describe --tags --abbrev=0 --match 'v[0-9]*' --exclude 'v*-*' HEAD 2>/dev/null || true)
if [ -z "$last" ]; then
    base=$(sed -n "s/^APP_VERSION = '\(.*\)'/\1/p" app.py)
    range="HEAD"
else
    base="${last#v}"
    range="$last..HEAD"
fi
IFS=. read -r MA MI PA <<<"${base%%-*}"

log=$(git log --no-merges --format='%s%x1f%b%x1e' $range 2>/dev/null || true)
level=none
while IFS=$'\x1f' read -r -d $'\x1e' subject body; do
    subject="${subject#$'\n'}"
    [ -z "$subject" ] && continue
    type=$(printf '%s' "$subject" | sed -nE 's/^([a-z]+)(\([^)]*\))?(!?):.*/\1\3/p')
    if [[ "$type" == *'!' ]] || printf '%s' "$body" | grep -q '^BREAKING[ -]CHANGE:'; then
        this=major
    elif [ "$type" = feat ]; then
        this=minor
    elif [[ "$type" =~ ^(fix|perf|revert)$ ]]; then
        this=patch
    else
        this=none
    fi
    case "$level:$this" in
        *:major) level=major ;;
        none:minor|patch:minor) level=minor ;;
        none:patch) level=patch ;;
    esac
    [ "$WHY" = 1 ] && [ "$this" != none ] && printf '  %-5s %s\n' "$this" "$subject" >&2
done <<<"$log"

case "$level" in
    major) next="$((MA + 1)).0.0" ;;
    minor) next="$MA.$((MI + 1)).0" ;;
    patch) next="$MA.$MI.$((PA + 1))" ;;
    none)  echo "Nada desde ${last:-o início} pede um release." >&2; exit 2 ;;
esac
echo "$next"
