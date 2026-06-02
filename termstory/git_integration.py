import os
import re
import subprocess
from typing import List, Dict

def is_git_repo(path: str) -> bool:
    """Check if the directory path is a valid git repository worktree"""
    abs_path = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
        return False
    try:
        # Check if the folder is inside a git work tree
        res = subprocess.run(
            ["git", "-C", abs_path, "rev-parse", "--is-inside-work-tree"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        return res.returncode == 0
    except Exception:
        return False

def clean_commit_message(message: str) -> str:
    """Clean commit message for display by removing emojis, JIRA codes, PR numbers, and prefixes"""
    if not message:
        return ""
        
    msg = message.strip()
    
    # 1. Strip raw emojis and miscellaneous symbols first (so they don't block start-of-line patterns)
    emoji_pattern = re.compile(
        '['
        '\U0001f600-\U0001f64f'  # emoticons
        '\U0001f300-\U0001f5ff'  # symbols & pictographs
        '\U0001f680-\U0001f6ff'  # transport & map symbols
        '\U0001f1e0-\U0001f1ff'  # flags
        '\U00002700-\U000027bf'  # dingbats
        '\U00002600-\U000026ff'  # misc symbols
        '\U0001f900-\U0001f9ff'  # supplemental symbols
        '\U0001fa70-\U0001faff'  # pictographs extended
        ']+', flags=re.UNICODE
    )
    msg = emoji_pattern.sub('', msg)
    msg = msg.strip()
    
    # 2. Strip :emoji: shorthand patterns
    msg = re.sub(r':[a-zA-Z0-9_\-+]+:', '', msg)
    msg = msg.strip()
    
    # 3. Strip any JIRA/issue reference like [ABC-123] or ABC-123 at the start
    msg = re.sub(r'^\[[A-Za-z]+-\d+\]\s*', '', msg)
    msg = re.sub(r'^[A-Za-z]+-\d+[:\s]\s*', '', msg)
    
    # 4. Strip conventional commit prefixes (e.g. feat: fix: chore: etc. with case-insensitive flag at the start)
    msg = re.sub(r'(?i)^(feat|fix|chore|docs|refactor|test|style|ci|perf|build)(?:\([a-zA-Z0-9_\-\/]+\))?:\s*', '', msg)
    
    # 5. Strip PR references at the end, e.g. '(#3044)' or ' #3044'
    msg = re.sub(r'\s*\(#\d+\)\s*$', '', msg)
    msg = re.sub(r'\s*#\d+\s*$', '', msg)
    
    # Strip extra whitespace and capitalize first letter
    msg = msg.strip()
    if msg:
        msg = msg[0].upper() + msg[1:]
        
    return msg

def get_project_commits(project_path: str, since_ts: int) -> List[Dict]:
    """Get recent commits for a project since a specific Unix timestamp"""
    abs_path = os.path.abspath(os.path.expanduser(project_path))
    if not is_git_repo(abs_path):
        return []
        
    try:
        # Run git log with since timestamp filter
        # %H: commit hash
        # %at: author date (Unix timestamp)
        # %s: commit subject line
        res = subprocess.run(
            [
                "git", "-C", abs_path, "log", 
                f"--since={since_ts}", 
                "--pretty=format:%H|%at|%s"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        if res.returncode != 0:
            return []
            
        commits = []
        for line in res.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            h, ts_str, raw_msg = parts
            try:
                ts = int(ts_str)
            except ValueError:
                continue
                
            cleaned = clean_commit_message(raw_msg)
            commits.append({
                "hash": h,
                "timestamp": ts,
                "message": raw_msg,
                "cleaned_message": cleaned
            })
        return commits
    except Exception:
        return []
