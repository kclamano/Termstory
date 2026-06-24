#!/bin/bash
# TermStory Installer v0.6.3

set -euo pipefail

echo "=== TermStory Installer v0.6.3 ==="

# ── Find Python ────────────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "❌ Python 3 not found. Please install it and re-run."
  exit 1
fi
echo "  Python: $($PYTHON --version)"
echo "  pip:    $($PYTHON -m pip --version 2>&1 | awk '{print $1, $2}')"

# ── Global state ──────────────────────────────────────────────────────────────
# The EXIT trap reads this to restore a stranded backup if the script is
# interrupted mid-install (SIGTERM, SIGINT, unchecked error).
_BACKUP_DIR=""
_SRC_DIR=""

# ── Download & extract ─────────────────────────────────────────────────────────
WORK_DIR=$(mktemp -d)

cleanup() {
  # Restore stranded venv backup if script was aborted mid-install
  if [ -n "$_BACKUP_DIR" ] && [ -d "$_BACKUP_DIR" ]; then
    rm -rf "$HOME/.termstory-venv"
    [ -d "$_BACKUP_DIR/termstory-venv" ] && mv "$_BACKUP_DIR/termstory-venv" "$HOME/.termstory-venv"
    rm -rf "$_BACKUP_DIR"
  fi
  rm -rf "${WORK_DIR:-}"
}
trap cleanup EXIT

echo "  Downloading TermStory..."
if ! curl -fsSL \
    "https://github.com/bitflicker64/Termstory/archive/refs/heads/main.tar.gz" \
    -o "$WORK_DIR/termstory.tar.gz"; then
  echo "❌ Download failed. Check your internet connection."
  exit 1
fi

tar -xzf "$WORK_DIR/termstory.tar.gz" -C "$WORK_DIR"
SRC_DIR="$WORK_DIR/Termstory-main"

if [ ! -d "$SRC_DIR" ]; then
  echo "❌ Extracted archive doesn't contain expected directory: $SRC_DIR"
  exit 1
fi

# ── pip version helper ─────────────────────────────────────────────────────────
# Spawns one Python subprocess; result used at most once per strategy.
pip_major_version() {
  "$PYTHON" -c "import pip; print(int(pip.__version__.split('.')[0]))" 2>/dev/null || echo "0"
}

# ── Install strategies ─────────────────────────────────────────────────────────

install_venv() {
  local venv="$HOME/.termstory-venv"
  echo "  Trying venv install at $venv ..."

  # Back up any existing venv so we can roll back on failure.
  # backup_dir holds the moved venv at "$backup_dir/termstory-venv".
  # Register cleanup so an interrupted/aborted script doesn't strand it.
  local backup_dir=""
  if [ -d "$venv" ]; then
    backup_dir=$(mktemp -d)
    mv "$venv" "$backup_dir/termstory-venv"
    # Register with global EXIT trap — restores on abort/interrupt
    _BACKUP_DIR="$backup_dir"
  fi

  # Inline rollback helper — bash does not support true nested functions;
  # a "nested" definition leaks to global scope and loses access to locals.
  _rollback_venv() {
    local msg="$1" backup="$2"
    echo "  $msg"
    rm -rf "$venv"
    if [ -n "$backup" ]; then
      mv "$backup/termstory-venv" "$venv"
      rm -rf "$backup"
    fi
    return 1
  }

  if ! "$PYTHON" -m venv "$venv" 2>/dev/null; then
    _rollback_venv "venv creation failed (is the venv module installed?)" "$backup_dir" || return 1
  fi

  # Let pip write its own stderr to the terminal — don't redirect or silence errors.
  local pip_rc=0
  "$venv/bin/pip" install --quiet "$SRC_DIR" || pip_rc=$?
  if [ "$pip_rc" -ne 0 ]; then
    _rollback_venv "pip install failed (exit $pip_rc)." "$backup_dir" || return 1
  fi

  if ! "$venv/bin/python" -c "import termstory" 2>/dev/null; then
    _rollback_venv "Package not importable after install." "$backup_dir" || return 1
  fi

  # Success — discard backup
  [ -n "$backup_dir" ] && rm -rf "$backup_dir" && _BACKUP_DIR=""

  echo ""
  echo "  ✅ Installed in virtualenv."
  echo "  Run right now:"
  echo "    $venv/bin/termstory today"
  echo ""
  echo "  For permanent access, add to ~/.bashrc or ~/.zshrc:"
  echo '    export PATH="$HOME/.termstory-venv/bin:$PATH"'
  echo ""
}

install_user() {
  echo "  Trying --user install..."

  local pip_ver pip_rc=0
  pip_ver=$(pip_major_version)

  # --break-system-packages required on Debian/Ubuntu with pip >= 23.
  # Let pip write its own stderr to the terminal on failure.
  if [ "$pip_ver" -ge 23 ]; then
    "$PYTHON" -m pip install --quiet --user --break-system-packages "$SRC_DIR" || pip_rc=$?
  else
    "$PYTHON" -m pip install --quiet --user "$SRC_DIR" || pip_rc=$?
  fi

  if [ "$pip_rc" -ne 0 ]; then
    echo "  pip install failed (exit $pip_rc)."
    return 1
  fi

  # Verify the imported module is actually from this install target,
  # not a stale system or site-packages copy.
  if ! "$PYTHON" -c "
import sys, os, site
user_site = site.getusersitepackages()
import termstory
fp = os.path.realpath(termstory.__file__)
if not fp.startswith(os.path.realpath(user_site)):
    sys.exit(1)
" 2>/dev/null; then
    echo "  Package not importable from user site-packages after install."
    return 1
  fi

  # Locate the installed binary (Linux ~/.local/bin or macOS Library path).
  local bin_path
  bin_path=$(find \
    "$HOME/.local/bin" \
    "$HOME/Library/Python" \
    -name "termstory" -type f 2>/dev/null | head -1) || true

  echo ""
  echo "  ✅ Installed."
  if [ -n "$bin_path" ]; then
    echo "  Binary: $bin_path"
    echo "  Run:    termstory today"
    echo "  (Ensure $(dirname "$bin_path") is in your PATH)"
  else
    echo "  Binary not found in standard locations."
    echo "  Run:    $PYTHON -m termstory.cli today"
  fi
}

# ── Try venv first, then user, then give up ────────────────────────────────────
if ! install_venv && ! install_user; then
  echo ""
  echo "❌ All install strategies failed."
  echo "   Manual fallback:"
  echo "     git clone https://github.com/bitflicker64/Termstory.git"
  echo "     cd Termstory && pip install ."
  exit 1
fi
