#!/usr/bin/env bash
# Prepara um commit e tag de release localmente. Não faz push de nada.
#
#   tools/prepare-release.sh [VERSION]
#
# A VERSION padrão é o que tools/next-version.sh diz que o SemVer pede. Se uma
# for fornecida e discordar, o script para e explica o porquê: a versão é a
# decisão do mantenedor, mas uma divergência precisa ser uma decisão, não um acidente.
# Use FORCE_VERSION=1 para prosseguir com uma versão que discorda.
#
# Escreva a entrada de changelog da versão em templates/index.html primeiro; o
# script se recusa a lançar sem ela. Depois: revise e então siga as
# etapas de publicação em CONTRIBUTING.md.
set -euo pipefail
cd "$(dirname "$0")/.."

WANT="${1:-}"
[ -z "$(git status --porcelain --untracked-files=no -- . ':!templates/index.html')" ] \
    || { echo "A árvore de trabalho tem alterações não commitadas além do changelog." >&2; exit 1; }
[ "$(git config core.hooksPath)" = "tools/git-hooks" ] || { echo "Execute: git config core.hooksPath tools/git-hooks" >&2; exit 1; }
[ "$(git symbolic-ref --short HEAD)" = main ] || { echo "Um release sai da main." >&2; exit 1; }

SUGGESTED=$(tools/next-version.sh)
VERSION="${WANT:-$SUGGESTED}"
if [ "$VERSION" != "$SUGGESTED" ] && [ "${FORCE_VERSION:-0}" != 1 ]; then
    echo "O SemVer pede $SUGGESTED, não $VERSION. Os commits que decidem:" >&2
    tools/next-version.sh --why >/dev/null || true
    echo "Rode novamente com FORCE_VERSION=1 se $VERSION for deliberado." >&2
    exit 1
fi
[[ "$VERSION" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || { echo "'$VERSION' não é X.Y.Z." >&2; exit 1; }
if git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null; then
    echo "v$VERSION já existe." >&2
    exit 1
fi
tools/release-notes.sh "$VERSION" >/dev/null

sed -i "s/^APP_VERSION = '.*'/APP_VERSION = '$VERSION'/" app.py
sed -i "s/^LABEL org.opencontainers.image.version=\".*\"/LABEL org.opencontainers.image.version=\"$VERSION\"/" Dockerfile
sed -i "s/^Versão atual: \*\*.*\*\*/Versão atual: **$VERSION**/" README.md

git add app.py Dockerfile README.md templates/index.html
git commit -q -m "chore(release): $VERSION"
git tag -a "v$VERSION" -m "$VERSION"
echo
echo "==> v$VERSION commitado e marcado na main. Nada foi enviado."
echo "    Revise: git show --stat HEAD && tools/release-notes.sh $VERSION"
echo "    Depois siga \"Lançamento (releasing)\" em CONTRIBUTING.md."
