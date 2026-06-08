import os
import tempfile
import pytest
from termstory.parser import parse_zsh_history

def test_macos_zsh_history_parsing():
    # Construct a synthetic Zsh history file with macOS paths and multiline commands
    synthetic_history = """\
: 1680000000:0;cd /Volumes/External/MyProject
: 1680000100:5;git commit -m "feat: Add macOS support"
: 1680000200:0;cd ~/Library/Application\\ Support/MyApp
: 1680000300:2;defaults write com.apple.finder AppleShowAllFiles YES
: 1680000400:10;echo "Complex \\
multiline \\
macOS \\
command" > test.txt
"""
    
    with tempfile.TemporaryDirectory() as temp_dir:
        history_file = os.path.join(temp_dir, ".zsh_history")
        with open(history_file, 'w') as f:
            f.write(synthetic_history)
            
        commands = parse_zsh_history(history_file)
        
        # Verify timestamps and cleaning
        assert len(commands) == 5
        
        cmd1 = commands[0]
        assert cmd1.timestamp == 1680000000
        assert cmd1.command == "cd /Volumes/External/MyProject"
        
        cmd3 = commands[2]
        assert cmd3.timestamp == 1680000200
        # Check that backslash escaping in path is preserved or cleaned appropriately
        # 'clean_command' just strips multiline continuations and multiple spaces
        assert cmd3.command == "cd ~/Library/Application\\ Support/MyApp"
        
        cmd4 = commands[3]
        assert cmd4.timestamp == 1680000300
        assert cmd4.command == "defaults write com.apple.finder AppleShowAllFiles YES"
        
        # Multiline command should be squashed to a single line with spaces
        cmd5 = commands[4]
        assert cmd5.timestamp == 1680000400
        assert cmd5.command == 'echo "Complex multiline macOS command" > test.txt'
