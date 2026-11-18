#!/bin/sh
# Deterministic case-local build: stage the legitimate inputs into a disposable
# work directory, then let rIC3 build the BTOR model.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
work="$root/.pcd-build"
rm -rf "$work"
mkdir -p "$work"
cp "$root"/input/rtl/* "$work"/
cp "$root"/build/ric3.toml "$work"/
cd "$work"
"${RIC3:-ric3}" build
