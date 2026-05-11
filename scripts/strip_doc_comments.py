"""
strip_doc_comments.py
Purpose: Remove ALL [DOC] explanatory comments from every project file in seconds,
         leaving only essential operational comments.

Usage:
    python3 scripts/strip_doc_comments.py              # dry run — shows counts only
    python3 scripts/strip_doc_comments.py --apply      # actually removes comments

Supported file types and their [DOC] comment format:
    .py / .sh / .yaml / .yml  →  # [DOC] explanation text
    .sql                       →  -- [DOC] explanation text
    .md                        →  <!-- [DOC] explanation text -->  (single-line HTML comment)

What it does:
    - Removes every line whose first non-space content matches the [DOC] prefix above
    - Collapses 3+ consecutive blank lines into 2 (cosmetic cleanup only)
    - Writes back in-place (original is overwritten — use git to undo if needed)

What it does NOT touch:
    - Regular comments, docstrings, or any line without the [DOC] tag
    - Third-party dirs: .venv, venv310, __pycache__, .git, node_modules
    - .json files (JSON has no comment syntax — [DOC] is not applicable there)

Reversibility:
    All changes are tracked by git.  To undo: git checkout -- .
    Or selectively:  git diff --name-only | xargs git checkout --
"""

import os
import re
import sys
import glob

# ── Configuration ─────────────────────────────────────────────────────────────

# Directories to skip entirely (build artifacts, not project source)
SKIP_DIRS = {'.venv', 'venv310', '__pycache__', '.git', 'node_modules'}

# File extensions → regex that matches a [DOC] line in that format
EXTENSIONS = {
    '.py':   r'^\s*#\s*\[DOC\]',          # Python:   # [DOC] ...
    '.sql':  r'^\s*--\s*\[DOC\]',         # SQL:      -- [DOC] ...
    '.sh':   r'^\s*#\s*\[DOC\]',          # Bash:     # [DOC] ...
    '.yaml': r'^\s*#\s*\[DOC\]',          # YAML:     # [DOC] ...
    '.yml':  r'^\s*#\s*\[DOC\]',          # YAML:     # [DOC] ...
    '.md':   r'^\s*<!--\s*\[DOC\].*-->',  # Markdown: <!-- [DOC] ... -->
}

# Project root (one level above this script)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Core logic ────────────────────────────────────────────────────────────────

def should_skip(path: str) -> bool:
    """Return True if this path is inside a directory we want to ignore."""
    parts = path.replace(PROJECT_ROOT, '').split(os.sep)
    return any(part in SKIP_DIRS for part in parts)


def strip_file(filepath: str, pattern: str, apply: bool) -> int:
    """
    Strip [DOC] lines from one file.
    Returns the number of lines removed.
    If apply=False, just counts without writing.
    """
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    stripped = []
    removed = 0
    blank_streak = 0

    for line in lines:
        if re.match(pattern, line):
            # This is a [DOC] comment — skip it
            removed += 1
        else:
            # Cosmetic: collapse more than 2 consecutive blank lines into 2
            if line.strip() == '':
                blank_streak += 1
                if blank_streak > 2:
                    continue  # drop the extra blank line
            else:
                blank_streak = 0
            stripped.append(line)

    if apply and removed > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(stripped)

    return removed


def run(apply: bool) -> None:
    """Walk the project tree, process every eligible file."""
    total_files = 0
    total_lines_removed = 0
    changed_files = []

    for ext, pattern in EXTENSIONS.items():
        for filepath in glob.glob(f'{PROJECT_ROOT}/**/*{ext}', recursive=True):
            if should_skip(filepath):
                continue

            removed = strip_file(filepath, pattern, apply)
            if removed > 0:
                rel = os.path.relpath(filepath, PROJECT_ROOT)
                changed_files.append((rel, removed))
                total_lines_removed += removed
            total_files += 1

    # ── Report ─────────────────────────────────────────────────────────────
    mode = 'APPLIED' if apply else 'DRY RUN'
    print(f'\n[{mode}] Scanned {total_files} files')
    print(f'[{mode}] Files with [DOC] comments: {len(changed_files)}')
    print(f'[{mode}] Total [DOC] lines {"removed" if apply else "found"}: {total_lines_removed}')

    if changed_files:
        print(f'\nFiles affected:')
        for rel, count in sorted(changed_files):
            print(f'  {count:4d} lines  {rel}')

    if not apply:
        print(f'\nTo apply: python3 scripts/strip_doc_comments.py --apply')
    else:
        print(f'\nDone. Use  git diff  to review changes.')
        print(f'To undo:   git checkout -- .')


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    apply_flag = '--apply' in sys.argv
    run(apply=apply_flag)
