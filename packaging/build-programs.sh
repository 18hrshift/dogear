#!/usr/bin/env bash
# Builds the programs the standalone installers carry, from pinned source archives:
# LAME, then FFmpeg (ffmpeg and ffprobe) with LAME for MP3, then eSpeak NG with its data.
#
# packaging/build.py runs this after checking each archive's SHA-256 (packaging/pins.toml).
# On Windows it runs in MSYS2's UCRT64 shell, with MinGW-w64 GCC, so one recipe serves
# every platform. Each program is linked statically against the libraries built here, and
# FFmpeg is built without autodetection, so the result needs only what every system has.
#
# Usage: build-programs.sh LAME FFMPEG ESPEAK_NG SONIC WORK OUT
#   LAME, FFMPEG, ESPEAK_NG, SONIC  the source archives
#   WORK  a scratch folder (emptied first)
#   OUT   where the programs go (emptied first): ffmpeg, ffprobe, espeak-ng, espeak-ng-data
# JOBS sets how many compile jobs run at once.
set -euo pipefail

if [ "$#" -ne 6 ]; then
  echo "Usage: build-programs.sh LAME FFMPEG ESPEAK_NG SONIC WORK OUT" >&2
  exit 2
fi

# MSYS2 is handed Windows paths; cygpath turns them into ones its tools read.
unix_path() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -u "$1"; else printf '%s\n' "$1"; fi
}

lame_archive=$(unix_path "$1")
ffmpeg_archive=$(unix_path "$2")
espeak_archive=$(unix_path "$3")
sonic_archive=$(unix_path "$4")
work=$(unix_path "$5")
out=$(unix_path "$6")
jobs=${JOBS:-2}

exe=""
static_flags=""
cmake_generator=()
case "$(uname -s)" in
  MINGW* | MSYS*)
    exe=".exe"
    static_flags="-static"  # no MinGW runtime DLLs beside the programs
    cmake_generator=(-G "MSYS Makefiles")
    ;;
esac

rm -rf "$work" "$out"
mkdir -p "$work/src" "$out"
prefix="$work/prefix"

unpack() {
  mkdir -p "$work/src/$2"
  tar -xf "$1" -C "$work/src/$2" --strip-components=1
}

echo "Building LAME."
unpack "$lame_archive" lame
(
  cd "$work/src/lame"
  ./configure --prefix="$prefix" --enable-static --disable-shared \
    --disable-frontend --disable-decoder
  make -j"$jobs"
  make install
)

echo "Building FFmpeg."
unpack "$ffmpeg_archive" ffmpeg
(
  cd "$work/src/ffmpeg"
  # LGPL build: no --enable-gpl or --enable-version3. Autodetection off, so nothing from
  # the build machine is linked in by accident; zlib is turned back on for PNG covers.
  ./configure --prefix="$prefix" \
    --enable-static --disable-shared \
    --disable-autodetect --enable-zlib --enable-libmp3lame \
    --disable-ffplay --disable-avdevice --disable-network --disable-doc --disable-debug \
    --pkg-config-flags=--static \
    --extra-cflags="-I$prefix/include" \
    --extra-ldflags="-L$prefix/lib $static_flags"
  make -j"$jobs"
  make install
)

echo "Building eSpeak NG."
unpack "$sonic_archive" sonic
unpack "$espeak_archive" espeak-ng
# eSpeak NG's build fetches Sonic with git unless given its source. It is handed the
# pinned archive instead, and built without it (USE_LIBSONIC=OFF), as Dogear only asks
# espeak-ng for phonemes. The same goes for audio output, MBROLA, and the other synthesizers.
# eSpeak NG keeps its data folder's path in a fixed buffer, 160 bytes by default outside
# Windows. An installed app's path can be longer (macOS runs a downloaded app from a long
# temporary path until it's moved), so the buffer is made bigger with the setting it has
# for that, N_PATH_HOME.
# (The odd expansion keeps macOS's bash 3.2 from calling an empty array unset.)
cmake -S "$work/src/espeak-ng" -B "$work/espeak-ng-build" \
  ${cmake_generator[@]+"${cmake_generator[@]}"} \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_FLAGS="-DN_PATH_HOME=1024" \
  -DCMAKE_INSTALL_PREFIX="$prefix" \
  -DBUILD_SHARED_LIBS=OFF \
  -DBUILD_TESTING=OFF \
  -DESPEAK_BUILD_MANPAGES=OFF \
  -DUSE_ASYNC=OFF \
  -DUSE_LIBPCAUDIO=OFF \
  -DUSE_LIBSONIC=OFF \
  -DUSE_MBROLA=OFF \
  -DUSE_KLATT=OFF \
  -DUSE_SPEECHPLAYER=OFF \
  -DFETCHCONTENT_FULLY_DISCONNECTED=ON \
  -DFETCHCONTENT_SOURCE_DIR_SONIC-GIT="$work/src/sonic"
cmake --build "$work/espeak-ng-build" -j "$jobs"
cmake --install "$work/espeak-ng-build" --strip

cp "$prefix/bin/ffmpeg$exe" "$prefix/bin/ffprobe$exe" "$prefix/bin/espeak-ng$exe" "$out/"
cp -R "$prefix/share/espeak-ng-data" "$out/"
echo "Built ffmpeg, ffprobe, and espeak-ng in $out."
