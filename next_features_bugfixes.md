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
- Restrict flag persistence: only save `has_seen_timestamp_prompt = True` on valid, explicit responses (`y`/`yes`/`n`/`no`/KeyboardInterrupt/EOF) to allow prompts to reappear if the user types invalid input.
- Updated CLI tests in `test_cli_commands.py` to mock `get_config_path` and assert that the prompt saves the flag. Added a regression test calling the CLI twice sequentially to ensure the prompt is successfully suppressed on the second run.

---
