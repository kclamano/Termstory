import os
import tempfile
import pytest
from termstory.project import find_project_root, humanize_project_name

def test_macos_quirks_project_resolution():
    with tempfile.TemporaryDirectory() as temp_dir:
        # 1. Simulate macOS Library / Application Support (blacklisted)
        library_path = os.path.join(temp_dir, "Users/name/Library/Application Support/MyApp")
        os.makedirs(library_path, exist_ok=True)
        
        # 2. Simulate macOS /Volumes external drive WITH a git repository
        volumes_git_path = os.path.join(temp_dir, "Volumes/External/MyProject")
        os.makedirs(os.path.join(volumes_git_path, ".git"), exist_ok=True)
        
        # 3. Simulate macOS /Volumes external drive WITHOUT markers
        volumes_no_marker_path = os.path.join(temp_dir, "Volumes/External/JustDocs")
        os.makedirs(volumes_no_marker_path, exist_ok=True)
        
        home = os.path.realpath(os.path.abspath(os.path.expanduser("~")))
        
        # For Library, since it contains a blacklisted word ("library") or is outside Home,
        # it should resolve to `home`. Wait, if we use temp_dir, temp_dir isn't Home!
        # find_project_root will see it's outside home and has no markers -> returns home.
        res1 = find_project_root(library_path)
        assert res1 == home, f"Expected {home}, got {res1}"
        
        # For external drive with .git, it should correctly resolve to the path containing .git
        res2 = find_project_root(volumes_git_path)
        assert res2 == os.path.realpath(volumes_git_path), f"Expected {os.path.realpath(volumes_git_path)}, got {res2}"
        
        # For external drive without markers, since it's outside home, it falls back to home
        res3 = find_project_root(volumes_no_marker_path)
        assert res3 == home, f"Expected {home}, got {res3}"

def test_macos_humanize_project_name():
    home = os.path.realpath(os.path.abspath(os.path.expanduser("~")))
    # Ensure fallback maps to "Home" which is treated as "Other" in TermStory UI
    assert humanize_project_name(home) == "Home"
    
    # Check volume extraction
    assert humanize_project_name("/Volumes/External/MyProject") == "Myproject"

from termstory.project import extract_cd_path

def test_extract_cd_path_macos_quotes():
    # macOS paths often have spaces and are quoted or escaped
    assert extract_cd_path('cd ~/Library/Application\\ Support/MyApp') == '~/Library/Application Support/MyApp'
    assert extract_cd_path('cd "/Volumes/External Drive/My Project"') == '/Volumes/External Drive/My Project'
    assert extract_cd_path("cd '/Volumes/External Drive/My Project'") == '/Volumes/External Drive/My Project'
