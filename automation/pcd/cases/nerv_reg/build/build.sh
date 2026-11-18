#!/bin/sh
# Imported official benchmark: stage exactly the case inputs, then build.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
work="$root/.pcd-build"
rm -rf "$work"
mkdir -p "$work"
# Copy recursively so benchmarks whose ric3.toml names subdirectories
# (for example serv's rtl/serv_*.v) keep the same layout in the work tree.
cp -R "$root"/input/rtl/. "$work"/
cp "$root"/build/ric3.toml "$work"/
cd "$work"
"${RIC3:-ric3}" build
