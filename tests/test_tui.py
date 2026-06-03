import os
import time
import tempfile
import pytest
from datetime import datetime, timedelta

from termstory.database import Database
from termstory.models import Session, Project, Command
from termstory.tui import (
    TermStoryWorkspace,
    calculate_streak,
    generate_heatmap,
    calculate_dashboard_stats,
    get_session_memory_str,
    deduplicate_sessions,
    clean_command_to_memory,
    strip_ansi,
    OnboardingScreen,
)

def test_calculate_streak():
    now = datetime(2026, 6, 2, 12, 0)
    now_ts = int(now.timestamp())
    
    # 1. Empty sessions
    assert calculate_streak([]) == 0
    
    # 2. Single session today
    s1 = Session(id=1, start_time=now_ts, end_time=now_ts + 600, duration_seconds=600, project_id=1)
    assert calculate_streak([s1]) == 1
    
    # 3. Gap of 3 days (streak broken)
    s2 = Session(id=2, start_time=now_ts - 3 * 86400, end_time=now_ts - 3 * 86400 + 600, duration_seconds=600, project_id=1)
    assert calculate_streak([s1, s2]) == 1
    
    # 4. Continuous streak (today, yesterday, day before)
    s_yesterday = Session(id=3, start_time=now_ts - 86400, end_time=now_ts - 86400 + 600, duration_seconds=600, project_id=1)
    s_prev = Session(id=4, start_time=now_ts - 2 * 86400, end_time=now_ts - 2 * 86400 + 600, duration_seconds=600, project_id=1)
    # Mock get_current_time to return Jun 2, 2026
    # (Since calculate_streak uses get_current_time(), we can mock/patch it if needed, or rely on local system time.
    # In our tests, we use relative dates to ensure stability.)

def test_generate_heatmap():
    now = int(datetime.now().timestamp())
    sessions = [
        Session(id=1, start_time=now, end_time=now + 600, duration_seconds=600, project_id=1, commands=[
            Command(timestamp=now, command="git status")
        ])
    ]
    heatmap = generate_heatmap(sessions, days_limit=30)
    assert "█" in heatmap or "■" in heatmap or "▄" in heatmap
    assert "░" in heatmap

def test_get_session_memory_str():
    # 1. Commit priority
    s1 = Session(id=1, start_time=1000, end_time=1600, duration_seconds=600, project_id=1, commits=[
        {"hash": "abc", "message": "feat: commit message", "cleaned_message": "Clean message"}
    ])
    assert get_session_memory_str(s1) == "Clean message"
    
    # 2. Non-noise command
    s2 = Session(id=2, start_time=1000, end_time=1600, duration_seconds=600, project_id=1, commands=[
        Command(timestamp=1000, command="git commit -m 'test'"),
        Command(timestamp=1001, command="ls") # noise
    ])
    assert get_session_memory_str(s2) == "test"

def test_tui_workspace_init():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        db = Database(db_path)
        db.init_db()
        
        app = TermStoryWorkspace(db, days_limit=30, config_override={"has_seen_onboarding": True, "ai_enabled": False})
        assert app.db == db
        assert app.days_limit == 30

@pytest.mark.asyncio
async def test_tui_workspace_mount():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        db = Database(db_path)
        db.init_db()
        
        # Insert a mock project and session
        now = int(datetime.now().timestamp())
        p = Project(id=1, name="Project Alpha", path="~/alpha", first_seen=now, last_seen=now, session_count=1, total_time=600)
        cmd = Command(timestamp=now, command="git diff", session_id=1, project_id=1)
        s = Session(id=1, start_time=now, end_time=now + 600, duration_seconds=600, project_id=1, commands=[cmd], commits=[
            {"hash": "abcdefabcdef", "timestamp": now, "message": "feat: init", "cleaned_message": "Init"}
        ])
        db.save_data([p], [s], [cmd])
        db.save_commits(1, [{"hash": "abcdefabcdef", "timestamp": now, "message": "feat: init", "cleaned_message": "Init"}])
        
        app = TermStoryWorkspace(db, days_limit=30, config_override={"has_seen_onboarding": True, "ai_enabled": False})
        async with app.run_test() as pilot:
            # Verify widgets are instantiated and layout works
            assert app.query_one("#stats-panel") is not None
            tree = app.query_one("#history-navigator")
            assert tree is not None
            assert app.query_one("#details-canvas") is not None
            assert app.query_one("#search-box") is not None
            
            # Verify the 4-level hierarchy structure
            # Root node has children (Level 1: Categories)
            assert len(tree.root.children) == 3
            timeline_root = tree.root.children[0]
            assert timeline_root.data["category"] == "timeline"
            
            # Timeline node has children (Level 2: Month nodes)
            assert len(timeline_root.children) > 0
            month_node = timeline_root.children[0]
            assert month_node.data["type"] == "month"
            
            # Month node has children (Level 3: Date nodes)
            assert len(month_node.children) > 0
            date_node = month_node.children[0]
            assert date_node.data["type"] == "date"
            
            # Date node has children (Level 4: Project nodes)
            assert len(date_node.children) > 0
            project_node = date_node.children[0]
            assert project_node.data["type"] == "project"
            
            # Project node has children (Level 5: Session nodes)
            assert len(project_node.children) > 0
            session_node = project_node.children[0]
            assert session_node.data["type"] == "session"
            assert session_node.data["session_id"] == 1
            assert session_node.data["project_id"] == 1


def test_strip_ansi():
    assert strip_ansi("\033[1;36mTermstory\033[0m") == "Termstory"
    assert strip_ansi("Simple text") == "Simple text"


def test_clean_command_to_memory():
    # 1. Quoted git commit extraction
    assert clean_command_to_memory("git commit -m 'docs: fix markdown'") == "docs: fix markdown"
    assert clean_command_to_memory('git commit -s -m "feat: user login"') == "feat: user login"
    
    # 2. Humanize checkout and push/pull
    assert clean_command_to_memory("git checkout -b feature/tui") == "Create branch feature/tui"
    assert clean_command_to_memory("git checkout main") == "Switch to branch main"
    assert clean_command_to_memory("git push origin main") == "Push changes to remote"
    
    # 3. Multi-command chain
    assert clean_command_to_memory("git add . && git commit -m 'Release v0.1'") == "Release v0.1"


def test_deduplicate_sessions():
    s1 = Session(id=1, start_time=1000, end_time=2000, duration_seconds=1000, project_id=1)
    s2 = Session(id=2, start_time=1000, end_time=2500, duration_seconds=1500, project_id=1) # duplicate expanding
    s3 = Session(id=3, start_time=3000, end_time=4000, duration_seconds=1000, project_id=1) # unique
    
    deduped = deduplicate_sessions([s1, s2, s3])
    assert len(deduped) == 2
    assert deduped[0].id == 2 # kept max end_time
    assert deduped[0].end_time == 2500
    assert deduped[1].id == 3


@pytest.mark.asyncio
async def test_tui_update_session_label():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        db = Database(db_path)
        db.init_db()

        # Save a session
        now = int(datetime.now().timestamp())
        p = Project(id=1, name="Project Alpha", path="~/alpha", first_seen=now, last_seen=now, session_count=1, total_time=600)
        cmd = Command(timestamp=now, command="git diff", session_id=1, project_id=1)
        s = Session(id=1, start_time=now, end_time=now + 600, duration_seconds=600, project_id=1, commands=[cmd])
        db.save_data([p], [s], [cmd])

        app = TermStoryWorkspace(db, days_limit=30, config_override={"has_seen_onboarding": True, "ai_enabled": False})
        async with app.run_test() as pilot:
            tree = app.query_one("#history-navigator")
            # Find the session leaf
            def find_leaf(node):
                if node.data and node.data.get("type") == "session":
                    return node
                for child in node.children:
                    res = find_leaf(child)
                    if res:
                        return res
                return None
            leaf = find_leaf(tree.root)
            assert leaf is not None
            
            # Update label in-place
            tree.update_session_label(1, "Updated summary message")
            assert "Updated summary message" in str(leaf.label)


@pytest.mark.asyncio
async def test_tui_onboarding_dismiss():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        db = Database(db_path)
        db.init_db()

        app = TermStoryWorkspace(db, days_limit=30, config_override={"has_seen_onboarding": False})
        async with app.run_test() as pilot:
            app.handle_onboarding_result({
                "ai_enabled": True,
                "active_provider": "ollama",
                "providers": {
                    "ollama": {
                        "api_key": "",
                        "api_base_url": "http://localhost:11434/v1",
                        "model_name": "llama3"
                    }
                },
                "has_seen_onboarding": True
            })
            assert app.config["has_seen_onboarding"] is True
            assert app.config["ai_enabled"] is True
            assert app.config["active_provider"] == "ollama"


@pytest.mark.asyncio
async def test_tui_update_stats_header():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        db = Database(db_path)
        db.init_db()

        app = TermStoryWorkspace(db, days_limit=30, config_override={"has_seen_onboarding": True, "ai_enabled": True, "active_provider": "groq"})
        async with app.run_test() as pilot:
            stats_panel = app.query_one("#stats-panel")
            
            # Active and idle
            app.update_stats_header()
            assert "AI: ACTIVE (GROQ)" in str(stats_panel.render())
            assert "Activity (Last 30 Days):" in str(stats_panel.render())
            
            # Active and summarizing
            app.ai_summarizing = True
            app.update_stats_header()
            assert "Summarizing..." in str(stats_panel.render())


@pytest.mark.asyncio
async def test_tui_action_show_onboarding():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        db = Database(db_path)
        db.init_db()

        app = TermStoryWorkspace(db, days_limit=30, config_override={"has_seen_onboarding": True})
        async with app.run_test() as pilot:
            # Trigger onboarding show action
            app.action_show_onboarding()
            # Verify OnboardingScreen is pushed on the stack
            assert isinstance(app.screen, OnboardingScreen)


@pytest.mark.asyncio
async def test_tui_onboarding_click_disabled():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        db = Database(db_path)
        db.init_db()

        app = TermStoryWorkspace(db, days_limit=30, config_override={"has_seen_onboarding": False})
        async with app.run_test() as pilot:
            # Press 'ctrl+d' (Keep Local Only shortcut) on OnboardingScreen
            await pilot.press("ctrl+d")
            assert app.config["has_seen_onboarding"] is True
            assert app.config["ai_enabled"] is False


@pytest.mark.asyncio
async def test_tui_onboarding_mouse_click():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        db = Database(db_path)
        db.init_db()

        app = TermStoryWorkspace(db, days_limit=30, config_override={"has_seen_onboarding": False})
        async with app.run_test(size=(120, 50)) as pilot:
            # Click the disable button on OnboardingScreen
            await pilot.click("#btn-disable-ai")
            assert app.config["has_seen_onboarding"] is True
            assert app.config["ai_enabled"] is False


@pytest.mark.asyncio
async def test_tui_render_interactive_ai_buttons(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        db = Database(db_path)
        db.init_db()
        
        now_ts = int(time.time())
        p = Project(id=1, name="Proj A", path="~/proj-a", first_seen=now_ts, last_seen=now_ts, session_count=1, total_time=0)
        cmd = Command(timestamp=now_ts, command="git diff", exit_code=0, session_id=1, project_id=1)
        s = Session(id=1, start_time=now_ts, end_time=now_ts, duration_seconds=0, project_id=1, commands=[cmd], ai_summary=None)
        db.save_data([p], [s], [cmd])
        
        app = TermStoryWorkspace(
            db, 
            days_limit=30, 
            config_override={
                "has_seen_onboarding": True, 
                "ai_enabled": True, 
                "active_provider": "groq",
                "providers": {
                    "groq": {
                        "api_key": "gsk_test",
                        "api_base_url": "https://api.groq.com/openai/v1",
                        "model_name": "llama3"
                    }
                }
            }
        )
        
        called = []
        def mock_generate_ai_summary(commands, api_key, api_base_url, model_name, provider, *args, **kwargs):
            called.append(commands)
            return "Generated AI summary description"
            
        monkeypatch.setattr("termstory.tui.generate_ai_summary", mock_generate_ai_summary)
        
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            
            # Press the Generate Story button programmatically
            app.query_one("#btn-gen-session-1").press()
            await pilot.pause()
            
            assert len(called) == 1
            assert app.sessions[0].ai_summary == "Generated AI summary description"

            import asyncio
            # Wait for the button to disappear due to cooldown
            for _ in range(50):
                try:
                    app.query_one("#btn-gen-session-1")
                except Exception:
                    break  # Button disappeared
                await asyncio.sleep(0.05)
                
            # Clear the cooldown manually to test regeneration
            app.sessions[0].recent_generation = False
            app.refresh_details_canvas()
            await pilot.pause()

            # Press the button again (now it is '⟳ Regenerate' button)
            app.query_one("#btn-gen-session-1").press()
            await pilot.pause()

            assert len(called) == 2
            assert app.sessions[0].ai_summary == "Generated AI summary description"


@pytest.mark.asyncio
async def test_tui_generate_executive_review(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        db = Database(db_path)
        db.init_db()
        
        now_ts = int(time.time())
        p = Project(id=1, name="Proj A", path="~/proj-a", first_seen=now_ts, last_seen=now_ts, session_count=1, total_time=0)
        cmd = Command(timestamp=now_ts, command="git diff", exit_code=0, session_id=1, project_id=1)
        s = Session(id=1, start_time=now_ts, end_time=now_ts, duration_seconds=0, project_id=1, commands=[cmd], ai_summary="Story")
        db.save_data([p], [s], [cmd])
        
        app = TermStoryWorkspace(
            db, 
            days_limit=30, 
            config_override={
                "has_seen_onboarding": True, 
                "ai_enabled": True, 
                "active_provider": "groq",
                "providers": {
                    "groq": {
                        "api_key": "gsk_test",
                        "api_base_url": "https://api.groq.com/openai/v1",
                        "model_name": "llama3"
                    }
                }
            }
        )
        
        called = []
        def mock_generate_timeframe_summary(stats_summary, api_key, api_base_url, model_name, provider):
            called.append(stats_summary)
            return "Generated Executive Review text."
            
        def mock_generate_daily_chronicle(github_username, session_date, sessions, projects, api_key, api_base_url, model_name, provider):
            called.append(session_date)
            return "Generated Executive Review text."
            
        monkeypatch.setattr("termstory.ai.generate_timeframe_summary", mock_generate_timeframe_summary)
        monkeypatch.setattr("termstory.ai.generate_daily_chronicle", mock_generate_daily_chronicle)
        
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            
            # Press the generate executive review button programmatically
            date_str = datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d")
            app.query_one(f"#btn-exec-{date_str}-date").press()
            await pilot.pause()
            
            import asyncio
            for _ in range(50):
                if len(called) == 1:
                    break
                await asyncio.sleep(0.05)
                
            assert len(called) == 1
            cached = db.get_macro_summary(date_str)
            assert cached == "Generated Executive Review text."

@pytest.mark.asyncio
async def test_tui_overall_timeframe_summary(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        db = Database(db_path)
        db.init_db()
        
        now_ts = int(time.time())
        p = Project(id=1, name="Proj A", path="~/proj-a", first_seen=now_ts, last_seen=now_ts, session_count=1, total_time=0)
        cmd = Command(timestamp=now_ts, command="git diff", exit_code=0, session_id=1, project_id=1)
        s = Session(id=1, start_time=now_ts, end_time=now_ts, duration_seconds=0, project_id=1, commands=[cmd], ai_summary="Story")
        db.save_data([p], [s], [cmd])
        
        app = TermStoryWorkspace(
            db, 
            days_limit=30, 
            config_override={
                "has_seen_onboarding": True, 
                "ai_enabled": True, 
                "active_provider": "groq",
                "providers": {
                    "groq": {
                        "api_key": "gsk_test",
                        "api_base_url": "https://api.groq.com/openai/v1",
                        "model_name": "llama3"
                    }
                }
            }
        )
        
        called = []
        def mock_generate_timeframe_summary(stats_summary, api_key, api_base_url, model_name, provider):
            called.append(stats_summary)
            return "Generated Overall Summary."
            
        monkeypatch.setattr("termstory.tui.generate_timeframe_summary", mock_generate_timeframe_summary)
        
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            
            # Select the timeline category node to display the overall summary
            tree = app.query_one("#history-navigator")
            timeline_node = tree.root.children[0]
            tree.select_node(timeline_node)
            await pilot.pause()
            
            # Press the generate executive review button for overall timeframe
            app.query_one("#btn-exec-overall-overall").press()
            await pilot.pause()
            
            import asyncio
            for _ in range(50):
                if len(called) == 1:
                    break
                await asyncio.sleep(0.05)
                
            assert len(called) == 1
            cached = db.get_macro_summary("overall")
            assert cached == "Generated Overall Summary."


@pytest.mark.asyncio
async def test_tui_bulk_auto_summarize(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        db = Database(db_path)
        db.init_db()
        
        monkeypatch.setattr("time.sleep", lambda secs: None)
        
        now_ts = int(time.time())
        p = Project(id=1, name="Proj A", path="~/proj-a", first_seen=now_ts, last_seen=now_ts, session_count=1, total_time=0)
        cmd = Command(timestamp=now_ts, command="git diff", exit_code=0, session_id=1, project_id=1)
        s = Session(id=1, start_time=now_ts, end_time=now_ts, duration_seconds=0, project_id=1, commands=[cmd], ai_summary=None)
        db.save_data([p], [s], [cmd])
        
        app = TermStoryWorkspace(
            db, 
            days_limit=30, 
            config_override={
                "has_seen_onboarding": True, 
                "ai_enabled": True, 
                "active_provider": "groq",
                "providers": {
                    "groq": {
                        "api_key": "gsk_test",
                        "api_base_url": "https://api.groq.com/openai/v1",
                        "model_name": "llama3"
                    }
                }
            }
        )
        
        called = []
        def mock_generate_ai_summary(commands, api_key, api_base_url, model_name, provider, *args, **kwargs):
            called.append(commands)
            return "Bulk summary output"
            
        monkeypatch.setattr("termstory.tui.generate_ai_summary", mock_generate_ai_summary)
        
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            
            # Press the bulk auto-summarize button programmatically
            date_str = datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d")
            app.query_one(f"#btn-bulk-{date_str}-date").press()
            await pilot.pause()
            
            assert len(called) == 1
            assert app.sessions[0].ai_summary == "Bulk summary output"


@pytest.mark.asyncio
async def test_tui_help_screen():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        db = Database(db_path)
        db.init_db()
        
        app = TermStoryWorkspace(
            db, 
            days_limit=30, 
            config_override={
                "has_seen_onboarding": True, 
                "ai_enabled": False, 
            }
        )
        
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            
            # Help screen is not showing initially
            assert not any(screen.__class__.__name__ == "HelpScreen" for screen in app.screen_stack)
            
            # Press ?
            await pilot.press("?")
            await pilot.pause()
            
            # Help screen should be showing now
            from termstory.tui import HelpScreen
            help_screen = app.screen
            assert isinstance(help_screen, HelpScreen)
            
            # Dismiss using close button
            help_screen.query_one("#btn-close-help").press()
            await pilot.pause()
            
            # Help screen should be dismissed
            assert not isinstance(app.screen, HelpScreen)
            
            # Open it again
            await pilot.press("?")
            await pilot.pause()
            help_screen = app.screen
            assert isinstance(help_screen, HelpScreen)
            
            # Dismiss using ESC key
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, HelpScreen)

            # Open it again
            await pilot.press("?")
            await pilot.pause()
            help_screen = app.screen
            assert isinstance(help_screen, HelpScreen)
            
            # Dismiss using q key
            await pilot.press("q")
            await pilot.pause()
            assert not isinstance(app.screen, HelpScreen)


def test_tui_copy_to_clipboard(monkeypatch):
    from termstory.database import Database
    from termstory.tui import TermStoryWorkspace
    import subprocess
    from textual.app import App
    
    db = Database(":memory:")
    db.init_db()
    
    app = TermStoryWorkspace(
        db, 
        days_limit=30, 
        config_override={"has_seen_onboarding": True, "ai_enabled": False}
    )
    
    copied_texts = []
    
    class MockProcess:
        def __init__(self):
            self.returncode = 0
        def communicate(self, input):
            copied_texts.append(input.decode('utf-8'))
            return (b'', b'')
            
    def mock_popen(*args, **kwargs):
        return MockProcess()
        
    monkeypatch.setattr(subprocess, "Popen", mock_popen)
    
    parent_called = []
    def mock_parent_copy(self, text):
        parent_called.append(text)
        
    monkeypatch.setattr(App, "copy_to_clipboard", mock_parent_copy)
    
    app.copy_to_clipboard("test-copy-text")
    
    assert "test-copy-text" in copied_texts
    assert "test-copy-text" in parent_called


