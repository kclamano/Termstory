import urllib.request
import io
import json
from termstory.formatter import get_github_avatar_ascii, get_fallback_avatar_padded

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

def test_get_github_avatar_fallback_for_invalid():
    # If invalid or developer username, should return fallback immediately
    res = get_github_avatar_ascii("developer", width=12, height=7)
    assert res == get_fallback_avatar_padded(12, 7)
    
    res_other = get_github_avatar_ascii("Other", width=12, height=7)
    assert res_other == get_fallback_avatar_padded(12, 7)
    
    res_empty = get_github_avatar_ascii("", width=12, height=7)
    assert res_empty == get_fallback_avatar_padded(12, 7)

def test_get_github_avatar_fetch(monkeypatch):
    from PIL import Image
    import io
    import os
    import time
    
    test_user = f"octocat_test_{int(time.time())}"
    db_dir = os.path.expanduser("~/.termstory")
    disk_path = os.path.join(db_dir, f"avatar_{test_user}_2_2.txt")
    if os.path.exists(disk_path):
        try:
            os.remove(disk_path)
        except Exception:
            pass
            
    img = Image.new("RGBA", (2, 2), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    
    called = []
    def mock_urlopen(req, timeout=None):
        called.append(req.full_url)
        return MockResponse(png_bytes)
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    # First call will trigger background thread and return fallback
    res = get_github_avatar_ascii(test_user, width=2, height=2)
    assert res == get_fallback_avatar_padded(2, 2)
    
    # Wait for the background thread to finish
    for _ in range(20):
        time.sleep(0.05)
        # Check cache directly through get_github_avatar_ascii
        res2 = get_github_avatar_ascii(test_user, width=2, height=2)
        if res2 != get_fallback_avatar_padded(2, 2):
            break
            
    res_final = get_github_avatar_ascii(test_user, width=2, height=2)
    assert len(res_final) == 2
    assert len(res_final[0]) == 2
    # Verify that characters are Braille or space representation
    assert all(c == " " or (0x2800 <= ord(c) <= 0x28ff) for line in res_final for c in line)
    
    # Cleanup disk cache file
    if os.path.exists(disk_path):
        try:
            os.remove(disk_path)
        except Exception:
            pass
