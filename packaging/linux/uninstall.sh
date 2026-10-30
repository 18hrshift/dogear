#!/bin/sh
# Removes Dogear installed by install.sh. Audiobooks you made, voices it downloaded, and
# your settings stay where they are.
# Run:  sh ~/.local/opt/dogear/uninstall.sh
set -eu

target="$HOME/.local/opt/dogear"
link="$HOME/.local/bin/dogear"
desktop="${XDG_DATA_HOME:-$HOME/.local/share}/applications/dogear.desktop"

if [ ! -d "$target" ]; then
  echo "Error: Dogear isn't installed in $target, so there is nothing to remove." >&2
  exit 1
fi

# The command link is removed only if it is the one install.sh made.
if [ -L "$link" ] && [ "$(readlink "$link")" = "$target/dogear" ]; then
  rm "$link"
fi
rm -f "$desktop"
echo "Dogear is uninstalled."
echo "Voices it downloaded are in ${XDG_DATA_HOME:-$HOME/.local/share}/dogear, and spoken sentences it kept are in ${XDG_CACHE_HOME:-$HOME/.cache}/dogear. Delete those folders too if you no longer need them."
rm -rf "$target"
