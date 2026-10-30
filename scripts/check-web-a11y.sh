#!/usr/bin/env bash
# Check every page of `dogear serve`, in every state, for accessibility problems: axe-core
# in a real browser (Chromium, through Playwright), at desktop width and at 320 CSS
# pixels, in light and dark color schemes, plus checks axe doesn't make (no sideways
# scrolling at 320 pixels or with text at 200% and wider spacing, and a visible focus
# ring on everything the Tab key reaches).
#
#   scripts/check-web-a11y.sh [DIR]
#
# The pages are made with test data (tests/web_samples.py; no voice needed) into DIR
# (default: a new temporary folder), and the report is saved there as a11y-report.json.
# The first run downloads pinned versions of Playwright, its headless Chromium (about
# 110 MB), and axe-core into $DOGEAR_VALIDATORS (default ~/.cache/dogear-validators).
# Later runs reuse them. Needs uv, Node.js 20 or newer, and npm. Set
# DOGEAR_A11Y_INSTALL_DEPS=1 to also install the browser's system libraries (Linux, with
# sudo), as CI does.
#
# Axe finds only some kinds of WCAG failure. Passing this is necessary, not enough: check
# pages by hand too, with a screen reader.
#
# Exits with 1 if any page has any problem.
set -euo pipefail

PLAYWRIGHT_VERSION=1.64.1
AXE_VERSION=4.14.0

fail() {
  echo "check-web-a11y: $*" >&2
  exit 1
}

[ $# -le 1 ] || fail "Give at most one folder, for example: scripts/check-web-a11y.sh out/web-pages"
command -v uv >/dev/null || fail "uv isn't installed. See https://docs.astral.sh/uv/."
command -v node >/dev/null || fail "Node.js isn't installed. The check needs Node.js 20 or newer."
command -v npm >/dev/null || fail "npm isn't installed. It comes with Node.js."
node_major=$(node -p 'process.versions.node.split(".")[0]')
[ "$node_major" -ge 20 ] || fail "The check needs Node.js 20 or newer, and this is $(node --version)."

here=$(cd "$(dirname "$0")" && pwd)
out=${1:-$(mktemp -d)}
mkdir -p "$out"
out=$(cd "$out" && pwd)

cache=${DOGEAR_VALIDATORS:-$HOME/.cache/dogear-validators}
tools=$cache/web-a11y-playwright-$PLAYWRIGHT_VERSION-axe-$AXE_VERSION
export PLAYWRIGHT_BROWSERS_PATH=$tools/browsers
if [ ! -f "$tools/installed" ]; then
  echo "Installing Playwright $PLAYWRIGHT_VERSION, its headless Chromium, and axe-core $AXE_VERSION."
  rm -rf "$tools"
  npm install --prefix "$tools" --no-audit --no-fund --loglevel=error \
    "playwright@$PLAYWRIGHT_VERSION" "axe-core@$AXE_VERSION" >/dev/null
  "$tools/node_modules/.bin/playwright" install --only-shell chromium >/dev/null
  touch "$tools/installed"
fi
if [ "${DOGEAR_A11Y_INSTALL_DEPS:-}" = 1 ]; then
  echo "Installing the browser's system libraries."
  "$tools/node_modules/.bin/playwright" install-deps chromium-headless-shell >/dev/null
fi

echo "Making the sample pages in $out."
(cd "$here/.." && uv run --frozen python tests/web_samples.py "$out" >/dev/null)

node "$here/web-a11y.cjs" "$tools" "$out"
