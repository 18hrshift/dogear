#!/bin/sh
# Installs Dogear for you alone; no administrator password is needed.
#   The program goes in ~/.local/opt/dogear.
#   The dogear command goes in ~/.local/bin.
#   "Dogear" goes in your applications menu. It opens a terminal window running Dogear.
# Run it from the folder it came in:  sh install.sh
# To remove Dogear later:  sh ~/.local/opt/dogear/uninstall.sh
set -eu

here=$(cd "$(dirname "$0")" && pwd)
target="$HOME/.local/opt/dogear"
bin="$HOME/.local/bin"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

if [ ! -x "$here/dogear/dogear" ]; then
  echo "Error: the dogear folder isn't beside install.sh." >&2
  echo "What to do: unpack the whole download, then run install.sh from that folder." >&2
  exit 1
fi

# In a desktop entry's Exec line, an argument in double quotes escapes " \` $ and \ with a
# backslash; then every backslash is doubled, as in any desktop entry text. A literal %
# is written %%.
desktop_quote() {
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/["`$]/\\&/g' -e 's/\\/\\\\/g' -e 's/%/%%/g'
}

echo "Installing Dogear in $target."
mkdir -p "$(dirname "$target")"
rm -rf "$target.new"
cp -R "$here/dogear" "$target.new"
cp "$here/uninstall.sh" "$target.new/uninstall.sh"
rm -rf "$target"
mv "$target.new" "$target"

mkdir -p "$bin"
ln -sf "$target/dogear" "$bin/dogear"

mkdir -p "$apps"
cat > "$apps/dogear.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Dogear
GenericName=Talking book maker
Comment=Turn books into audiobooks you can navigate. Keep its window open while you use Dogear.
Exec="$(desktop_quote "$target/dogear")" serve
Terminal=true
Icon=audio-x-generic
Categories=AudioVideo;Audio;Utility;Accessibility;
Keywords=audiobook;talking book;DAISY;EPUB;
EOF
cat > "$apps/dogear-lan.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Dogear for phones and tablets
GenericName=Talking book maker
Comment=Start Dogear so phones and tablets on the same network can use it too. Keep its window open while you use Dogear.
Exec="$(desktop_quote "$target/dogear")" serve --lan
Terminal=true
Icon=audio-x-generic
Categories=AudioVideo;Audio;Utility;Accessibility;
Keywords=audiobook;talking book;DAISY;EPUB;phone;
EOF

echo "Dogear is installed."
echo "To start it, choose Dogear in your applications menu. A terminal window opens; keep it open while you use Dogear."
case ":$PATH:" in
  *":$bin:"*) echo "To use it from a terminal, run: dogear --help" ;;
  *) echo "To use it from a terminal, run: $bin/dogear --help (after you next log in, dogear --help is enough on most systems)." ;;
esac
echo "To remove it, run: sh $target/uninstall.sh"
