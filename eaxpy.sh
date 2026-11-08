#!/usr/bin/env bash
# EA Explorer launcher, the Python version (phase 13.9, D331). Linux and macOS; Windows: eaxpy.cmd.
# It fetches uv (one small program) into work/tools the first time, and uv fetches the Python it needs into
# work/tools/python; then it runs eaxpy.py. Nothing is installed elsewhere on the machine. cleanup keeps work/tools.
# Another uv (an offline server, say): set EAX_UV to its path. Another uv version: set EAX_UV_VERSION.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$ROOT/work/tools"
VERSION="${EAX_UV_VERSION:-0.9.5}"
UV="${EAX_UV:-$TOOLS/uv}"
if [ ! -x "$UV" ]; then
  case "$(uname -m)" in arm64|aarch64) arch=aarch64 ;; *) arch=x86_64 ;; esac
  case "$(uname -s)" in Darwin) target="$arch-apple-darwin" ;; *) target="$arch-unknown-linux-gnu" ;; esac
  url="https://github.com/astral-sh/uv/releases/download/$VERSION/uv-$target.tar.gz"
  echo "First run: fetching uv $VERSION into work/tools (once; it then fetches Python 3.12 there too)..."
  mkdir -p "$TOOLS"
  tmp="$TOOLS/uv-unpacked"; rm -rf "$tmp"; mkdir -p "$tmp"
  if command -v curl >/dev/null 2>&1; then get() { curl -fsSL "$1" -o "$2"; }; else get() { wget -qO "$2" "$1"; }; fi
  if ! get "$url" "$tmp/uv.tar.gz"; then
    echo "ERROR: could not fetch uv from $url."
    echo "Without internet: download that file elsewhere, put uv into work/tools, or set EAX_UV to a uv program."
    exit 1
  fi
  tar -xzf "$tmp/uv.tar.gz" -C "$tmp"
  find "$tmp" -type f \( -name uv -o -name uvx \) -exec cp {} "$TOOLS/" \;
  chmod +x "$TOOLS/uv" "$TOOLS/uvx" 2>/dev/null || true
  rm -rf "$tmp"
fi
# uv keeps its Python and its cache in work/tools, not in the user's home
export UV_PYTHON_INSTALL_DIR="$TOOLS/python" UV_CACHE_DIR="$TOOLS/cache" UV_PYTHON_PREFERENCE=only-managed
exec "$UV" run --no-project --quiet --python 3.12 "$ROOT/eaxpy.py" "$@"
