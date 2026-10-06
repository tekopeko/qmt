#!/bin/sh
# One hash over everything a browser renders: the templates and the static
# CSS/JS. The audit stamps this value after a passing phone check and the Stop
# hook compares against it, so "checked on a phone" always means THESE files.
root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$root" || exit 1
find src/qmt/web/templates src/qmt/web/static -type f \
     \( -name '*.html' -o -name '*.css' -o -name '*.js' -o -name '*.webmanifest' \) -print0 \
  | sort -z | xargs -0 shasum | shasum | cut -d' ' -f1
