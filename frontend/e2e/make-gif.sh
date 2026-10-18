#!/bin/sh
# Playwright 녹화(webm) → GIF. ffmpeg·ffprobe 필요. 5MB를 넘으면 실패한다.
set -eu
if [ $# -ne 2 ]; then
  echo "usage: $0 <in.webm> <out.gif>" >&2
  exit 2
fi
in=$1
out=$2
limit=$((5 * 1024 * 1024))
filters='fps=10,scale=1000:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=3'

mkdir -p "$(dirname "$out")"
ffmpeg -y -loglevel error -i "$in" -filter_complex "$filters" "$out"

bytes=$(wc -c < "$out" | tr -d ' ')
mb=$(awk "BEGIN { printf \"%.2f\", $bytes / 1048576 }")
secs=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$out" 2>/dev/null || true)
echo "$out: ${bytes} bytes (${mb} MB), ${secs:-?} s"

if [ "$bytes" -gt "$limit" ]; then
  echo "5MB를 넘었습니다. make-gif.sh의 fps 또는 max_colors를 낮춰라" >&2
  exit 1
fi
