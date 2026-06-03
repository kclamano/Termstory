# TermStory Developer Memory Engine — State & Context (agents.md)

This file serves as the active development state, architectural roadmap, and design philosophy context for TermStory to ensure seamless pairing and handoffs.

---

## 1. Core Philosophy: Developer Memory Engine

TermStory is **not** a tracking tool, productivity auditor, or a generic manager dashboard. It is a **personal developer memory engine** designed to trigger recognition.
* **Recognize, don't inspect**: Optimize for recognition ("What did I work on?"). Details ("How do you know?") belong in `--detailed` mode.
* **Density over decoration**: Avoid rounded panels, double borders, or nested boxes. Use clean column alignment, simple tables, and minimal spacing.
* **Screenshot-friendly**: Every screen should fit in a single terminal screen/screenshot and tell a compelling story about a developer's day, search, or project.
* **Map General to Other**: "General / No Project" or empty project names are mapped to `"Other"`.
* **Noise Filtering**: Filter out routine navigation, status, and inspection commands (like `cd`, `ls`, `docker ps`, `git status`, `docker logs`, `grep`, etc.) so only creative/memorable work remains.

---

## 2. Technical Component Deep-Dive & Architecture

### A. Parser Engine ([parser.py](file:///Users/himanshuverma/Projects/termstory/termstory/parser.py))
Parses shell histories safely to extract Unix timestamps and clean command strings.
* **Zsh Parser**: Extracts Zsh logs written in the extended history format: `: <timestamp>:<duration>;<command>`. Handles multiline commands marked with a trailing backslash `\`.
* **Bash Parser**: Reads standard `.bash_history`. If `#<timestamp>` rows exist, it associates commands with their timestamps. If timestamps are missing, it spaces them backward and forward in 10-second intervals based on the file modification time (`mtime`).
* **Filtering Limits**: Filters out commands older than 5 years or with future timestamps to avoid database pollution.

### B. Session Builder ([session.py](file:///Users/himanshuverma/Projects/termstory/termstory/session.py))
Chains chronological commands into sessions.
* **Threshold**: Groups commands into a single session if the idle time between consecutive commands is under **30 minutes**.
* **Attributes**: Computes session start time, end time, duration in seconds, and active commands.

### C. Project Resolver ([project.py](file:///Users/himanshuverma/Projects/termstory/termstory/project.py))
Maps directory paths to logical project names.
* **VCS Root Detection**: Recursively scans parent directories looking for `.git`, `.hg`, or `.svn` root folders.
* **Configuration Inspection**: Reads metadata from build configurations (`pom.xml`, `package.json`, `setup.py`, `Cargo.toml`, etc.) to extract clean project names.
* **Normalization**: Maps empty/general workspaces to `"Other"`.

### D. Git Correlator ([git_integration.py](file:///Users/himanshuverma/Projects/termstory/termstory/git_integration.py))
Enriches shell activity by fetching corresponding Git commits.
* **Subprocess Spawning**: Runs local `git log` commands filtered by timestamp ranges corresponding to session start and end times.
* **Cleaning Heuristics**: Strips conventional commit tags (e.g. `feat:`, `fix(tui):`), emojis, merge hashes, and branch pointers from commit messages to feed clean content to the database and AI prompts.

### E. Database Layer ([database.py](file:///Users/himanshuverma/Projects/termstory/termstory/database.py))
Manages SQLite storage under `~/.termstory/termstory.db`.
* **WAL Mode**: Executes `PRAGMA journal_mode = WAL;` for non-blocking concurrent reads/writes.
* **Index Strategy**: Optimizes search, TUI loads, and timeline scrolling via:
  - `idx_commands_timestamp` on `commands(timestamp)`
  - `idx_commands_session_id` on `commands(session_id)`
  - `idx_sessions_start_time` on `sessions(start_time DESC)`
  - `idx_sessions_project_id` on `sessions(project_id)`
  - `idx_commits_timestamp` on `commits(timestamp DESC)`
  - `idx_commits_project_id` on `commits(project_id)`
* **Cache Architecture**: The `macro_summaries` table stores AI summaries for Months and Dates to bypass repeated API calls. Columns: `timeframe_id` (UNIQUE), `type` (`date`/`month`), `summary`, `created_at`.
* **Session Summaries**: Stored directly in the `sessions.ai_summary` column.

### F. Privacy Sanitizer ([sanitizer.py](file:///Users/himanshuverma/Projects/termstory/termstory/sanitizer.py))
A local pipeline that redacts sensitive parameters prior to LLM submission.
* **Blacklist Operations**: Drops sessions containing high-risk keywords (e.g., `vault login`, `aws configure`, `gh auth`, `create secret`) and returns `"Security/Authentication Operations"` directly.
* **Credential Redaction**: Replaces parameters marked with flags (`--password`, `-p`, `--token`, `--api-key`) with `[REDACTED]`.
* **IP / Host Masking**: Redacts IPv4/IPv6 addresses, URL hosts, and FQDNs. Skips common source/config extensions (like `.py`, `.json`, `.db`, `.sh`, `.yml`) to preserve file names.

### G. Zero-Dependency AI Client ([ai.py](file:///Users/himanshuverma/Projects/termstory/termstory/ai.py))
Interfaces with LLMs using Python's native `urllib.request`.
* **Endpoint Normalization**: Strips trailing slashes from `api_base_url` and appends `/chat/completions` dynamically.
* **Key Sanitization**: Skips building empty `Authorization` headers to ensure compatibility with local engines (e.g., Ollama).
* **Timeout Protection**: Sets a 15.0s timeout to prevent thread blocks during TUI queries.

---

## 3. Command Redesign & Feature Status

### 🔍 `termstory search`
* **Status**: Implemented, tested, and pushed.
* **Features**: Groups by project, collapses multiple daily sessions into a single line per day, prioritizes commits over commands, filters noise commands, and maps General to Other.
* **Files**: [formatter.py](file:///Users/himanshuverma/Projects/termstory/termstory/formatter.py) (`format_search_results`, `_is_noise_command`, `_get_session_memory`, `_collapse_by_day`).

### 📋 `termstory today`
* **Status**: Implemented, tested, and pushed.
* **Features**: Clean bulleted timeline per project with project-level duration summaries, yesterday comparison support, and noise filtering.
* **Files**: [formatter.py](file:///Users/himanshuverma/Projects/termstory/termstory/formatter.py) (`format_today_output`).

### 📁 `termstory project`
* **Status**: Implemented, tested, and pushed.
* **Features**: Replaced cards with a clean, high-density, box-free list of dates and milestone accomplishments/memories per day.
* **Files**: [formatter.py](file:///Users/himanshuverma/Projects/termstory/termstory/formatter.py) (`format_project_output`).

### 💡 `termstory insights` / Highlights
* **Status**: Implemented, tested, and pushed.
* **Features**: Overhauled cards, empty charts, and focus score metrics into a compact, clean executive highlights list showing project active days, total duration, and main achievements.
* **Files**: [formatter.py](file:///Users/himanshuverma/Projects/termstory/termstory/formatter.py) (`format_insights_output`, `_get_project_main_achievement`).

### 💻 `termstory ui` (Textual TUI Dashboard)
* **Status**: Fully implemented, refined, and verified.
* **Layout Structure**:
  - `StatsHeader` at the top showing active days, streaks, total duration, and a GitHub-style activity heatmap syncing with the timeline's active `days_limit` (defaults to 90 days).
  - Main panel split 30% / 70% between the `HistoryTree` explorer (which hides the root node `Timeline Explorer` to maximize space) and the scrollable `DetailsCanvas`.
  - Simple modal help overlay (`HelpScreen`) toggleable via `?`, dismissible with `Esc`/`q`/Close.
  - Interactive onboarding popup screen (`OnboardingScreen`) triggered when no config is detected, supporting key shortcuts for Groq (`Ctrl+G`), OpenAI (`Ctrl+A`), Ollama (`Ctrl+L`), Custom (`Ctrl+C`), or Disable (`Ctrl+D`).
* **Performance**: Utilizes `@work` async workers to fetch AI summaries on background threads. Implemented session date caching to eliminate rendering lags.
* **Robust OS-Level Copying**: Overrides `copy_to_clipboard` to pipe copy commands directly to local OS utilities (`pbcopy`, `xclip`/`xsel`/`wl-copy`, `clip`) so that copy shortcut `c` writes selections directly to the host operating system's clipboard even when OSC 52 terminal sequences are disabled.
* **Files**: [tui.py](file:///Users/himanshuverma/Projects/termstory/termstory/tui.py), [test_tui.py](file:///Users/himanshuverma/Projects/termstory/tests/test_tui.py), [cli.py](file:///Users/himanshuverma/Projects/termstory/termstory/cli.py).

### 🎨 Phase 4: UI Refinement, Timeline Alignment & Rich Narrative Summaries
* **Status**: Implemented, polished, and verified.
* **Features**:
  - **Dynamic Heatmap & Header Alignment**: Synced stats header labels (`Activity (Last N Days):`) and the command volume heatmap to match the timeline limit dynamically.
  - **Narrative AI Prompt Redesign**: Updated prompts in [ai.py](file:///Users/himanshuverma/Projects/termstory/termstory/ai.py) to replace marketing paragraphs with high-density, CLI-styled console logs using ASCII tree branches (`├─`, `└─`) or tech bullets (`•`) detailing built targets, flow details, and outcome results in a clean, developer-focused structure.
  - **Tree Explorer Cleanups**: Hid the redundant `"Timeline Explorer"` tree root node via constructor args, zeroed margins and tree padding, and centered the footer shortcuts.
* **Files**: [tui.py](file:///Users/himanshuverma/Projects/termstory/termstory/tui.py), [ai.py](file:///Users/himanshuverma/Projects/termstory/termstory/ai.py), [test_tui.py](file:///Users/himanshuverma/Projects/termstory/tests/test_tui.py), [test_ai.py](file:///Users/himanshuverma/Projects/termstory/tests/test_ai.py).

### 📖 Phase 5: Upgraded Daily AI System Prompt & TUI Chronicle Integration
* **Status**: Fully implemented, integrated, and verified.
* **Features**:
  - **Narrative Daily Chronicle**: Embedded the upgraded "Story of You" system prompt in [ai.py](file:///Users/himanshuverma/Projects/termstory/termstory/ai.py) utilizing second-person narrative ("You"), dynamic GitHub handle resolution, inferred breaks, and ASCII connection formatting.
  - **Activity Punch-Card**: Integrated a dynamic horizontal activity punch-card visual strip (`00:00 ░░░░░ 06:00 ... 23:59`) based on hourly command intensity counts.
  - **TUI Integration**: Completely unified the Daily Chronicle inside `termstory ui`'s `DetailsCanvas` when date nodes are selected, maintaining standard session detail feeds at the bottom for full visibility and single-session interactions.
* **Files**: [tui.py](file:///Users/himanshuverma/Projects/termstory/termstory/tui.py), [ai.py](file:///Users/himanshuverma/Projects/termstory/termstory/ai.py), [formatter.py](file:///Users/himanshuverma/Projects/termstory/termstory/formatter.py), [cli.py](file:///Users/himanshuverma/Projects/termstory/termstory/cli.py).

---

## 4. Running Verification

Always verify changes using:
```bash
python3 -m pytest tests/
```
And manually inspect outputs via:
```bash
python3 -m termstory.cli today
python3 -m termstory.cli project termstory
python3 -m termstory.cli insights
python3 -m termstory.cli ui
```
