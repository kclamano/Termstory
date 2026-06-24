#!/bin/bash
# TermStory Uninstaller v0.6.4

set -euo pipefail

echo "=== TermStory Uninstaller v0.6.4 ==="

# Mirror the installer's marker so we only ever touch OUR inserts.
RC_MARKER="# Added by termstory installer"
RC_EXPORT_LINE='export PATH="$HOME/.termstory-venv/bin:$PATH"'

VENV_DIR="$HOME/.termstory-venv"
DATA_DIR="$HOME/.termstory"

# ── Confirm with user unless --yes passed ────────────────────────────────────
auto_yes=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) auto_yes=1 ;;
    -h|--help)
      echo "Usage: uninstall.sh [--yes|-y]"
      echo "    --yes    Skip confirmation prompt"
      exit 0
      ;;
  esac
done

if ! [ "$auto_yes" -eq 1 ]; then
  if [ -t 0 ]; then
    printf '  Uninstall TermStory (delete venv, data, and RC exports)? [y/N] '
    read -r reply </dev/tty 2>/dev/null || reply=""
    case "$reply" in
      [Yy]|[Yy][Ee][Ss]) ;;
      *) echo "  Aborted."; exit 0 ;;
    esac
  else
    echo "  Non-interactive shell and no --yes flag passed. Aborted."
    echo "  Re-run with:  bash scripts/uninstall.sh --yes"
    exit 0
  fi
fi

# ── 1. Remove venv ────────────────────────────────────────────────────────────
if [ -d "$VENV_DIR" ]; then
  echo "  Removing $VENV_DIR ..."
  rm -rf "$VENV_DIR"
else
  echo "  No venv at $VENV_DIR — skipping."
fi

# ── 2. Remove data dir (the SQLite DB) ────────────────────────────────────────
if [ -d "$DATA_DIR" ]; then
  echo "  Removing $DATA_DIR ..."
  rm -rf "$DATA_DIR"
else
  echo "  No data at $DATA_DIR — skipping."
fi

# ── 3. pip uninstall (per-user / --user install) ─────────────────────────────
if command -v pip3 >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
  py=""
  for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
      py="$cmd"
      break
    fi
  done
  if [ -n "$py" ]; then
    # Capture rc; ignore failures (package may not be installed)
    rc=0
    "$py" -m pip uninstall -y termstory 2>/dev/null || rc=$?
    if [ "$rc" -eq 0 ]; then
      echo "  pip uninstall: OK"
    else
      echo "  pip uninstall: package not found or already gone — skipping."
    fi
  fi
fi

# ── 4. Clean up RC files ─────────────────────────────────────────────────────
# Scan ~/.bashrc, ~/.zshrc, ~/.bash_profile. Only ever touch the lines
# prefixed with our marker — never user-owned config.
candidates=()
[ -f "$HOME/.zshrc" ]         && candidates+=("$HOME/.zshrc")
[ -f "$HOME/.bashrc" ]        && candidates+=("$HOME/.bashrc")
[ -f "$HOME/.bash_profile" ]  && candidates+=("$HOME/.bash_profile")

removed_runs=0
if [ "${#candidates[@]}" -gt 0 ]; then
  for rc in "${candidates[@]}"; do
    if grep -Fqx "$RC_MARKER" "$rc" 2>/dev/null; then
      echo "  Cleaning $rc ..."
      # Match the marker line + the immediately-following export line.
      # Use temp file for portability (BSD/GNU grep -z interacts oddly).
      tmp="${rc}.termstory-uninstall.tmp"
      awk -v marker="$RC_MARKER" -v export_line="$RC_EXPORT_LINE" '
        BEGIN { skip = 0 }
        $0 == marker { skip = 1; next }
        skip == 1 && $0 == export_line { skip = 0; next }
        skip == 1 { print; next }
        { print }
      ' "$rc" > "$tmp" && mv "$tmp" "$rc"
      removed_runs=$((removed_runs + 1))
    fi
  done
  if [ "$removed_runs" -eq 0 ]; then
    echo "  No marker found in RC files — nothing to clean."
  fi
else
  echo "  No RC files to scan."
fi

echo ""
echo "  ✅ TermStory uninstalled."
echo ""
echo "  Note: open a new shell (or 'source ~/.zshrc') to drop the PATH"
echo "        entry from the current session."
