import json
import urllib.request
import urllib.error
from io import BytesIO
from termstory.ai import (
    generate_ai_summary,
    get_last_ai_error,
    clear_last_ai_error
)

class MockHTTPResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.code = status_code
        self.reason = "Mocked Reason"
        
    def read(self):
        return self.data
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

def test_get_and_clear_error():
    clear_last_ai_error()
    assert get_last_ai_error() is None

def test_invalid_url_sets_error():
    clear_last_ai_error()
    res = generate_ai_summary(
        ["pytest tests/"],
        "test-key",
        "",
        "llama3",
        "groq"
    )
    assert res is None
    assert get_last_ai_error() == "API Base URL is not configured or invalid."

def test_url_error_sets_error(monkeypatch):
    clear_last_ai_error()
    
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
    assert "Connection refused" in get_last_ai_error()

def test_http_error_json_body_parsing(monkeypatch):
    clear_last_ai_error()
    
    def mock_urlopen(req, timeout=None):
        # Create an HTTPError with a json body containing an error message
        body = json.dumps({
            "error": {
                "message": "Invalid API Key provided"
            }
        }).encode("utf-8")
        fp = BytesIO(body)
        raise urllib.error.HTTPError(
            url="https://api.groq.com/openai/v1",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=fp
        )
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    res = generate_ai_summary(
        ["pytest tests/"],
        "test-key",
        "https://api.groq.com/openai/v1",
        "llama3",
        "groq"
    )
    assert res is None
    assert get_last_ai_error() == "HTTP Error 401: Invalid API Key provided"

def test_http_error_non_json_body_parsing(monkeypatch):
    clear_last_ai_error()
    
    def mock_urlopen(req, timeout=None):
        # Create an HTTPError with a non-json text body
        body = b"Service Unavailable"
        fp = BytesIO(body)
        raise urllib.error.HTTPError(
            url="https://api.groq.com/openai/v1",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=fp
        )
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    res = generate_ai_summary(
        ["pytest tests/"],
        "test-key",
        "https://api.groq.com/openai/v1",
        "llama3",
        "groq"
    )
    assert res is None
    assert get_last_ai_error() == "HTTP Error 503: Service Unavailable"
