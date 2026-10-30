#!/bin/sh
# Dogear.app's own program (Contents/MacOS/Dogear). It opens a Terminal window running
# `dogear serve`. That window is Dogear: it shows the link to open in a browser, and
# closing it, or pressing Ctrl+C in it, stops Dogear.
#
# Terminal runs a .command file in a new window, with no permission prompt. The file is
# written fresh each time in your temporary folder, since the app itself may be on a
# read-only disk image, and it names the dogear program inside this app.
set -eu

contents=$(cd "$(dirname "$0")/.." && pwd)
dogear="$contents/Resources/dogear/dogear"
command_file="${TMPDIR:-/tmp}/Dogear.command"

# Single quotes keep the path whole; a single quote inside it is written '\''.
quoted=$(printf '%s' "$dogear" | sed "s/'/'\\\\''/g")
printf '%s\n' '#!/bin/sh' "exec '$quoted' serve" > "$command_file"
chmod 755 "$command_file"
exec open -a Terminal "$command_file"
