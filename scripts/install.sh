#!/bin/bash
set -e

echo "=== TermStory Installer v0.6.0 ==="

PYTHON=""; for cmd in python3 python; do command -v $cmd &>/dev/null && PYTHON=$cmd && break; done
[ -z "$PYTHON" ] && { echo "Python 3 not found"; exit 1; }
echo "  $($PYTHON --version)"
echo "  pip: $($PYTHON -m pip --version 2>&1 | head -1)"

TMPDIR=$(mktemp -d)
echo "  Downloading..."
curl -fsSL "https://github.com/bitflicker64/Termstory/archive/refs/heads/main.tar.gz" -o "$TMPDIR/termstory.tar.gz"
tar -xzf "$TMPDIR/termstory.tar.gz" -C "$TMPDIR"
cd "$TMPDIR/Termstory-main"

echo "  Installing (may need sudo on some systems)..."
$PYTHON -m pip install --break-system-packages -e . 2>&1 | tail -5

cd /; rm -rf "$TMPDIR"

# Verify
if $PYTHON -c "import termstory" 2>/dev/null; then
  BIN=$(find ~/.local/bin ~/Library/Python/*/bin /usr/local/bin -name "termstory" -type f 2>/dev/null | head -1)
  if [ -n "$BIN" ]; then
    echo "  ✅ Installed at: $BIN"
    echo "  Run: $BIN today"
  else
    echo "  ✅ Installed! Run: $PYTHON -m termstory.cli today"
  fi
else
  echo "  ⚠️  Module not found after install. Trying venv..."
  $PYTHON -m venv "$HOME/.termstory-venv"
  "$HOME/.termstory-venv/bin/pip" install -e . 2>&1 | tail -3
  echo "  ✅ Installed in venv. Add to ~/.zshrc:"
  echo '    export PATH="$HOME/.termstory-venv/bin:$PATH"'
  echo "  Then run: termstory today"
fi
