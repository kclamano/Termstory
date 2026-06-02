# TermStory

TermStory parses your local shell history, groups command executions into sessions, identifies projects, and provides a beautifully structured summary of what you did today.

## Features
* 📁 **Project Detection**: Extracts working directories from successful `cd` commands.
* ⏱️ **Session Grouping**: Automatically clusters commands into developer sessions based on 30+ minute gaps.
* 📋 **Daily summaries**: Quickly answer "What did I do today?" with `termstory today`.
* 🔒 **100% Local & Private**: All data is saved into a local SQLite database (`~/.termstory/termstory.db`).

## Installation

Install directly in development mode:
```bash
pip install -e .
```

Or install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### 1. Daily Summary
Show today's summary:
```bash
termstory today
```

Options:
* `--detailed`: Show all exact commands run inside each session.
* `--compare`: Compare today's project durations with yesterday's.
* `--stats`: Show a complete, sorted command execution count breakdown.

### 2. Weekly Summary
Show this week's (Monday-Sunday) work statistics:
```bash
termstory week
```

Options:
* `--last`: Show last week's summary instead of this week's.
* `--project NAME`: Filter the report to only show a specific project.
* `--detailed`: Show all exact commands in each session.

### 3. Monthly Summary
Show this month's summary of logged days, project times, and averages:
```bash
termstory month
```

Options:
* `[MONTH_YEAR]`: Query a specific month/year (e.g. `termstory month "June 2026"`).
* `--last`: Show last month's summary.
* `--detailed`: Show all exact commands in each session.

### 4. Project Details
Show a 30-day dashboard for a specific project:
```bash
termstory project <name>
```
*Supports fuzzy matching (e.g., `termstory project hugo` matches `Apache HugeGraph`).*

Options:
* `--last-week`: Show summary for last week instead of last 30 days.
* `--since YYYY-MM-DD`: Show summary since a specific date.
* `--files`: Show only the list of related files modified (inferred from editor commands).
* `--stats`: Show only top command statistics.

### 5. List All Projects
List all tracked projects ranked by total work time:
```bash
termstory projects
```

Options:
* `--sort [time|recent|name]`: Sort projects by total hours, last activity date, or alphabetically.

### 6. Date Override
Override the date for any subcommand or run a positional date query:
```bash
termstory 2026-06-02           # Runs today's summary for June 2nd
termstory --date 2026-06-02    # Runs today's summary for June 2nd
termstory --date 2026-06-02 week # Runs weekly summary for the week containing June 2nd
```

## Running Tests

Run the test suite using `pytest`:
```bash
pytest tests/
```
