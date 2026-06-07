import os
from termstory.parser import parse_zsh_history, parse_bash_history, parse_all_histories, clean_command
from termstory.models import Command

def test_clean_command():
    assert clean_command("   git    status   ") == "git status"
    assert clean_command("echo \\\n  hello \\\n  world") == "echo hello world"
    assert clean_command("   ") is None

def test_parse_zsh_history_valid_file():
    # Use our fixture
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_history.txt")
    commands = parse_zsh_history(fixture_path)
    
    # 7 commands are in the fixture
    assert len(commands) == 7
    assert all(isinstance(c, Command) for c in commands)
    # Check that they are sorted
    assert commands[0].timestamp < commands[-1].timestamp
    
    # Check commands content
    assert commands[0].command == "git status"
    assert commands[0].timestamp == 1748851200
    assert commands[2].command == "cd ~/Project/incubator-hugegraph"
    assert commands[4].command == 'echo "Hello World"'  # multiline joined

def test_parse_zsh_history_malformed_lines(tmp_path):
    # Create a history file with valid and malformed lines
    temp_file = tmp_path / "zsh_malformed_test"
    temp_file.write_text(
        ": 1748851200:0;git status\n"
        "random malformed line without colon\n"
        ": 1748851210:0;docker ps\n"
        ": invalid_timestamp:0;should skip\n"
    )
    
    commands = parse_zsh_history(str(temp_file))
    assert len(commands) == 2
    assert commands[0].command == "git status"
    assert commands[1].command == "docker ps"

def test_parse_bash_history_with_timestamps(tmp_path):
    temp_file = tmp_path / "bash_timestamps_test"
    temp_file.write_text(
        "#1748851200\n"
        "git status\n"
        "#1748851210\n"
        "docker ps\n"
    )
    
    commands = parse_bash_history(str(temp_file))
    assert len(commands) == 2
    assert commands[0].timestamp == 1748851200
    assert commands[0].command == "git status"
    assert commands[1].timestamp == 1748851210
    assert commands[1].command == "docker ps"

def test_parse_bash_history_without_timestamps(tmp_path):
    temp_file = tmp_path / "bash_no_timestamps_test"
    temp_file.write_text(
        "git status\n"
        "docker ps\n"
    )
    
    # Set the file's modification time to a known value
    known_mtime = 1748851220
    os.utime(str(temp_file), (known_mtime, known_mtime))
    
    commands = parse_bash_history(str(temp_file))
    assert len(commands) == 2
    # Commands should be spaced out backward from mtime (which is 1748851220)
    # len(temp_commands) is 2, so start_time is mtime - 2 * 10 = 1748851200
    # idx 0: 1748851200
    # idx 1: 1748851210
    assert commands[0].timestamp == 1748851200
    assert commands[0].command == "git status"
    assert commands[1].timestamp == 1748851210
    assert commands[1].command == "docker ps"

def test_parse_zsh_history_legacy_fallback(tmp_path):
    temp_file = tmp_path / "zsh_legacy_test"
    temp_file.write_text(
        "git status\n"
        "docker ps\n"
    )
    
    # Set the file's modification time to a known value
    known_mtime = 1748851220
    os.utime(str(temp_file), (known_mtime, known_mtime))
    
    commands = parse_zsh_history(str(temp_file))
    assert len(commands) == 2
    
    # 1-Second Step-Back:
    # last command gets known_mtime (1748851220)
    # preceding command gets known_mtime - 1 (1748851219)
    assert commands[0].timestamp == 1748851219
    assert commands[0].command == "git status"
    assert commands[1].timestamp == 1748851220
    assert commands[1].command == "docker ps"

def test_parse_zsh_history_hybrid_mode(tmp_path):
    temp_file = tmp_path / "zsh_hybrid_test"
    temp_file.write_text(
        "git pull\n"
        "git status\n"
        ": 1748851200:0;git commit -m 'feat'\n"
        "malformed line to ignore\n"
        ": 1748851210:0;git push\n"
        ": invalid:0;ignored too\n"
    )
    
    commands = parse_zsh_history(str(temp_file))
    assert len(commands) == 4
    
    assert commands[0].command == "git pull"
    assert commands[0].timestamp == 1748851139
    
    assert commands[1].command == "git status"
    assert commands[1].timestamp == 1748851140
    
    assert commands[2].command == "git commit -m 'feat'"
    assert commands[2].timestamp == 1748851200
    
    assert commands[3].command == "git push"
    assert commands[3].timestamp == 1748851210

def test_parse_zsh_history_locking(tmp_path):
    temp_file = tmp_path / "zsh_locking_test"
    temp_file.write_text(
        "git status\n"
        ": 1748851200:0;git commit\n"
    )
    
    existing_lookup = {
        "git status": [1748850000],
        "git commit": [1748851200]
    }
    
    commands = parse_zsh_history(str(temp_file), existing_lookup=existing_lookup)
    assert len(commands) == 2
    
    assert commands[0].command == "git status"
    assert commands[0].timestamp == 1748850000
    
    assert commands[1].command == "git commit"
    assert commands[1].timestamp == 1748851200

def test_parse_all_histories_project_paths_propagation(monkeypatch, tmp_path):
    temp_file = tmp_path / "zsh_test_history"
    temp_file.write_text("git status\n")
    
    received_project_paths = []
    
    class MockTimestampDetective:
        def __init__(self, search_root, project_paths):
            nonlocal received_project_paths
            received_project_paths.extend(project_paths)
            
        def resolve_all(self, items):
            return [{"command": "git status", "is_legacy_still": True, "detected_ts": 1748851220, "detected_source": "Mock"}]
            
    monkeypatch.setattr("termstory.parser.TimestampDetective", MockTimestampDetective)
    
    parse_all_histories([str(temp_file)], project_paths=["/path/to/project-a", "/path/to/project-b"])
    
    assert "/path/to/project-a" in received_project_paths
    assert "/path/to/project-b" in received_project_paths
