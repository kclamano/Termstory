from termstory.models import Command, Session, Project
from termstory.project import detect_projects, extract_cd_path, humanize_project_name, disambiguate_project_names

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
    
    # New V2 rules
    assert humanize_project_name("learning-k8s") == "Kubernetes"
    assert humanize_project_name("test-tf-cli") == "Terraform CLI"
    assert humanize_project_name("my-sqlite-db") == "Sqlite Database"

def test_disambiguate_project_names():
    p1 = Project(id=1, name="HugeGraph", path="/home/user/projects/hugegraph", first_seen=0, last_seen=0, session_count=1, total_time=1)
    p2 = Project(id=2, name="HugeGraph", path="/home/user/personal/hugegraph", first_seen=0, last_seen=0, session_count=1, total_time=1)
    p3 = Project(id=3, name="Other", path="/home/user/projects/other", first_seen=0, last_seen=0, session_count=1, total_time=1)
    
    names = disambiguate_project_names([p1, p2, p3])
    
    assert names[1] == "HugeGraph (/home/user/projects)"
    assert names[2] == "HugeGraph (/home/user/personal)"
    assert names[3] == "Other" # Unchanged as it's unique

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
    
    # Session 3 inherits Project B because the simulated cwd persists
    assert s3.project_id == proj_b.id
    assert cmd5.project_id == proj_b.id

def test_find_project_root(tmp_path, monkeypatch):
    monkeypatch.setattr("os.path.expanduser", lambda path: str(tmp_path) if path == "~" else path)
    
    # 1. Create a directory structure with git root
    proj_dir = tmp_path / "Projects" / "my-awesome-repo"
    sub_dir = proj_dir / "subfolder" / "deep-nested"
    sub_dir.mkdir(parents=True)
    
    # Create a git marker
    git_dir = proj_dir / ".git"
    git_dir.mkdir()
    
    # Verify resolving sub_dir root finds the repo root
    from termstory.project import find_project_root
    assert find_project_root(str(sub_dir)) == str(proj_dir)
    
    # 2. Test common project marker file (e.g. package.json)
    package_dir = tmp_path / "Projects" / "node-project"
    nested_node = package_dir / "src" / "components"
    nested_node.mkdir(parents=True)
    
    package_json = package_dir / "package.json"
    package_json.touch()
    
    assert find_project_root(str(nested_node)) == str(package_dir)
    
    # 3. Test fallback with no markers under known Projects path
    fallback_dir = tmp_path / "Projects" / "fallback-project" / "sub" / "dir"
    fallback_dir.mkdir(parents=True)
    assert find_project_root(str(fallback_dir)) == str(tmp_path / "Projects" / "fallback-project")
