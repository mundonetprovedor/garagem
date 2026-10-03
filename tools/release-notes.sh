#!/usr/bin/env bash
# Imprime o corpo do release do GitHub para uma versão.
#
#   tools/release-notes.sh 0.4.0 > /tmp/notes.md
#
# O corpo é a entrada dessa versão no changelog do app
# (templates/index.html) e nada mais, seguido, assim que a tag existir, pelos
# commits desde o release anterior e um link de comparação.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${1:?uso: tools/release-notes.sh X.Y.Z}"
TAG="v$VERSION"

python3 - "$VERSION" <<'PY'
import html, re, sys, pathlib
version = sys.argv[1]
text = pathlib.Path("templates/index.html").read_text(encoding="utf-8")
m = re.search(r'<div class="changelog-version">' + re.escape(version) + r'</div>\s*<ul>(.*?)</ul>', text, re.S)
if not m:
    sys.exit(f"templates/index.html não tem entrada de changelog para {version}.")
for item in re.findall(r"<li>(.*?)</li>", m.group(1), re.S):
    print("- " + html.unescape(re.sub(r"<[^>]+>", "", " ".join(item.split()))))
PY

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    prev=$(git tag -l 'v*' --sort=-v:refname | grep -vE -- '-' | grep -vx "$TAG" \
           | while read -r t; do git merge-base --is-ancestor "$t" "$TAG" && { echo "$t"; break; }; done || true)
    if [ -n "$prev" ]; then
        echo
        echo "### O que mudou"
        echo
        git log --no-merges --format='- %s' "$prev..$TAG" | grep -v '^- chore(release)' || true
        repo=$(git remote get-url origin 2>/dev/null | sed -E 's#^git@[^:]+:##; s#^https://github\.com/##; s#\.git$##' || true)
        if [[ "$repo" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]]; then
            echo
            echo "**Mudanças completas:** https://github.com/$repo/compare/$prev...$TAG"
        fi
    fi
fi
