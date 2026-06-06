import os
import re
from datetime import datetime
from typing import List, Optional
from termstory.models import Command

def clean_command(cmd_str: str) -> Optional[str]:
    """Clean the command string: strip whitespace and join multiline commands with spaces"""
    cleaned = re.sub(r'\\\s*\n', ' ', cmd_str)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return None
    return cleaned

def parse_zsh_history(filepath: str) -> List[Command]:
    """Parse a Zsh history file containing ': <timestamp>:<duration>;<command>' format"""
    commands = []
    if not os.path.exists(filepath):
        return commands

    # Match ': 1748851200:0;git status' style lines
    pattern = re.compile(r'^:\s*(\d+):(\d+);(.*)$')
    
    current_timestamp = None
    current_duration = None
    current_command_parts = []
    
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            match = pattern.match(line)
            if match:
                # Save previous command if we have one pending
                if current_timestamp is not None:
                    cmd_str = "".join(current_command_parts)
                    cmd_cleaned = clean_command(cmd_str)
                    if cmd_cleaned:
                        commands.append(Command(
                            timestamp=current_timestamp,
                            command=cmd_cleaned,
                            exit_code=0,
                            duration=current_duration
                        ))
                
                # Start new command parsing
                current_timestamp = int(match.group(1))
                current_duration = int(match.group(2))
                current_command_parts = [match.group(3)]
            else:
                # Continuation of multiline command if the previous line ended with a backslash
                if current_timestamp is not None:
                    if current_command_parts and current_command_parts[-1].rstrip().endswith('\\'):
                        # Strip trailing backslash and ensure a space separates the parts
                        current_command_parts[-1] = current_command_parts[-1].rstrip()[:-1] + " "
                        current_command_parts.append(line)
                    
        # Save last command
        if current_timestamp is not None:
            cmd_str = "".join(current_command_parts)
            cmd_cleaned = clean_command(cmd_str)
            if cmd_cleaned:
                commands.append(Command(
                    timestamp=current_timestamp,
                    command=cmd_cleaned,
                    exit_code=0,
                    duration=current_duration
                ))

    # Filtering logic
    now = int(datetime.now().timestamp())
    five_years_ago = now - (5 * 365 * 24 * 60 * 60)
    
    filtered_commands = []
    for cmd in commands:
        if cmd.timestamp < five_years_ago:
            continue
        if cmd.timestamp > now:
            continue
        filtered_commands.append(cmd)
        
    filtered_commands.sort(key=lambda x: x.timestamp)
    return filtered_commands

def parse_bash_history(filepath: str) -> List[Command]:
    """Parse Bash history. Reads standard commands, using #<timestamp> lines if present, 
    otherwise falls back to spacing command timestamps backward from file modification time."""
    commands = []
    if not os.path.exists(filepath):
        return commands
        
    try:
        mtime = int(os.path.getmtime(filepath))
    except Exception:
        mtime = int(datetime.now().timestamp())
        
    raw_lines = []
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            raw_lines.append(line)
            
    # Pattern to match #1620000000 style timestamp lines
    timestamp_pattern = re.compile(r'^#(\d{10})$')
    
    temp_commands = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        line_stripped = line.strip()
        if not line_stripped:
            i += 1
            continue
        
        match = timestamp_pattern.match(line_stripped)
        if match:
            # Timestamp line. The next lines form the command
            timestamp = int(match.group(1))
            i += 1
            cmd_lines = []
            while i < len(raw_lines):
                next_line = raw_lines[i]
                next_line_stripped = next_line.strip()
                if timestamp_pattern.match(next_line_stripped):
                    break
                cmd_lines.append(next_line)
                i += 1
                if cmd_lines and not cmd_lines[-1].rstrip().endswith('\\'):
                    break
                    
            cmd_str = "".join(cmd_lines)
            cmd_cleaned = clean_command(cmd_str)
            if cmd_cleaned:
                temp_commands.append((timestamp, cmd_cleaned))
        else:
            # Command lines without timestamp header
            cmd_lines = [line]
            i += 1
            while i < len(raw_lines):
                if cmd_lines and not cmd_lines[-1].rstrip().endswith('\\'):
                    break
                next_line = raw_lines[i]
                next_line_stripped = next_line.strip()
                if timestamp_pattern.match(next_line_stripped):
                    break
                cmd_lines.append(next_line)
                i += 1
                
            cmd_str = "".join(cmd_lines)
            cmd_cleaned = clean_command(cmd_str)
            if cmd_cleaned:
                temp_commands.append((None, cmd_cleaned))
                
    # Assign timestamps if missing
    commands_to_return = []
    has_any_timestamps = any(t is not None for t, _ in temp_commands)
    
    if not has_any_timestamps:
        # None of the commands have timestamps (standard Bash default setup)
        # Space them backward from the file modification time
        start_time = mtime - (len(temp_commands) * 10)
        for idx, (t, cmd) in enumerate(temp_commands):
            commands_to_return.append(Command(
                timestamp=start_time + (idx * 10),
                command=cmd,
                exit_code=0,
                duration=None
            ))
    else:
        # Resolve mixture of timestamps or missing timestamps
        resolved_timestamps = [t for t, _ in temp_commands]
        n = len(temp_commands)
        
        first_known_idx = -1
        for idx in range(n):
            if resolved_timestamps[idx] is not None:
                first_known_idx = idx
                break
                
        if first_known_idx == -1:
            first_known_timestamp = mtime
        else:
            first_known_timestamp = resolved_timestamps[first_known_idx]
            
        # Backward fill
        for idx in range(first_known_idx - 1, -1, -1):
            resolved_timestamps[idx] = resolved_timestamps[idx + 1] - 10
            
        # Forward fill
        for idx in range(1, n):
            if resolved_timestamps[idx] is None:
                resolved_timestamps[idx] = resolved_timestamps[idx - 1] + 10
                
        for idx, (t, cmd) in enumerate(temp_commands):
            commands_to_return.append(Command(
                timestamp=resolved_timestamps[idx],
                command=cmd,
                exit_code=0,
                duration=None
            ))
            
    # Standard filtering (older than 5 years or future timestamps)
    now = int(datetime.now().timestamp())
    five_years_ago = now - (5 * 365 * 24 * 60 * 60)
    
    filtered_commands = []
    for cmd in commands_to_return:
        if cmd.timestamp < five_years_ago:
            continue
        if cmd.timestamp > now:
            continue
        filtered_commands.append(cmd)
        
    filtered_commands.sort(key=lambda x: x.timestamp)
    return filtered_commands

def parse_all_histories(filepaths: List[str]) -> List[Command]:
    """Parse all listed history files, merge and deduplicate them, and sort by timestamp"""
    all_commands = []
    for path in filepaths:
        filename = os.path.basename(path).lower()
        if "zsh" in filename:
            all_commands.extend(parse_zsh_history(path))
        elif "bash" in filename:
            all_commands.extend(parse_bash_history(path))
        else:
            # Fallback to bash parser for unknown file types
            all_commands.extend(parse_bash_history(path))
            
    # Deduplicate by (timestamp, command text)
    seen = set()
    deduped_commands = []
    for cmd in all_commands:
        key = (cmd.timestamp, cmd.command)
        if key not in seen:
            seen.add(key)
            deduped_commands.append(cmd)
            
    deduped_commands.sort(key=lambda x: x.timestamp)
    return deduped_commands
