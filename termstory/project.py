import os
import re
from typing import List, Optional
from termstory.models import Session, Project

import shlex

def extract_cd_path(cmd_str: str) -> Optional[str]:
    """Extract directory path from a cd command"""
    try:
        tokens = shlex.split(cmd_str)
    except Exception:
        tokens = cmd_str.strip().split()
        
    if not tokens or tokens[0] != 'cd':
        return None
        
    # Filter out cd flags (like -P, -L, --, etc.)
    path_args = [t for t in tokens[1:] if not t.startswith('-')]
    if not path_args:
        # cd with no arguments defaults to ~ (home)
        return "~"
        
    # Take the first argument
    return path_args[0]

def humanize_project_name(path: str) -> str:
    """Humanize directory name (e.g. incubator-hugegraph -> Apache HugeGraph)"""
    if path == "~" or path == os.path.expanduser("~") or path == "/":
        return "Home"
        
    # Remove trailing slash
    normalized_path = path.rstrip('/')
    base_name = os.path.basename(normalized_path)
    if not base_name:
        return "Root"
        
    # Replace hyphens and underscores with spaces
    name = base_name.replace('-', ' ').replace('_', ' ')
    
    # Specific heuristics and capitalization replacements
    word_replacements = {
        "hugegraph": "HugeGraph",
        "incubator": "Apache",
    }
    
    words = name.split()
    processed_words = []
    for word in words:
        word_lower = word.lower()
        if word_lower in word_replacements:
            processed_words.append(word_replacements[word_lower])
        elif word_lower == "my":
            continue
        else:
            # Capitalize first letter
            processed_words.append(word.capitalize())
            
    if not processed_words:
        return base_name.capitalize()
        
    return " ".join(processed_words)

def detect_projects(sessions: List[Session]) -> List[Project]:
    """Detect projects from cd commands in sessions, humanize names, and update links in sessions/commands"""
    projects_dict = {}
    project_id_counter = 1
    
    # Sort sessions by start_time to keep timelines linear
    sorted_sessions = sorted(sessions, key=lambda s: s.start_time)
    
    for session in sorted_sessions:
        # Find cd commands
        cd_commands = []
        for cmd in session.commands:
            cmd_stripped = cmd.command.strip()
            # Must start with cd followed by space/tab/EOF
            if cmd_stripped == "cd" or cmd_stripped.startswith("cd ") or cmd_stripped.startswith("cd\t"):
                cd_commands.append(cmd)
                
        if cd_commands:
            # Look at the last cd command in the session
            last_cd = cd_commands[-1]
            path = extract_cd_path(last_cd.command)
            if path:
                # Normalize path to match duplicate projects
                norm_path = os.path.expanduser(path)
                norm_path = os.path.abspath(norm_path)
                
                if norm_path not in projects_dict:
                    name = humanize_project_name(path)
                    project = Project(
                        id=project_id_counter,
                        name=name,
                        path=path,
                        first_seen=session.start_time,
                        last_seen=session.end_time,
                        session_count=1,
                        total_time=session.duration_seconds
                    )
                    projects_dict[norm_path] = project
                    project_id_counter += 1
                else:
                    project = projects_dict[norm_path]
                    project.first_seen = min(project.first_seen, session.start_time)
                    project.last_seen = max(project.last_seen, session.end_time)
                    project.session_count += 1
                    project.total_time += session.duration_seconds
                    
                # Link session and commands to project
                session.project_id = project.id
                for cmd in session.commands:
                    cmd.project_id = project.id
        else:
            session.project_id = None
            for cmd in session.commands:
                cmd.project_id = None
                
    return list(projects_dict.values())
