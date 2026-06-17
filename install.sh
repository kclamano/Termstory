#!/bin/bash
set -e

echo "=== TermStory Installer v0.6.0 ==="

PYTHON=""
for cmd in python3 python; do
  command -v $cmd &>/dev/null && PYTHON=$cmd && break
done
[ -z "$PYTHON" ] && { echo "Python 3 not found"; exit 1; }
echo "  $($PYTHON --version)"

# TEMP DIR
TMPDIR=$(mktemp -d)
echo "  Downloading..."
curl -fsSL "https://github.com/bitflicker64/Termstory/archive/refs/heads/main.tar.gz" -o "$TMPDIR/termstory.tar.gz"
tar -xzf "$TMPDIR/termstory.tar.gz" -C "$TMPDIR"

cd "$TMPDIR/Termstory-main"

# Try install — --user bypasses PEP 668 (break-system-packages)
if $PYTHON -m pip install --user -e . 2>/dev/null; then
  echo "  Installed (--user)"
elif $PYTHON -m pip install -e . --break-system-packages 2>/dev/null; then
  echo "  Installed (--break-system-packages)"
elif $PYTHON -m pip install --user -e --no-warn-script-location . 2>/dev/null; then
  echo "  Installed (--user)"
else
  # Last resort: virtual env
  echo "  Trying venv..."
  $PYTHON -m venv "$HOME/.termstory-venv"
  "$HOME/.termstory-venv/bin/pip" install -e . 2>&1 | tail -3
  echo "  Add to shell: export PATH=\"\$HOME/.termstory-venv/bin:\$PATH\""
  echo "  Or run: $HOME/.termstory-venv/bin/termstory today"
  cd /; rm -rf "$TMPDIR"; exit 0
fi

cd /; rm -rf "$TMPDIR"

# Warn about PATH
if command -v termstory &>/dev/null; then
  echo "  Installed! Run: termstory today"
else
  echo "  Not on PATH. Add to ~/.zshrc: export PATH=\"\$HOME/.local/bin:\$PATH\""
  echo "  Then: termstory today"
fi
