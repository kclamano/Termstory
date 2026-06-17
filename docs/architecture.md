## 3. Project Layout

```
termstory/
├── setup.py                     # Package metadata
├── pyproject.toml               # Build config
├── README.md                    # This document
├── DATA_PRIVACY.md              # LLM data handling policy
├── termstory/
│   ├── __init__.py              # Version: 0.6.0
│   ├── __main__.py              # python3 -m termstory entry point
│   ├── cli.py                   # Typer CLI — all commands & ingestion entry point
│   ├── tui.py                   # Textual TUI dashboard & all widgets
│   ├── parser.py                # Shell history parsing engine
│   ├── timestamp_detective.py   # Forensic timestamp recovery engine
│   ├── session.py               # 30-minute session grouping
│   ├── project.py               # VCS root detection & project name resolution
│   ├── git_integration.py       # git log subprocess client & commit cleaner
│   ├── database.py              # SQLite layer (WAL, schema, queries, cache)
│   ├── date_utils.py            # Timezone & timestamp utilities
│   ├── sanitizer.py             # Local credential & PII redaction
│   ├── ai.py                    # Zero-dependency LLM client (urllib only)
│   ├── insights.py              # Focus score & pattern calculations
│   ├── models.py                # Command, Session, Project, Commit dataclasses
│   └── formatter.py            # CLI output layout & Rich styling
└── tests/
    ├── fixtures/
    │   └── sample_history.txt
    ├── test_parser.py
    ├── test_session.py
    ├── test_project.py
    ├── test_git_integration.py
    ├── test_database.py
    ├── test_database_queries.py
    ├── test_sanitizer.py
    ├── test_ai.py
    ├── test_tui.py
    ├── test_formatter_rich.py
    ├── test_insights.py
    ├── test_timestamp_detective.py
    └── test_integration.py
```

---

## 4. The Ingestion Pipeline

Every CLI command and every TUI launch runs this pipeline:

```
~/.zsh_history / ~/.bash_history
         │
         ▼
    parser.py  ──────────────────────────────────────────────────────────┐
    Parse raw history into Command objects.                               │
    Separate timestamped commands from legacy (no-timestamp) commands.   │
         │                                                                │
         ▼  (legacy commands only)                                        │
    timestamp_detective.py                                                │
    Phase A: Replay cd/pushd/popd → virtual CWD per command              │
    Phase B: 5 forensic detectors (git log, file stat, pkg mgr,          │
             docker, lockfiles) → real timestamps + Chain of Custody      │
    Phase C: Anchor Interpolation → linear fill between anchors          │
         │                                                                │
         └─────────────────────────────────────────────────────────────►─┤
         ▼                                                                │
    session.py                                                            │
    Group commands into sessions (30-minute idle threshold)              │
         │                                                                │
         ▼                                                                │
    project.py                                                            │
    Detect VCS root → extract project name from manifests → "Other"      │
         │                                                                │
         ▼                                                                │
    git_integration.py                                                    │
    Run git log for session timeframe → clean commit messages            │
         │                                                                │
         ▼                                                                │
    sanitizer.py                                                          │
    Redact credentials, IPs, tokens before any AI call                   │
         │                                                                │
         ▼                                                                │
    database.py  →  ~/.termstory/termstory.db (SQLite + WAL)            │
    Store sessions, commands, commits, recovery_source, AI cache         │
         │                                                                │
         ▼                                                                │
    tui.py / formatter.py                                                 │
    Render timeline, badges, AI summaries, Chain of Custody tooltips     │
```

---

## 5. Shell History Parsing

### Zsh — EXTENDED_HISTORY format

When `setopt EXTENDED_HISTORY` is enabled, Zsh writes:

```
: 1717500000:3;git commit -m "fix auth"
```

The parser extracts timestamp, duration, and command text with multiline support (trailing `\` continuation).

### Zsh — Hybrid / Frankenstein Mode

If you recently enabled `EXTENDED_HISTORY`, your `~/.zsh_history` contains a mix of timestamped and legacy lines. The parser handles this automatically:

- Timestamped lines are extracted normally.
- Legacy lines are collected separately.
- The oldest timestamped command's timestamp minus 60 seconds becomes the `anchor_time`.
- **The Timestamp Detective runs on all legacy lines** (see Section 6).
- **Timestamp Locking**: On subsequent runs, synthetic timestamps are looked up in the database and re-used to prevent legacy commands from shifting dates.

### Bash — HISTTIMEFORMAT
If `HISTTIMEFORMAT` is set, Bash writes `#<timestamp>` headers before each command. The parser associates each command with its preceding timestamp header. Without headers, timestamps are spaced 10 seconds apart backward from the file's `mtime`.

### Fish & PowerShell
Fish (`~/.local/share/fish/fish_history`) and PowerShell (`(Get-PSReadLineOption).HistorySavePath`) formats are natively supported. TermStory dynamically discovers active history file formats and reads timestamped blocks or falls back to legacy interpolation when headers are absent.

### Terminal Multiplexer Resilience
TermStory's parser intelligently strips injected `PROMPT_COMMAND` hooks and escape sequences left by multiplexers like Tmux, Zellij, and Kitty. Session boundaries natively embrace interleaved TTY sessions instead of artificially fracturing your timeline.

### Filtering

Commands older than 5 years or with future timestamps are silently dropped to prevent database pollution.

---

## 6. The Timestamp Detective

> The most significant feature in TermStory's history. If you've been using your terminal for years without `EXTENDED_HISTORY`, your shell history has no dates at all — every command appears to have happened "today". The Timestamp Detective reverse-engineers real timestamps by mining your git log, filesystem metadata, and package manager artifacts.

### The Problem

Without `EXTENDED_HISTORY`, a file like Vansh's 847-command history gets anchored to "today" via a 1-second step-back. His March commits, April npm installs, and May docker builds all collapse into one meaningless session labelled *today*.

### The Solution — Three Phases

#### Phase A — Virtual CWD Tracker

Before running any detector, the engine replays `cd`, `pushd`, and `popd` commands in sequence to compute the **virtual working directory** at every point in history. This is critical because git commit searches must be scoped to the correct repository — otherwise `git commit -m "fix typo"` could match a commit from the wrong project.

```
idx 0:  ls                     → cwd = "~"
idx 1:  cd ~/Projects/myapp    → cwd = "~/Projects/myapp"
idx 2:  npm install            → cwd = "~/Projects/myapp"
idx 3:  git commit -m "init"   → cwd = "~/Projects/myapp"  ← searches THIS repo only
idx 4:  cd ..                  → cwd = "~/Projects"
```

Supports: `cd -` (previous dir), relative `..` paths, `~` and `$HOME` expansion, `pushd`/`popd` stack.

#### Phase B — Five Forensic Detectors

Run in priority order. Each returns `(unix_timestamp, source_string)` or `None`.

**1. Git Commit Matcher** ⭐ Highest confidence

Extracts the message from `git commit -m "…"` and runs `git log --all` on the CWD-scoped repository. Fuzzy-matches the message using `difflib.SequenceMatcher` with a threshold of ≥ 0.85 after stripping conventional prefixes (`feat:`, `fix(scope):`) and emojis from both sides.

**Multi-Repo Collision Trap:** The CWD-derived repo is searched first. If Vansh has three repos with `git commit -m "fix typo"`, only the repo he was sitting in when he typed it gets matched. Fallback to other known project paths only if the local repo has no match.

**2. File Stat** 🟡 Medium confidence

Stats the artifact created by file-creating commands:

| Command | Target |
|---|---|
| `touch <file>` | `<file>` — `st_birthtime` (macOS) or `st_mtime` |
| `mkdir [-p] <dir>` | `<dir>` |
| `echo/printf/cat > <file>` | redirect target |
| `cp <src> <dst>` | `<dst>` |
| `git init [dir]` | `<dir>/.git` |
| `npm init [-y]` | `cwd/package.json` |
| `python -m venv <name>` | `<name>/bin/activate` |
| `cargo init [dir]` | `<dir>/Cargo.toml` |
| `go mod init` | `cwd/go.mod` |

`touch -t` (explicit timestamp set) is excluded. All paths are resolved against the virtual CWD.

**3. Package Manager Install Metadata** 🟡 Medium confidence

| Command | Artifact |
|---|---|
| `brew install <formula>` | `$(brew --prefix)/Cellar/<formula>` mtime |
| `pip install <pkg>` | pip dist-info directory mtime |
| `npm install` (local) | `package-lock.json` mtime |
| `npm install -g <pkg>` | global node_modules `/<pkg>` mtime |
| `cargo add/install <crate>` | `~/.cargo/registry/src/*/*crate*` mtime |
| `gem install <gem>` | `~/.gem/ruby/*/gems/<gem>-*` mtime |

Both `brew --prefix` and `npm root -g` subprocess calls are cached after the first call.

**4. Docker Image Inspector** 🟡 Medium confidence

For `docker build -t <tag>` commands, runs:
```bash
docker image inspect <tag> --format='{{.Created}}'
```
Parses the RFC3339 timestamp and returns the exact second the image was built.

**5. Venv / Lockfile Sentinels** 🟡 Low-medium confidence

| Command | Artifact |
|---|---|
| `bundle install` | `Gemfile.lock` mtime |
| `go mod tidy` / `go get` | `go.sum` mtime |
| `composer install` | `composer.lock` mtime |
| `poetry add/install` | `poetry.lock` mtime |
| `mix deps.get` | `mix.lock` mtime |
| `git clone <url> [dir]` | `<dir>/.git` birthtime |
| `ssh-keygen -f <file>` | `<file>` birthtime |

#### Phase C — Anchor Interpolation Engine ⭐ The Killer Feature

After Phase B, some commands have real timestamps (anchors) and others are still `None`. For each contiguous gap between two anchors, unresolved commands are distributed **linearly**:

```
t_i = t_a + (t_b − t_a) × (i − i_a) / (i_b − i_a)
```

**Example:**

```
[500] npm install express     → 🔍 ANCHOR  Tuesday 14:00  (package.json mtime)
[501] npm start               → 📐 INTERP  Tuesday 14:07  (between anchors)
[502] git commit -m "add express" → 🔍 ANCHOR Tuesday 14:15  (git log)
```

`npm start` is mathematically placed at 14:07 — the proportional moment between the two known events. Not a guess, not today — the most likely real time.

- **Prefix gap** (before first anchor): 1-second step-back from anchor.
- **Suffix gap** (after last anchor): 1-second step-forward from anchor.
- **No anchors at all**: original mtime step-back (same as v0.2.8 behaviour).

### Chain of Custody — The Trust Badge

Every command that the Detective recovered gets a `recovery_source` string persisted to the database. In the TUI, it renders as a badge below the command:

```
💻 Command Timeline:
  • 14:00:03  npm install express
      [🔍 stat: package.json mtime]
  • 14:07:31  npm start
      [🔍 Interpolated (between stat: package.json mtime → git log: myapp@a3f9b2c)]
  • 14:15:44  git commit -m "add express"
      [🔍 git log: myapp@a3f9b2c]
```

This turns *"how the hell did it know that?"* into a *"holy crap, this app is smart"* moment.

### TUI Session Labels

| Label | Meaning |
|---|---|
| `✨ npm init, express installed  (14:00 - 14:45)` | Real EXTENDED_HISTORY timestamp |
| `🔍 Recovered Archive (38 cmds • 14:00 - 14:45)` | Detective found anchors + interpolated |
| `📦 Legacy Archive (12 recovered cmds)` | Zero forensic evidence, fully synthetic |

---

## 7. Project Resolution

`project.py` maps a working directory to a human-readable project name using a two-pass strategy:

```
Working Directory: /home/dev/Projects/termstory/tests
         │
         ▼
Walk up directories looking for .git / .hg / .svn
         │
         ▼
Found root: /home/dev/Projects/termstory
         │
         ▼
Read build manifests:
  package.json → "name" field
  Cargo.toml   → [package] name
  setup.py     → name= argument
  pom.xml      → <artifactId>
         │
         ▼
Normalize: strip hyphens, fix casing
Result: "termstory"
```

**Fallback strictness:** If a directory is not inside a standard project root (`~/Projects/`, `~/src/`, etc.) and has no VCS markers, it maps to the user's home directory and is grouped under `"Other"`. This prevents `~/.ssh`, `~/Downloads`, or `/tmp` from polluting the project list.

**Symlink Protection:** TermStory safely traverses symlinks while preventing infinite recursive loops and stalling on stale network mounts (like NFS/SMB).

---

## 8. Git Commit Correlation

`git_integration.py` enriches sessions by fetching matching commits:

```bash
git -C <repo_root> log --all \
    --since="<session_start - 5min>" \
    --until="<session_end + 10min>" \
    --format="%H|%at|%s"
```

**Commit cleaning pipeline:**
- Strips conventional commit prefixes (`feat(scope):`, `fix:`, `chore:`)
- Removes Unicode emoji and `:shorthand:` tokens
- Drops merge commit messages and branch pointer refs
- Stores both raw and cleaned message for AI prompts

---
