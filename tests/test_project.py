from termstory.models import Command, Session
from termstory.project import detect_projects, extract_cd_path, humanize_project_name

def test_extract_cd_path():
    assert extract_cd_path("cd ~/projects/incubator-hugegraph") == "~/projects/incubator-hugegraph"
    assert extract_cd_path("cd -P /usr/local/bin") == "/usr/local/bin"
    assert extract_cd_path("cd") == "~"
    assert extract_cd_path("cd -- '/Users/test/Spaces Dir'") == "/Users/test/Spaces Dir"
    assert extract_cd_path("ls -l") is None

def test_humanize_project_name():
    assert humanize_project_name("~/projects/incubator-hugegraph") == "Apache HugeGraph"
    assert humanize_project_name("/Users/username/my-awesome-project") == "Awesome Project"
    assert humanize_project_name("~") == "Home"
    assert humanize_project_name("/") == "Home"
    assert humanize_project_name("/some/nested/directory-name_here") == "Directory Name Here"

def test_detect_projects():
    # Session 1: working in project A
    cmd1 = Command(timestamp=1000, command="cd ~/projects/incubator-hugegraph")
    cmd2 = Command(timestamp=1010, command="git status")
    s1 = Session(id=1, start_time=1000, end_time=1010, duration_seconds=10, project_id=None, commands=[cmd1, cmd2])
    
    # Session 2: working in project B
    cmd3 = Command(timestamp=2000, command="cd /Users/username/my-awesome-project")
    cmd4 = Command(timestamp=2020, command="python setup.py install")
    s2 = Session(id=2, start_time=2000, end_time=2020, duration_seconds=20, project_id=None, commands=[cmd3, cmd4])
    
    # Session 3: no cd commands
    cmd5 = Command(timestamp=3000, command="echo 'no projects here'")
    s3 = Session(id=3, start_time=3000, end_time=3000, duration_seconds=0, project_id=None, commands=[cmd5])
    
    projects = detect_projects([s1, s2, s3])
    
    # We should have exactly 2 projects detected
    assert len(projects) == 2
    
    # Verify Project A details
    proj_a = next(p for p in projects if "HugeGraph" in p.name)
    assert proj_a.path == "~/projects/incubator-hugegraph"
    assert proj_a.name == "Apache HugeGraph"
    assert s1.project_id == proj_a.id
    assert cmd1.project_id == proj_a.id
    assert cmd2.project_id == proj_a.id
    
    # Verify Project B details
    proj_b = next(p for p in projects if "Awesome" in p.name)
    assert proj_b.path == "/Users/username/my-awesome-project"
    assert s2.project_id == proj_b.id
    
    # Session 3 should remain unaffiliated
    assert s3.project_id is None
    assert cmd5.project_id is None
