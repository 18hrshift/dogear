#!/usr/bin/env bash
# Check an EPUB talking book with EPUBCheck (is it a valid EPUB?) and Ace by DAISY (does
# it meet the EPUB accessibility rules?).
#
#   scripts/check-epub.sh BOOK.epub
#
# The first run downloads pinned versions of both, about 750 MB with the headless
# browser Ace runs in, into $DOGEAR_VALIDATORS (default ~/.cache/dogear-validators).
# Later runs reuse them. Needs curl, unzip, Java 8 or newer, and Node.js 20 or newer.
#
# Reports are saved next to the book, as BOOK.epubcheck.json and the folder BOOK.ace.
# Exits with 1 if EPUBCheck reports any error or warning or Ace reports any violation.
set -euo pipefail

EPUBCHECK_VERSION=5.4.0
EPUBCHECK_SHA256=33350c61038e71dfb3d45a76aed04bf5481e6d5500cb780f6e98db8bbd15a28c
ACE_VERSION=1.4.6

fail() {
  echo "check-epub: $*" >&2
  exit 1
}

sha256() {
  if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1
}

[ $# -eq 1 ] || fail "Give one EPUB file, for example: scripts/check-epub.sh book.epub"
book=$1
[ -f "$book" ] || fail "$book doesn't exist, or isn't a file."
command -v java >/dev/null || fail "Java isn't installed. EPUBCheck needs Java 8 or newer."
command -v node >/dev/null || fail "Node.js isn't installed. Ace needs Node.js 20 or newer."
command -v npm >/dev/null || fail "npm isn't installed. It comes with Node.js."
node_major=$(node -p 'process.versions.node.split(".")[0]')
[ "$node_major" -ge 20 ] || fail "Ace needs Node.js 20 or newer, and this is $(node --version)."

cache=${DOGEAR_VALIDATORS:-$HOME/.cache/dogear-validators}
mkdir -p "$cache"

epubcheck_dir=$cache/epubcheck-$EPUBCHECK_VERSION
if [ ! -f "$epubcheck_dir/epubcheck.jar" ]; then
  echo "Downloading EPUBCheck $EPUBCHECK_VERSION."
  download=$cache/epubcheck-$EPUBCHECK_VERSION.zip.partial
  curl -fsSL -o "$download" \
    "https://github.com/w3c/epubcheck/releases/download/v$EPUBCHECK_VERSION/epubcheck-$EPUBCHECK_VERSION.zip"
  if [ "$(sha256 "$download")" != "$EPUBCHECK_SHA256" ]; then
    rm -f "$download"
    fail "The EPUBCheck download didn't match its checksum, so it wasn't used. Try again later."
  fi
  rm -rf "$cache/epubcheck-unpacked" "$epubcheck_dir"
  unzip -q "$download" -d "$cache/epubcheck-unpacked"
  mv "$cache/epubcheck-unpacked/epubcheck-$EPUBCHECK_VERSION" "$epubcheck_dir"
  rm -rf "$cache/epubcheck-unpacked" "$download"
fi

# Ace's browser goes inside its own folder, so the whole install is one folder to cache.
ace_dir=$cache/ace-$ACE_VERSION
export PUPPETEER_CACHE_DIR=$ace_dir/browsers
if [ ! -f "$ace_dir/installed" ]; then
  echo "Installing Ace $ACE_VERSION and the headless browser it runs in."
  rm -rf "$ace_dir"
  npm install --prefix "$ace_dir" --no-audit --no-fund --loglevel=error \
    "@daisy/ace-cli@$ACE_VERSION" >/dev/null
  touch "$ace_dir/installed"
fi

stem=${book%.epub}
epubcheck_report=$stem.epubcheck.json
ace_report=$stem.ace
problems=()

echo "Checking $book with EPUBCheck $EPUBCHECK_VERSION."
rm -f "$epubcheck_report"
epubcheck_status=0
epubcheck_log=$(mktemp)
trap 'rm -f "$epubcheck_log"' EXIT
java -jar "$epubcheck_dir/epubcheck.jar" "$book" --json "$epubcheck_report" --failonwarnings \
  >"$epubcheck_log" 2>&1 || epubcheck_status=$?
if [ ! -f "$epubcheck_report" ]; then
  cat "$epubcheck_log"  # it stopped before writing a report, so show why
else
  # Each message as a plain numbered line: its severity, its ID, what it says, and where.
  node -e '
    const report = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
    const c = report.checker;
    console.log(`EPUBCheck found ${c.nFatal} fatal errors, ${c.nError} errors, ` +
      `${c.nWarning} warnings, and ${c.nUsage} usage notes.`);
    report.messages.forEach((m, n) => {
      const where = (m.locations || []).map((l) => `${l.path} line ${l.line}`).join("; ");
      console.log(`${n + 1}. ${m.severity} ${m.ID}: ${m.message}${where ? ` (${where})` : ""}`);
    });
  ' "$epubcheck_report"
fi
if [ "$epubcheck_status" -ne 0 ]; then
  problems+=("EPUBCheck found errors or warnings. Its report: $epubcheck_report")
fi

echo "Checking $book with Ace $ACE_VERSION."
rm -rf "$ace_report"
ace_status=0
# -E: exit with 2 on any violation. -f: replace old reports. -s: no log lines.
"$ace_dir/node_modules/.bin/ace-cli" -E -f -s -o "$ace_report" "$book" || ace_status=$?
if [ -f "$ace_report/report.json" ]; then
  # List each violation as a plain numbered line: its impact, its rule, and where.
  node -e '
    const report = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
    const found = [];
    for (const subject of report.assertions || []) {
      for (const a of subject.assertions || []) {
        if (a["earl:result"]["earl:outcome"] !== "fail") continue;
        const test = a["earl:test"];
        found.push(`${test["earl:impact"]}: ${test["dct:title"]}, in ${subject["earl:testSubject"].url}`);
      }
    }
    console.log(`Ace found ${found.length} violation${found.length === 1 ? "" : "s"}.`);
    found.forEach((line, n) => console.log(`${n + 1}. ${line}`));
  ' "$ace_report/report.json"
fi
if [ "$ace_status" -eq 2 ]; then
  problems+=("Ace found accessibility violations. Its report: $ace_report/report.html")
elif [ "$ace_status" -ne 0 ]; then
  problems+=("Ace couldn't check the book (exit status $ace_status). To reinstall it, delete $ace_dir.")
fi

if [ ${#problems[@]} -eq 0 ]; then
  echo "Both passed: EPUBCheck found no errors or warnings, and Ace found no violations."
  exit 0
fi
echo "The book didn't pass:" >&2
for n in "${!problems[@]}"; do
  echo "$((n + 1)). ${problems[$n]}" >&2
done
exit 1
