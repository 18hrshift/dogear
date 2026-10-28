#!/usr/bin/env bash
# Check DAISY 2.02 books with DAISY Pipeline 2's validator (daisy202-validator), in Docker.
#
#   scripts/check-daisy.sh FOLDER [FOLDER...]
#
# Each FOLDER is a book: the folder holding its ncc.html. The validator's report for each
# is saved next to it, as "FOLDER validation report.html". Exits 0 only when every book
# passes: the job must finish with status SUCCESS, which needs every check to pass,
# including the ones the report calls warnings.
#
# Needs Docker, curl, and zip. The first run downloads the Pipeline image (about 350 MB).
# The script starts its own Pipeline server on a private network and a free local port,
# and removes both when it ends; it touches no other container.
set -euo pipefail

IMAGE="daisyorg/pipeline:1.15.5"

fail_setup() {
  echo "$1" >&2
  exit 2
}

if [ $# -eq 0 ]; then
  fail_setup "Usage: scripts/check-daisy.sh FOLDER [FOLDER...], where each folder holds a book's ncc.html."
fi
for program in docker curl zip; do
  command -v "$program" >/dev/null || fail_setup "This check needs $program. Install it and run the check again."
done
books=()
for folder in "$@"; do
  folder="${folder%/}"
  [ -f "$folder/ncc.html" ] || fail_setup "There is no ncc.html in $folder. Give the folder of a DAISY 2.02 book."
  books+=("$(cd "$folder" && pwd)")
done

name="dogear-daisy-check-$$-$RANDOM"
work="$(mktemp -d)"
cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker network rm "$name" >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

echo "Starting DAISY Pipeline 2 ($IMAGE)."
docker network create "$name" >/dev/null
docker run -d --name "$name" --network "$name" -p 127.0.0.1::8181 \
  -e PIPELINE2_WS_HOST=0.0.0.0 -e PIPELINE2_WS_AUTHENTICATION=false "$IMAGE" >/dev/null
address="$(docker port "$name" 8181/tcp | head -n 1)"
alive=""
for _ in $(seq 90); do
  if curl -sf "http://$address/ws/alive" >/dev/null; then
    alive=yes
    break
  fi
  sleep 2
done
[ -n "$alive" ] || fail_setup "DAISY Pipeline 2 didn't start within 3 minutes. Its log: docker logs $name"

failed=0
for book in "${books[@]}"; do
  job="$work/$(basename "$book" | tr -c 'A-Za-z0-9\n' '_')"
  mkdir -p "$job"
  # Only the book's own files: not Dogear's hidden record of what it wrote.
  (cd "$book" && zip -q -r "$job/book.zip" . -x '.*' -x '*/.*')
  docker run --rm --network "$name" --user "$(id -u):$(id -g)" -v "$job:/mnt" \
    --entrypoint /opt/daisy-pipeline2/cli/dp2 "$IMAGE" \
    --host "http://$name" --starting false \
    daisy202-validator --source ncc.html --data /mnt/book.zip --output /mnt/report \
    >"$job/dp2.log" 2>&1 || true
  # dp2 draws a progress bar; keep only its messages.
  sed -e 's/\x1b\[[0-9;]*[A-Za-z]//g' "$job/dp2.log" | grep -E '^\[(ERROR|WARNING)\]|^Job' || true
  report="$(find "$job/report" -name '*.html' -print -quit 2>/dev/null || true)"
  saved="$book validation report.html"
  if [ -n "$report" ]; then
    cp "$report" "$saved"
  fi
  if grep -q 'Job finished with status: SUCCESS' "$job/dp2.log"; then
    echo "Valid: $book"
  else
    failed=1
    echo "Not valid: $book"
    if [ -n "$report" ]; then
      echo "The validator's report is in $saved"
    else
      echo "The validator wrote no report. Its output:"
      sed -e 's/\x1b\[[0-9;]*[A-Za-z]//g' "$job/dp2.log" | grep -v -E '^[_ ]*$|░|█'
    fi
  fi
done
exit "$failed"
