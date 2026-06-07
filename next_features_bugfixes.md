# Next Features & Bugfixes

This file tracks features, bugfixes, and refactors that have been implemented locally on feature branches but not yet released to PyPI. Once a subset of issues (e.g. 4-5) is completed, they will be combined and published under a single version bump.

---

## 1. Fix Repeated Onboarding Prompt

### Problem
When the Zsh or Bash history file has legacy (timestamp-less) entries, `parse_zsh_history()` and `parse_bash_history()` always find legacy items and set the environment variable `TERMSTORY_MISSING_TIMESTAMPS = 1`. 
Enabling history timestamps in shell config files (via `setopt EXTENDED_HISTORY` or `HISTTIMEFORMAT`) only applies to *new* commands, so old commands remain dateless. As a result, `termstory ui` repeatedly prompts the user on every launch.

### Fix
- Added `"has_seen_timestamp_prompt": False` to the configuration defaults in `load_config()`.
- Updated `show_ui()` in `cli.py` to check that the `has_seen_timestamp_prompt` config flag is `False` before triggering the timekeeping prompt.
- Handled default response parsing: pressing Enter (empty response `""`) now defaults to `"y"` to match the `[Y/n]` prompt style.
- Restrict flag persistence: only save `has_seen_timestamp_prompt = True` on valid, explicit responses (`y`/`yes`/`n`/`no`/KeyboardInterrupt/EOF). In the `"yes"` branch, the flag is saved *only after* the shell config file append operation succeeds. This prevents the prompt from being suppressed if the write fails (e.g. read-only filesystem or permission error).
- Defer configuration loading to minimize disk I/O on typical startup runs: check if the environment variable `TERMSTORY_MISSING_TIMESTAMPS` is `"1"` first before importing/calling `load_config()`.
- Updated CLI tests in `test_cli_commands.py` to mock `get_config_path` and assert that the prompt saves the flag. Added a regression test calling the CLI twice sequentially to ensure the prompt is successfully suppressed on the second run.

---

## 2. Fix AI Error Surfacing and Timestamp Detective Wiring

### Problems
1. **AI Silent Failures**: When the configured LLM API failed (due to incorrect API key, network timeout, rate limiting, or connection error), `_send_llm_request()` caught all exceptions and silently returned `None`. The TUI and CLI did not show any error or indication, leaving the user with blank sessions and no diagnostic information.
2. **Missing Project Paths in Detective**: The `TimestampDetective` was always initialized with `project_paths = []`, preventing it from locating local Git repositories to correlate commits for older legacy commands.
3. **Capped Git Ingestion Window**: Git commit ingestion was hardcoded to 90 days, which meant recovered sessions older than 90 days did not receive their corresponding commits even if resolved successfully by the Timestamp Detective.
4. **AI Disabled Notification**: When installed fresh, the default AI provider is `"disabled"`, and there was no post-onboarding indication to show how to configure/enable it.

### Fixes
- **Detailed Thread-Safe AI Error Tracking**:
  - Implemented module-level error tracking in `termstory/ai.py` using `threading.local()` to maintain separate error states for concurrent @work background threads.
  - Updated `_send_llm_request` to clear thread-local error state on start and capture exception messages, normalized and truncated to 200 characters to prevent UI clutter.
  - Added specialized handling for `urllib.error.HTTPError` to decode and extract error messages directly from JSON response bodies returned by the LLM providers (e.g., Groq's or OpenAI's API error payloads).
  - Updated `termstory/tui.py`'s single, bulk, and timeframe generation error paths to surface these captured error messages inside notification toasts.
  - Added unit tests in `tests/test_ai_error_surfacing.py` verifying correct error capture, clearing, HTTP JSON parsing, and concurrent thread isolation.
- **Interactive AI Onboarding Reminder**:
  - Added a one-time reminder printed to the console when exiting the TUI, gated by `has_seen_onboarding_reminder` flag, showing exactly how to configure the AI provider and set the API key.
  - Registered `"has_seen_onboarding_reminder": False` in config defaults.
  - Added warning diagnostics to stderr if configuration file saving fails.
  - Added a unit test verifying one-time reminder printing and subsequent suppression.
- **Git Repository Discovery**:
  - Implemented automatic git project path scanning in `cli.py:run_ingestion()`. Scans up to 2 levels deep in `["~/Projects", "~/src", "~/Developer", "~/Code", "~/Work"]` and 1 level deep in `["~"]` using `glob` to find `.git` folders.
  - Sorted discovered `project_paths` deterministically to ensure reproducible recovery tie-breaking.
  - Propagated discovered `project_paths` through `parse_all_histories` to `parse_zsh_history`, which passes them to the `TimestampDetective`.
  - Added unit test in `tests/test_parser.py` validating that the project paths parameter is correctly propagated, with environment variables cleanly cleared via monkeypatch.
- **Dynamic Commit Ingestion Timeframe & Configurable Timeout**:
  - Updated the git commit ingestion window in `cli.py` to dynamically adjust `since_ts` back to the oldest parsed command's timestamp (minus a 1-day buffer) if older commands exist. This ensures that recovered legacy commands get correct commit linkages.
  - Added support for a configurable `timeout` parameter inside `get_project_commits()` in `git_integration.py`. If deep history ingestion (older than 90 days) is active, a longer 30-second timeout is assigned to prevent subprocess timeouts in large repositories, keeping the common 90-day fast path capped at 10 seconds.
- **Copilot PR Review Improvements (HTTPError Body extraction & Lazy project_paths scan)**:
  - Updated HTTPError extraction to handle empty response bodies gracefully by falling back to `e.reason`.
  - Normalized all spaces and newlines (via `" ".join(str.split())`) on surfaced HTTPError messages to match generic exception format paths and prevent bad formatting in UI toasts.
  - Refactored project repository scanning (`discover_project_paths`) in `cli.py` to run lazily. Discovered paths are passed as a callable which is only executed inside the Zsh history parser when legacy commands are actually encountered, preventing startup/search slowdowns for fully timestamped histories.
  - Added unit test `test_parse_all_histories_project_paths_propagation_callable` in `tests/test_parser.py` and `test_http_error_empty_body_fallback_to_reason`/`test_http_error_whitespace_normalization` in `tests/test_ai_error_surfacing.py`.

---

