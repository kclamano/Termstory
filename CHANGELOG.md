# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- One-time console reminder on exit when the TUI is closed and the AI provider is disabled.
- Automatic local Git project path scanning (`discover_project_paths`) in the ingestion pipeline to feed into the `TimestampDetective` for legacy command reconstruction.
- Thread-safe AI error tracking in thread-local storage (`_local_ai_state`) to support concurrent background workers.
- Specialized JSON payload parsing for LLM API errors (e.g. Groq, OpenAI) to extract clean error messages.
- Warning toast notifications displaying detailed thread-local error messages when AI generation fails.
- Configurable git log search timeout (`timeout` parameter in `get_project_commits`), allowing up to 30 seconds for deep history queries while keeping the default fast path at 10 seconds.
- Whitespace normalization on HTTPError message displays to format nicely in TUI toast notifications.
- Lazy/conditional Git repository discovery that runs only if legacy (timestamp-less) history commands are detected in Zsh history files.
- Safe `project_paths` callable resolution inside `parser.py` using try-except wrapping to prevent file permission/read errors from crashing the history parser.
- Fail-fast mechanism for bulk auto-summarization to stop immediately on the first failure, avoiding consecutive error toast spams and redundant network calls.
- Tracked successes and added a warning toast displaying the exact number of successful generations (e.g. `Bulk auto-summarization stopped. Succeeded: 0/2.`).

### Fixed
- Repeated onboarding prompt by gating the `EXTENDED_HISTORY` timestamp-consent prompt behind a `has_seen_timestamp_prompt` config flag.
- Default input response handling in CLI prompts: pressing Enter defaults to `"y"` to match standard command line conventions.
- Prompt suppression logic: the prompt-seen flag is only saved after the shell config file append operation succeeds, ensuring it will retry if the file write fails.
- Deferred configuration loading in `cli.py` to prevent unnecessary disk I/O on normal startup.
- Dynamic git commit ingestion timeframe to fetch commits starting from the oldest parsed command's timestamp, correctly linking commits to recovered legacy commands.
- Empty HTTPError response body handling: falls back to `e.reason` instead of preserving blank messages.

---

## [0.2.10] - 2026-06-07

### Added
- Configurable AI token limit (`max_tokens`) and request timeout (`request_timeout_seconds`) settings.
- macOS `install.log` timestamp anchors in `TimestampDetective` to correlate package install times.

### Fixed
- Configuration value type conversion: values are now cast to target types (like bool or int) on CLI set commands to prevent type errors.
- macOS syslog offset parsing: corrected regex matching for timezone offsets (e.g., `-07`) to standard ISO format (`-07:00`) for python's `datetime.fromisoformat`.
- macOS syslog package filter: enforced strict package name matching in log inspection.
- AI timeout parameter override propagation.

---

## [0.2.9] - 2026-06-06

### Added
- **Timestamp Detective**: Forensic pipeline for recovering real timestamps for legacy history commands by fuzzy-matching git history, file stats, package manager installs, and docker images.
- Hybrid parser support: processes mixed/hybrid Zsh files containing both legacy and timestamped lines.
- Database-driven timestamp locking: sequentially locks in synthetic timestamps to prevent history shifting.
- Bulletproof UTF-8 encoding fallback on legacy archive files.
- Interactive `EXTENDED_HISTORY` onboarding prompt for Zsh/Bash users.
