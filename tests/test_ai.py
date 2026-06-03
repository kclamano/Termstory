import json
import urllib.request
import urllib.error
from io import BytesIO
from termstory.ai import generate_ai_summary, generate_timeframe_summary

class MockResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status = status_code
        
    def read(self):
        return self.data
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

def test_ai_disabled():
    res = generate_ai_summary(["git status"], "key", "http://base", "model", "disabled")
    assert res is None

def test_ai_blacklisted():
    res = generate_ai_summary(["vault read secret"], "key", "http://base", "model", "groq")
    assert res == "Security/Authentication Operations"

def test_ai_success_groq(monkeypatch):
    called = []
    
    def mock_urlopen(req, timeout=None):
        called.append(req)
        # Assertions on the request
        assert req.get_header("Content-type") == "application/json"
        assert req.get_header("Authorization") == "Bearer test-key"
        assert req.full_url == "https://api.groq.com/openai/v1/chat/completions"
        
        # Verify body
        body = json.loads(req.data.decode("utf-8"))
        assert body["model"] == "llama3"
        assert "Translate the developer's raw shell commands and Git commits" in body["messages"][0]["content"]
        
        resp_payload = {
            "choices": [
                {
                    "message": {
                        "content": "Fixed integration tests"
                    }
                }
            ]
        }
        return MockResponse(json.dumps(resp_payload).encode("utf-8"))
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    res = generate_ai_summary(
        ["pytest tests/"],
        "test-key",
        "https://api.groq.com/openai/v1",
        "llama3",
        "groq"
    )
    assert len(called) == 1
    assert res == "Fixed integration tests"

def test_ai_success_ollama(monkeypatch):
    called = []
    
    def mock_urlopen(req, timeout=None):
        called.append(req)
        assert req.get_header("Authorization") is None # No auth key for Ollama
        assert req.full_url == "http://localhost:11434/v1/chat/completions"
        
        resp_payload = {
            "choices": [
                {
                    "message": {
                        "content": "\"Run local migrations\"" # With quotes to test trimming
                    }
                }
            ]
        }
        return MockResponse(json.dumps(resp_payload).encode("utf-8"))
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    res = generate_ai_summary(
        ["python3 manage.py migrate"],
        "",
        "http://localhost:11434/v1",
        "llama3",
        "ollama"
    )
    assert len(called) == 1
    assert res == "Run local migrations"

def test_ai_failure_exception(monkeypatch):
    def mock_urlopen(req, timeout=None):
        raise urllib.error.URLError("Connection refused")
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    res = generate_ai_summary(
        ["pytest tests/"],
        "test-key",
        "https://api.groq.com/openai/v1",
        "llama3",
        "groq"
    )
    assert res is None


def test_ai_url_normalization(monkeypatch):
    test_urls = [
        "https://api.groq.com/openai/v1/",
        "https://api.groq.com/openai/v1",
        "https://api.groq.com/openai/v1/chat/completions",
        "https://api.groq.com/openai/v1/chat/completions/"
    ]
    
    for url in test_urls:
        called_url = []
        def mock_urlopen(req, timeout=None):
            called_url.append(req.full_url)
            resp_payload = {
                "choices": [{"message": {"content": "Tested URL normalization"}}]
            }
            return MockResponse(json.dumps(resp_payload).encode("utf-8"))
            
        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
        res = generate_ai_summary(
            ["pytest tests/"],
            "test-key",
            url,
            "llama3",
            "groq"
        )
        assert res == "Tested URL normalization"
        assert len(called_url) == 1
        assert called_url[0] == "https://api.groq.com/openai/v1/chat/completions"


def test_ai_empty_or_blank_key(monkeypatch):
    blank_keys = ["", "   ", None]
    for key in blank_keys:
        called = []
        def mock_urlopen(req, timeout=None):
            called.append(req)
            assert req.get_header("Authorization") is None
            resp_payload = {
                "choices": [{"message": {"content": "Tested blank key"}}]
            }
            return MockResponse(json.dumps(resp_payload).encode("utf-8"))
            
        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
        res = generate_ai_summary(
            ["pytest tests/"],
            key,
            "https://api.groq.com/openai/v1",
            "llama3",
            "groq"
        )
        assert res == "Tested blank key"
        assert len(called) == 1


def test_ai_invalid_url():
    # If base url is empty or None, it should return None immediately without making request
    res = generate_ai_summary(
        ["pytest tests/"],
        "test-key",
        "",
        "llama3",
        "groq"
    )
    assert res is None
    
    res2 = generate_ai_summary(
        ["pytest tests/"],
        "test-key",
        None,
        "llama3",
        "groq"
    )
    assert res2 is None


def test_ai_generate_executive_review(monkeypatch):
    called = []
    def mock_urlopen(req, timeout=None):
        called.append(req)
        assert req.get_header("Content-type") == "application/json"
        assert req.get_header("Authorization") == "Bearer test-key"
        
        # Verify body
        body = json.loads(req.data.decode("utf-8"))
        assert body["model"] == "gpt-4o"
        assert "Write a highly-personalized, modern engineering review" in body["messages"][0]["content"]
        
        resp_payload = {
            "choices": [
                {
                    "message": {
                        "content": "Worked on TermStory and added tests."
                    }
                }
            ]
        }
        return MockResponse(json.dumps(resp_payload).encode("utf-8"))
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    res = generate_timeframe_summary(
        stats_summary="User worked 5h total. 100% on TermStory. 10 total Git commits.",
        api_key="test-key",
        api_base_url="https://api.openai.com/v1",
        model_name="gpt-4o",
        provider="openai"
    )
    assert len(called) == 1
    assert res == "Worked on TermStory and added tests."


def test_ai_summary_with_commits(monkeypatch):
    called = []
    
    def mock_urlopen(req, timeout=None):
        called.append(req)
        body = json.loads(req.data.decode("utf-8"))
        content = body["messages"][0]["content"]
        assert "Git Commit Messages:" in content
        assert "feat: added onboarding" in content
        assert "fix: layout alignment" in content
        
        resp_payload = {
            "choices": [{"message": {"content": "Summary with commits."}}]
        }
        return MockResponse(json.dumps(resp_payload).encode("utf-8"))
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    res = generate_ai_summary(
        commands=["git commit -m 'feat: added onboarding'"],
        api_key="test-key",
        api_base_url="https://api.openai.com/v1",
        model_name="gpt-4o",
        provider="openai",
        commits=["feat: added onboarding", "fix: layout alignment"]
    )
    assert len(called) == 1
    assert res == "Summary with commits."


def test_daily_chronicle_prompt():
    from termstory.ai import generate_daily_chronicle_prompt
    from termstory.models import Session, Command, Project
    
    cmd = Command(timestamp=1780460000, command="vim main.py")
    s = Session(id=1, start_time=1780460000, end_time=1780461000, duration_seconds=1000, project_id=1, commands=[cmd])
    p = Project(id=1, name="TermStory", path="~/projects/termstory", first_seen=1780460000, last_seen=1780461000, session_count=1, total_time=1000)
    
    prompt = generate_daily_chronicle_prompt(
        github_username="@testuser",
        session_date="June 03, 2026",
        sessions=[s],
        projects=[p]
    )
    
    assert "@testuser" in prompt
    assert "June 03, 2026" in prompt
    assert "USE SECOND-PERSON" in prompt
    assert "DYNAMIC HANDLE" in prompt
    assert "INFER HUMANITY" in prompt
    assert "NO CORPORATE SLOP" in prompt



