import os
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union, Callable
from termstory.models import Command
from termstory.timestamp_detective import TimestampDetective

def clean_command(cmd_str: str) -> Optional[str]:
    """Clean the command string: strip whitespace and join multiline commands with spaces"""
    cleaned = re.sub(r'\\\s*\n', ' ', cmd_str)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return None
    return cleaned

def parse_zsh_history(
    filepath: str,
    existing_lookup: Optional[Dict[str, List[int]]] = None,
    project_paths: Optional[Union[List[str], Callable[[], List[str]]]] = None
) -> List[Command]:
    """Parse a Zsh history file containing ': <timestamp>:<duration>;<command>' format.
    Handles legacy command lines, timestamped command lines, and multiline command continuations
    gracefully in Zsh extended history mode, Legacy Fallback Mode, and Hybrid/Mixed history mode.
    """
    commands = []
    if not os.path.exists(filepath):
        return commands

    raw_lines = []
    try:
        # Use errors='replace' instead of 'ignore' so Zsh metafied bytes (0x83)
        # are replaced with a safe placeholder instead of silently eaten,
        # guaranteeing the rest of the file continues to be read.
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                raw_lines.append(line)
    except Exception:
        return commands

    pattern = re.compile(r'^:\s*(\d+):(\d+);(.*)$')
    
    # Find the index of the first line that matches the timestamped pattern
    first_timestamped_idx = None
    for idx, line in enumerate(raw_lines):
        if pattern.match(line):
            first_timestamped_idx = idx
            break
            
    parsed_items = []  # List[dict]: {"timestamp": Optional[int], "duration": Optional[int], "command": str}
    
    current_timestamp = None
    current_duration = None
    current_command_parts = []
    
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        match = pattern.match(line)
        if match:
            # We found a timestamped line. First, save any pending command
            if current_command_parts:
                cmd_str = "".join(current_command_parts)
                cmd_cleaned = clean_command(cmd_str)
                if cmd_cleaned:
                    parsed_items.append({
                        "timestamp": current_timestamp,
                        "duration": current_duration,
                        "command": cmd_cleaned
                    })
            
            # Start new timestamped command
            current_timestamp = int(match.group(1))
            current_duration = int(match.group(2))
            current_command_parts = [match.group(3)]
            i += 1
            
            # Consume multiline continuations
            while i < len(raw_lines):
                if current_command_parts and not current_command_parts[-1].rstrip().endswith('\\'):
                    break
                next_line = raw_lines[i]
                if pattern.match(next_line):
                    break
                # Strip trailing backslash and append
                current_command_parts[-1] = current_command_parts[-1].rstrip()[:-1] + " "
                current_command_parts.append(next_line)
                i += 1
        else:
            # Determine if this line should be treated as a legacy command or skipped/ignored
            is_legacy = False
            if first_timestamped_idx is None:
                # 100% legacy file fallback: treat non-colon lines as legacy commands
                if not line.startswith(':'):
                    is_legacy = True
            else:
                # Hybrid/Mixed history file mode:
                # Only treat lines BEFORE the first timestamped line as legacy commands
                # and ignore colon-prefixed malformed lines, or lines after first timestamped.
                if i < first_timestamped_idx and not line.startswith(':'):
                    is_legacy = True
            
            if is_legacy:
                # We found a legacy line. First, save any pending command
                if current_command_parts:
                    cmd_str = "".join(current_command_parts)
                    cmd_cleaned = clean_command(cmd_str)
                    if cmd_cleaned:
                        parsed_items.append({
                            "timestamp": current_timestamp,
                            "duration": current_duration,
                            "command": cmd_cleaned
                        })
                
                # Start new legacy command (no timestamp/duration)
                current_timestamp = None
                current_duration = None
                current_command_parts = [line]
                i += 1
                
                # Consume multiline continuations
                while i < len(raw_lines):
                    if current_command_parts and not current_command_parts[-1].rstrip().endswith('\\'):
                        break
                    next_line = raw_lines[i]
                    if pattern.match(next_line):
                        break
                    # Strip trailing backslash and append
                    current_command_parts[-1] = current_command_parts[-1].rstrip()[:-1] + " "
                    current_command_parts.append(next_line)
                    i += 1
            else:
                # Skip this line (malformed or trailing garbage in timestamped mode)
                i += 1

    # Save last pending command
    if current_command_parts:
        cmd_str = "".join(current_command_parts)
        cmd_cleaned = clean_command(cmd_str)
        if cmd_cleaned:
            parsed_items.append({
                "timestamp": current_timestamp,
                "duration": current_duration,
                "command": cmd_cleaned
            })

    # Separate timestamped and legacy items
    timestamped_items = [item for item in parsed_items if item["timestamp"] is not None]
    legacy_items = [item for item in parsed_items if item["timestamp"] is None]

    if legacy_items:
        # Flag missing/legacy timestamps for white-glove onboarding consent
        os.environ["TERMSTORY_MISSING_TIMESTAMPS"] = "1"

    # ── Resolve the base anchor_time used for commands the Detective can't place ──
    # Get file mtime as a common reference point — used in both branches below.
    try:
        file_mtime = int(os.path.getmtime(filepath))
    except Exception:
        file_mtime = int(datetime.now().timestamp())

    n_legacy = len(legacy_items)

    CHUNK_SIZE = 20
    n_legacy_chunks = (n_legacy + CHUNK_SIZE - 1) // CHUNK_SIZE
    legacy_window = max(n_legacy_chunks * 86400, 365 * 86400)

    if timestamped_items:
        oldest_ts = min(item["timestamp"] for item in timestamped_items)
        # Push anchor back so the spread window has room behind the oldest real timestamp.
        natural_anchor = oldest_ts - legacy_window
        anchor_time = min(natural_anchor, file_mtime - 60)
    else:
        # 100% legacy (no EXTENDED_HISTORY ever): anchor at file mtime pushed back
        # by the full window duration.
        anchor_time = file_mtime - legacy_window

    # ── Build the final list of Commands ────────────────────────────────────────
    # Apply the database timestamp-locking lookup so synthetic timestamps are stable
    # across repeated parse runs (prevents legacy command timestamps from "shifting").
    consumed: Dict[str, int] = {}  # command_str -> how many times we've consumed it

    def resolve_timestamp(cmd: str, fallback_ts: int) -> int:
        """Return the locked DB timestamp for this command if one exists, else the fallback."""
        if existing_lookup and cmd in existing_lookup:
            ts_list = existing_lookup[cmd]
            idx = consumed.get(cmd, 0)
            if idx < len(ts_list):
                consumed[cmd] = idx + 1
                return ts_list[idx]
        return fallback_ts

    resolved_commands: List[Command] = []

    # ── Phase 1: Run the Timestamp Detective on all legacy items ─────────────────
    # The Detective tries to recover real timestamps using:
    #   A. Virtual CWD tracking (cd/pushd/popd replay)
    #   B. Five detectors: git commit, file stat, package manager, docker, lockfiles
    #   C. Anchor interpolation between discovered timestamps
    # Items that the Detective resolves get is_legacy=False and a recovery_source string.
    # Truly unresolvable items get placed by the classic 1-second step-back below.
    if legacy_items:
        resolved_paths = []
        if project_paths:
            try:
                resolved_paths = project_paths() if callable(project_paths) else project_paths
            except Exception:
                pass
        detective = TimestampDetective(
            search_root=os.path.expanduser("~"),
            project_paths=resolved_paths or []
        )
        enriched_legacy = detective.resolve_all(legacy_items)
    else:
        enriched_legacy = []

    # Split enriched legacy into:
    #   detective_resolved → Detective found real evidence (is_legacy_still=False)
    #   still_synthetic    → No evidence found; use 1-second step-back (is_legacy_still=True)
    detective_resolved = [e for e in enriched_legacy if not e["is_legacy_still"] and e["detected_ts"] is not None]
    still_synthetic    = [e for e in enriched_legacy if e["is_legacy_still"]]

    # ── Phase 2: Add Detective-resolved commands with real timestamps ─────────────
    for item in detective_resolved:
        ts = item["detected_ts"]
        resolved_ts = resolve_timestamp(item["command"], ts)
        resolved_commands.append(Command(
            timestamp=resolved_ts,
            command=item["command"],
            exit_code=0,
            duration=0,
            is_legacy=False,              # Real timestamp — promoted out of Legacy Archive
            recovery_source=item.get("detected_source")  # Chain of Custody attribution
        ))

    # ── Phase 3: Interpolated / step-back commands — still synthetic but placed ──
    # These include:
    #   - Commands interpolated between two anchors (have a detected_ts but is_legacy_still=True)
    #   - Commands in prefix/suffix gaps (step-back / step-forward from nearest anchor)
    #   - Truly unresolvable commands (detected_ts may be None → fall back to anchor_time)
    interpolated = [e for e in still_synthetic if e.get("detected_ts") is not None]
    unresolvable = [e for e in still_synthetic if e.get("detected_ts") is None]

    for item in interpolated:
        ts = item["detected_ts"]
        resolved_ts = resolve_timestamp(item["command"], ts)
        resolved_commands.append(Command(
            timestamp=resolved_ts,
            command=item["command"],
            exit_code=0,
            duration=0,
            is_legacy=True,               # Synthetic, but placed correctly in the timeline
            recovery_source=item.get("detected_source")  # e.g. "Interpolated (between X → Y)"
        ))

    # ── Phase 4: Step-back for truly unresolvable (no anchors found at all) ──────
    # Session-Preserving Burst Clustering:
    # Group commands into chunks to form synthetic sessions, snap the chunks to
    # working hours (weekdays, 9 AM - 6 PM), and separate internal commands by 10s.
    n_unresolvable = len(unresolvable)
    n_chunks = (n_unresolvable + CHUNK_SIZE - 1) // CHUNK_SIZE if n_unresolvable > 0 else 0
    window = max(n_chunks * 86400, 365 * 86400)

    last_snapped_base_ts = 0
    current_snapped_base_ts = 0

    for idx, item in enumerate(unresolvable):
        chunk_idx = idx // CHUNK_SIZE
        intra_chunk_idx = idx % CHUNK_SIZE

        if intra_chunk_idx == 0:
            fraction = chunk_idx / max(n_chunks, 1)
            chunk_base_ts = int(anchor_time + fraction * window)

            dt = datetime.fromtimestamp(chunk_base_ts)
            
            if dt.hour < 9:
                dt -= timedelta(days=1)
                dt = dt.replace(hour=16, minute=0, second=0)
            elif dt.hour >= 18:
                dt = dt.replace(hour=16, minute=0, second=0)
                
            if dt.weekday() >= 5:
                dt -= timedelta(days=(dt.weekday() - 4))
                dt = dt.replace(hour=16, minute=0, second=0)

            current_snapped_base_ts = int(dt.timestamp())
            
            if current_snapped_base_ts <= last_snapped_base_ts:
                current_snapped_base_ts = last_snapped_base_ts + 3600
                
            last_snapped_base_ts = current_snapped_base_ts + (CHUNK_SIZE * 10)

        fallback_ts = current_snapped_base_ts + (intra_chunk_idx * 10)
        resolved_ts = resolve_timestamp(item["command"], fallback_ts)
        resolved_commands.append(Command(
            timestamp=resolved_ts,
            command=item["command"],
            exit_code=0,
            duration=0,
            is_legacy=True,               # Fully synthetic — no evidence found
            recovery_source=None          # No attribution: Detective had nothing to work with
        ))

    # ── Add real timestamped commands (no Detective needed) ──────────────────────
    for item in timestamped_items:
        fallback_ts = item["timestamp"]
        resolved_ts = resolve_timestamp(item["command"], fallback_ts)
        resolved_commands.append(Command(
            timestamp=resolved_ts,
            command=item["command"],
            exit_code=0,
            duration=item["duration"]
            # is_legacy=False (default), recovery_source=None (default)
        ))

    # Standard filtering: drop impossibly old or future-dated commands
    now = int(datetime.now().timestamp())
    five_years_ago = now - (5 * 365 * 24 * 60 * 60)

    filtered_commands = [
        cmd for cmd in resolved_commands
        if five_years_ago <= cmd.timestamp <= now
    ]
    filtered_commands.sort(key=lambda x: x.timestamp)
    return filtered_commands

def parse_bash_history(
    filepath: str,
    existing_lookup: Optional[Dict[str, List[int]]] = None,
    project_paths: Optional[Union[List[str], Callable[[], List[str]]]] = None
) -> List[Command]:
    """Parse Bash history. Reads standard commands, using #<timestamp> lines if present, 
    otherwise falls back to spacing command timestamps backward from file modification time.
    """
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
    
    consumed = {}
    def resolve_timestamp(cmd: str, fallback_ts: int) -> int:
        if existing_lookup and cmd in existing_lookup:
            ts_list = existing_lookup[cmd]
            idx = consumed.get(cmd, 0)
            if idx < len(ts_list):
                consumed[cmd] = idx + 1
                return ts_list[idx]
        return fallback_ts

    if not has_any_timestamps:
        # None of the commands have timestamps (standard Bash default setup)
        CHUNK_SIZE = 20
        n_cmds = len(temp_commands)
        n_chunks = (n_cmds + CHUNK_SIZE - 1) // CHUNK_SIZE if n_cmds > 0 else 0
        window = max(n_chunks * 86400, 365 * 86400)
        start_time = mtime - window
        
        last_snapped_base_ts = 0
        current_snapped_base_ts = 0
        
        for idx, (t, cmd) in enumerate(temp_commands):
            chunk_idx = idx // CHUNK_SIZE
            intra_chunk_idx = idx % CHUNK_SIZE

            if intra_chunk_idx == 0:
                fraction = chunk_idx / max(n_chunks, 1)
                chunk_base_ts = int(start_time + fraction * window)

                dt = datetime.fromtimestamp(chunk_base_ts)
                
                if dt.hour < 9:
                    dt -= timedelta(days=1)
                    dt = dt.replace(hour=16, minute=0, second=0)
                elif dt.hour >= 18:
                    dt = dt.replace(hour=16, minute=0, second=0)
                    
                if dt.weekday() >= 5:
                    dt -= timedelta(days=(dt.weekday() - 4))
                    dt = dt.replace(hour=16, minute=0, second=0)

                current_snapped_base_ts = int(dt.timestamp())
                
                if current_snapped_base_ts <= last_snapped_base_ts:
                    current_snapped_base_ts = last_snapped_base_ts + 3600
                    
                last_snapped_base_ts = current_snapped_base_ts + (CHUNK_SIZE * 10)

            fallback_ts = current_snapped_base_ts + (intra_chunk_idx * 10)
            resolved_ts = resolve_timestamp(cmd, fallback_ts)
            commands_to_return.append(Command(
                timestamp=resolved_ts,
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
            fallback_ts = resolved_timestamps[idx]
            resolved_ts = resolve_timestamp(cmd, fallback_ts)
            commands_to_return.append(Command(
                timestamp=resolved_ts,
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

def parse_all_histories(
    filepaths: List[str],
    db: Optional[Any] = None,
    project_paths: Optional[Union[List[str], Callable[[], List[str]]]] = None
) -> List[Command]:
    """Parse all listed history files, merge and deduplicate them, and sort by timestamp"""
    existing_lookup = None
    if db is not None:
        try:
            existing_lookup = db.get_all_commands_lookup()
        except Exception:
            pass

    all_commands = []
    for path in filepaths:
        filename = os.path.basename(path).lower()
        if "zsh" in filename:
            all_commands.extend(parse_zsh_history(path, existing_lookup, project_paths=project_paths))
        elif "bash" in filename:
            all_commands.extend(parse_bash_history(path, existing_lookup, project_paths=project_paths))
        else:
            # Fallback to bash parser for unknown file types
            all_commands.extend(parse_bash_history(path, existing_lookup, project_paths=project_paths))
            
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
