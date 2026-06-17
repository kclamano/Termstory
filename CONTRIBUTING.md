# Contributing to TermStory

Thank you for your interest in contributing to TermStory! Here is a brief guide to help you get started.

## Dev Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/termstory.git
   cd termstory
   ```
2. Install the package in editable mode with development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

## Running Tests

To run the test suite, simply use pytest:
```bash
python3 -m pytest tests/ -v
```

## Code Style

TermStory is designed as a **personal developer memory engine** that prioritizes recognition and clarity. Please adhere to the following code style philosophy:

*   **Density over decoration**: Avoid rounded panels, double borders, or nested boxes. Use clean column alignment, simple tables, and minimal spacing.
*   **Strictly banned**: The use of `rich.panel.Panel` is strictly banned in favor of dense text separators to maintain this philosophy.

## Submitting PRs

*   **Branch naming**: Use descriptive branch names like `feature/new-cli-command`, `bugfix/issue-123`, or `docs/update-readme`.
*   **Commit messages**: Use clear, concise commit messages. A good format is `[Scope] Short description`, for example, `[Parser] Fix bug in zsh history parsing`.

## Adding a New CLI Command

To add a new command to the TermStory CLI:
1.  Define the command logic and interface in `termstory/cli.py`.
2.  If the command requires new formatted output, add the rendering logic to `termstory/formatter.py`.
