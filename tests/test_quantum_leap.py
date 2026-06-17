import pytest
from termstory.parser import parse_zsh_history, parse_bash_history
from termstory.session import create_sessions

def test_zsh_quantum_leap_chaos(tmp_path):
    """
    Test TermStory's resilience against:
    - Negative timestamps
    - Future timestamps
    - DST backward jumps (1 hour regression)
    - Interleaved legacy commands in timestamped regions
    """
    history_file = tmp_path / ".zsh_history"
    
    content = """\
echo "legacy_start_1"
echo "legacy_start_2"
: 1698544800:0;echo "cmd_before_dst_1"
: 1698544900:0;echo "cmd_before_dst_2"
:: echo "interleaved_legacy_1"
: 1698541300:0;echo "cmd_dst_jump_back_1"
: 1698541400:0;echo "cmd_dst_jump_back_2"
:: echo "interleaved_legacy_2"
: -9999999:0;echo "cmd_negative_timestamp"
: 1698545000:0;echo "cmd_after_dst"
: 9999999999999:0;echo "cmd_future_timestamp"
"""
    history_file.write_text(content)
    
    commands = parse_zsh_history(str(history_file))
    sessions = create_sessions(commands)
    
    for s in sessions:
        assert s.duration_seconds >= 0, f"Session duration {s.duration_seconds} is below 0!"
        assert s.start_time >= 0, "Session start time is negative!"
        assert s.end_time >= s.start_time, "Session ends before it starts!"

def test_bash_quantum_leap_chaos(tmp_path):
    """
    Test Bash history parsing with temporal distortions.
    """
    history_file = tmp_path / ".bash_history"
    
    content = """\
#1698544800
echo "cmd_before_dst_1"
#1698544900
echo "cmd_before_dst_2"
#1698541300
echo "cmd_dst_jump_back_1"
#-9999999999
echo "cmd_negative_timestamp"
#9999999999999
echo "cmd_future_timestamp"
"""
    history_file.write_text(content)
    
    commands = parse_bash_history(str(history_file))
    sessions = create_sessions(commands)
    
    for s in sessions:
        assert s.duration_seconds >= 0, f"Session duration {s.duration_seconds} is below 0!"
        assert s.start_time >= 0, "Session start time is negative!"
        assert s.end_time >= s.start_time, "Session ends before it starts!"

