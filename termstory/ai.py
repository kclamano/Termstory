import json
import urllib.request
import urllib.error
from typing import List, Optional
from termstory.sanitizer import sanitize_session_commands

def _send_llm_request(
    prompt: str,
    api_key: str,
    api_base_url: str,
    model_name: str,
    provider: str
) -> Optional[str]:
    """Shared helper to construct and send the OpenAI-compatible chat completion request."""
    if provider == "disabled":
        return None
        
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "TermStory/1.0"
    }
    if api_key and isinstance(api_key, str) and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
        
    # OpenAI compatibility endpoint (normalize trailing slash)
    if not api_base_url or not isinstance(api_base_url, str):
        return None
    endpoint = api_base_url.strip().rstrip('/')
    if not endpoint.endswith('/chat/completions'):
        endpoint = f"{endpoint}/chat/completions"
        
    body = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.0,
        "max_tokens": 500
    }
    
    req_data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(endpoint, data=req_data, headers=headers, method="POST")
    
    try:
        # Set a reasonable timeout for the TUI background thread
        with urllib.request.urlopen(req, timeout=15.0) as response:
            resp_data = response.read().decode("utf-8")
            resp_json = json.loads(resp_data)
            result = resp_json["choices"][0]["message"]["content"].strip()
            # Clean up any quotes added by the LLM
            if result.startswith('"') and result.endswith('"'):
                result = result[1:-1]
            if result.startswith("'") and result.endswith("'"):
                result = result[1:-1]
            return result
    except Exception:
        # Gracefully fail and return None
        return None

def generate_ai_summary(
    commands: List[str],
    api_key: str,
    api_base_url: str,
    model_name: str,
    provider: str,
    project_name: str = "Other",
    commits: Optional[List[str]] = None
) -> Optional[str]:
    """Scrub commands and query the configured LLM API (Groq or Ollama) to generate a summary."""
    if not commands:
        return None
        
    # 1. Sanitization Pipeline
    sanitized_cmds, is_blacklisted = sanitize_session_commands(commands)
    if is_blacklisted:
        return "Security/Authentication Operations"
        
    if not sanitized_cmds:
        return None
        
    # If AI provider is disabled, return None (fallback to local heuristics)
    if provider == "disabled":
        return None
        
    # 2. Formulate the prompt
    commands_block = "\n".join(f"- {cmd}" for cmd in sanitized_cmds)
    
    commits_block = ""
    if commits:
        unique_commits = sorted(list(set(commits)))
        commits_block = "\nGit Commit Messages:\n" + "\n".join(f"- {c}" for c in unique_commits)
        
    prompt = (
        "Translate the developer's raw shell commands and Git commits into a high-density, CLI-styled terminal log of their work session.\n\n"
        "YOUR CORE GOAL:\n"
        "Generate a 3-line bulleted dev log. It must resemble a clean, tech-dense terminal audit output using ASCII connection lines or tech symbols.\n\n"
        "Choose ONE of the following formats to return, matching the inputs:\n\n"
        "Format Option A (ASCII branch log style):\n"
        "[💻 Dev Log]\n"
        "├─ 🔨 Built: <short, punchy action phrase of what was built or coded, using tech keywords>\n"
        "├─ 🔧 Flow: <brief sequence of tools used, tests run, or configurations edited>\n"
        "└─ 🚀 Result: <final milestone shipped, fixed, or pushed>\n\n"
        "Format Option B (Tech bullet list style):\n"
        "[🤖 Codebase Pulse]\n"
        "• Hacked: <what was designed, refactored, or debugged>\n"
        "• Tooling: <commands run, docker setups, or libraries configured>\n"
        "• Outcome: <what was successfully verified, resolved, or shipped>\n\n"
        "Choose either Option A or Option B at random or based on the inputs to provide variation, but always output EXACTLY the selected format.\n"
        "Never output any paragraphs of text, conversational filler, markdown formatting, or surrounding quotes. Only return the raw 4 lines of console text.\n\n"
        "STYLE & TONE RULES:\n"
        "1. NO MARKETING FLUFF: Never write paragraphs like 'Ultimately, the hard work paid off...'. Keep it purely developer-centric and density-focused.\n"
        "2. START WITH ACTION VERBS: Each bullet line must start directly with an active, past-tense engineering verb (e.g., 'wired up', 'refactored', 'debugged', 'spun up', 'implemented').\n"
        "3. Keep each line extremely concise, informative, and technical.\n\n"
        "Input Data to Summarize:\n"
        f"Project: {project_name}\n"
        "Commands Executed:\n"
        f"{commands_block}\n"
        f"{commits_block}\n\n"
        "Output format: Return ONLY the raw, polished console text block. No markdown formatting, no conversational filler, and no surrounding quotes."
    )
    
    return _send_llm_request(prompt, api_key, api_base_url, model_name, provider)


def generate_timeframe_summary(
    stats_summary: str,
    api_key: str,
    api_base_url: str,
    model_name: str,
    provider: str
) -> Optional[str]:
    """Query LLM to generate a professional action-oriented summary of a timeframe."""
    if provider == "disabled":
        return None
        
    from termstory.formatter import get_operator_handle
    github_username = get_operator_handle()
    
    prompt = (
        "Write a highly-personalized, modern engineering review of the developer's work over this entire period based on their commits, session summaries, and tooling stats.\n\n"
        "You are the master narrator for termstory, a developer memory engine. "
        "Your task is to transform the provided developer's time logs, project distribution, commits, and tools into a highly-personalized, creative, and viral terminal chronicle summarizing their entire work period.\n\n"
        
        "YOUR CORE GOAL:\n"
        "Generate one of the following two high-density, console-styled reports. You must choose the format that best fits the input log context to tell a compelling story, but you must output EXACTLY the selected layout structure:\n\n"
        
        "--- FORMAT OPTION 1: THE \"TERMINAL WRAPPED\" (Spotify Wrapped Style) ---\n"
        "This layout must resemble a clean Spotify-Wrapped style CLI card using box drawing characters:\n"
        "┌──────────────────────────────────────────────────────────┐\n"
        "│ ✨ TERMINAL WRAPPED // <TIMEFRAME OR DATE RANGE>          │\n"
        "├──────────────────────────────────────────────────────────┤\n"
        "│ 🎭 ARCHETYPE: \"<Creative Developer Archetype based on work>\" │\n"
        "│               (<Witty sub-description about their stats>) │\n"
        "│                                                          │\n"
        "│ 🎧 TOP GENRE: <Main Tech/Domain category worked on>      │\n"
        "│                                                          │\n"
        "│ 🕒 TIME IN THE SHADOWS: <Total Hours logged>             │\n"
        "│ ├── Focus Distribution: <Percentages on top 2 projects>  │\n"
        "│ └── Heaviest Lift:     `<Key branch, commit or project>` │\n"
        "│                                                          │\n"
        "│ 📂 MOST-EDITED BUFFERS (The Time Sinks)                  │\n"
        "│ ├── 1. `<Project A / File>`       [XX% of time]          │\n"
        "│ ├── 2. `<Project B / File>`       [XX% of time]          │\n"
        "│ └── 3. `<Project C / File>`       [XX% of time]          │\n"
        "│                                                          │\n"
        "│ 🔴 MOMENT OF DESPAIR / GLORY                             │\n"
        "│ • <A funny, high-signal developer reality or debugging    │\n"
        "│   combat situation extracted from logs/commits>          │\n"
        "└──────────────────────────────────────────────────────────┘\n\n"
        
        "--- FORMAT OPTION 2: THE \"DEVELOPER RPG SPEC SHEET\" ---\n"
        "This layout must resemble a retro video game character sheet card:\n"
        "============================================================\n"
        "🎮 CHARACTER SHEET: @<username> // LEVEL <XX> <CLASS NAME>\n"
        "============================================================\n\n"
        "[⚔️ CHARACTER ATTRIBUTES]\n"
        " • CLASS:     <Witty class name based on tools, e.g. Graph Alchemist>\n"
        " • ALIGNMENT: <e.g. Chaotic Green (Tests pass but nobody knows why)>\n"
        " • WEAPON:    [list of top 3 tools/commands detected]\n"
        " • MANA:      <Witty coffee/espresso/late-night description>\n\n"
        "[📈 PERIOD COMBAT TELEMETRY]\n"
        " • CRIT STRIKE:       <A major achievement or refactor/deletion block>\n"
        " • STAMINA:           <Total hours logged> across <number of sessions> runs.\n"
        " • SHIELD ACCURACY:   <Estimation of success rate based on commits/activity>\n"
        " • SPELL COOLDOWN:    <Time spent waiting or building key things>\n\n"
        "[🎒 INVENTORY BUFFERS]\n"
        " ├── 🧪 `<Top Project A Name>` (<Focus hours or percentage>)\n"
        " ├── 💥 `<Top Project B Name>` (<Focus hours or percentage>)\n"
        " └── 🛡️ `<Top Project C Name>` (<Focus hours or percentage>)\n\n"
        "AI LORE SUMMARY: \"<2-sentence epic story of their developer journey during this timeframe>\"\n"
        "============================================================\n\n"
        
        "RULES FOR GENERATION:\n"
        "1. Start directly with the box outline or character sheet. Do not output any preamble, markdown code blocks, conversational filler, or surrounding quotes.\n"
        "2. Do not show empty brackets or placeholders. Extract names, project shares, and commit messages from the context.\n"
        "3. Incorporate actual telemetry: total hours, project distributions, git commit details, and tool keywords.\n"
        "4. Tone must be cool, modern, developer-to-developer, with dry humor, but authentic to the logged data.\n"
        "5. Output must fit in a single terminal screen/grid view cleanly.\n\n"
        f"Developer Work Log Context:\n"
        f"OPERATOR: {github_username}\n"
        f"{stats_summary}\n\n"
        "Output format: Return ONLY the raw, polished console card block. No markdown formatting, no conversational filler, and no surrounding quotes."
    )
    
    return _send_llm_request(prompt, api_key, api_base_url, model_name, provider)


def generate_daily_chronicle_prompt(
    github_username: str,
    session_date: str,
    sessions: List,
    projects: List
) -> str:
    """Generate the Daily Chronicle AI prompt detailing sessions, commands, and inferred gaps."""
    import os
    from datetime import datetime
    from termstory.models import format_duration
    from termstory.formatter import _is_noise_command
    from collections import defaultdict
    
    # Load template reference
    example_text = ""
    try:
        template_path = os.path.join(os.path.dirname(__file__), "templates", "example_daily_chronicle.txt")
        with open(template_path, "r", encoding="utf-8") as f:
            example_text = f.read().strip()
    except Exception:
        example_text = (
            "🌅 ACT I: THE OPENING ARCHITECTURE [09:15 - 12:02]\n"
            "You opened the terminal and immediately focused on core package wiring.\n"
            "├─ 📂 Project: TermStory (`main` branch)\n"
            "├─ ⌨️  Action:  Modified `parser.py` and `session.py` sequentially.\n"
            "└─ 🧠 Story:   Wired up the Zsh extended format regex tracking rules. You successfully structured the flat sequence pipeline, passing 8 consecutive local syntax tests. Off to a clean start.\n\n"
            "🍕 THE LUNCH BREAK INTERMISSION [12:02 - 13:45]\n"
            "[System Status: Idle for 1h 43m]\n"
            "The terminal went completely cold right after midday. The engine safely infers you stepped away to forage for food.\n\n"
            "====================================================================\n"
            "[CHRONICLE END] You clocked 5h 42m of active focus across 3 projects.\n"
            "===================================================================="
        )
    
    project_map = {p.id: p.name for p in projects if p.id is not None}
    chrono_lines = []
    
    for idx, s in enumerate(sessions):
        dt_start = datetime.fromtimestamp(s.start_time)
        dt_end = datetime.fromtimestamp(s.end_time)
        start_str = dt_start.strftime("%H:%M")
        end_str = dt_end.strftime("%H:%M")
        duration_str = format_duration(s.duration_seconds)
        proj_name = project_map.get(s.project_id, "Other")
        if proj_name == "General / No Project":
            proj_name = "Other"
            
        # Classify time of day for context
        start_hour = dt_start.hour
        if 0 <= start_hour < 5:
            time_context = f"Late-Night/Goblin Mode ({start_str})"
        elif 5 <= start_hour < 8:
            time_context = f"Early Bird Coding ({start_str})"
        elif 8 <= start_hour < 12:
            time_context = f"Morning Session ({start_str})"
        elif 12 <= start_hour < 14:
            time_context = f"Midday Session ({start_str})"
        elif 14 <= start_hour < 17:
            time_context = f"Afternoon Session ({start_str})"
        elif 17 <= start_hour < 21:
            time_context = f"Evening Session ({start_str})"
        else:
            time_context = f"Night Owl Session ({start_str})"
            
        # Analyze activities based on commands
        raw_cmds = [cmd.command for cmd in s.commands]
        activities = []
        
        # Test detection
        if any(any(x in cmd.lower() for x in ["test", "pytest", "unittest", "cargo test", "npm test", "go test"]) for cmd in raw_cmds):
            activities.append("Debugging/Running Tests")
        # Build detection
        if any(any(x in cmd.lower() for x in ["build", "compile", "cargo build", "go build", "npm run build", "make"]) for cmd in raw_cmds):
            activities.append("Compiling/Building Code")
        # Editor detection
        if any(any(x in cmd.lower() for x in ["vim", "nvim", "nano", "code", "emacs"]) for cmd in raw_cmds):
            activities.append("Deep Focused Editing / Coding")
        # Container/cloud detection
        if any(any(x in cmd.lower() for x in ["docker", "kubectl", "aws", "terraform", "gcloud"]) for cmd in raw_cmds):
            activities.append("Wrangling Containers/Infrastructure")
        # Git detection
        if any(any(x in cmd.lower() for x in ["git commit", "git push", "git add"]) for cmd in raw_cmds):
            activities.append("Committing and Pushing Changes")
            
        activity_str = ", ".join(activities) if activities else "General Development"
            
        chrono_lines.append(f"SESSION: [{start_str} - {end_str}] ({duration_str})")
        chrono_lines.append(f"TIME CONTEXT: {time_context}")
        chrono_lines.append(f"PROJECT: {proj_name}")
        chrono_lines.append(f"DETECTED ACTIVITY: {activity_str}")
        
        # Git commits
        if s.commits:
            chrono_lines.append("GIT COMMITS:")
            for c in s.commits:
                msg = c.get("cleaned_message") or c.get("message") or ""
                chrono_lines.append(f"  - {msg}")
                
        # Commands (filter noise, include exit codes for failed ones)
        cmds = [cmd for cmd in s.commands if not _is_noise_command(cmd.command)]
        if cmds:
            chrono_lines.append("COMMANDS:")
            for cmd in cmds[:15]:
                exit_str = f" (Exit Code {cmd.exit_code})" if cmd.exit_code != 0 else ""
                chrono_lines.append(f"  - {cmd.command}{exit_str}")
                
        chrono_lines.append("")
        
        # Check for gap between this session and the next one
        if idx < len(sessions) - 1:
            next_s = sessions[idx + 1]
            gap_seconds = next_s.start_time - s.end_time
            if gap_seconds >= 600: # 10 minutes or more
                gap_hours = gap_seconds // 3600
                gap_mins = (gap_seconds % 3600) // 60
                gap_str = []
                if gap_hours > 0:
                    gap_str.append(f"{gap_hours} hour{'s' if gap_hours > 1 else ''}")
                if gap_mins > 0:
                    gap_str.append(f"{gap_mins} minute{'s' if gap_mins > 1 else ''}")
                gap_display = " and ".join(gap_str) if gap_str else f"{gap_seconds} seconds"
                
                s_end_str = dt_end.strftime("%H:%M")
                next_start_str = datetime.fromtimestamp(next_s.start_time).strftime("%H:%M")
                
                # Classify break type based on time
                end_hour = dt_end.hour
                if 11 <= end_hour < 14:
                    break_context = "Lunch Time Break"
                elif 18 <= end_hour < 21:
                    break_context = "Dinner Time Break"
                elif 23 <= end_hour or end_hour < 5:
                    break_context = "Midnight Sleep/AFK"
                else:
                    break_context = "General Break / Away From Keyboard"
                    
                chrono_lines.append(f"[INFERRED BREAK]: Gap of {gap_display} (from {s_end_str} to {next_start_str})")
                chrono_lines.append(f"BREAK CONTEXT: {break_context}")
                chrono_lines.append("")
                
    chrono_blocks = "\n".join(chrono_lines)
    
    prompt = (
        "You are the master bard and core storyteller for termstory, a developer memory engine. "
        "Your task is to transform raw command telemetry, git commits, and inferred time gaps into a beautiful, personalized, and slightly humorous 'Story of You' for a single developer day.\n\n"
        
        "YOUR CORE RULES:\n"
        "1. DO NOT GENERATE HEADER: Start directly with the Acts (like ACT I). The header (with the DYNAMIC HANDLE, date, stats, and ASCII avatar) is generated by python and must NOT be output by you.\n"
        "2. USE SECOND-PERSON: Always address the developer as 'You' (e.g., 'You stepped into the arena at...', 'You woke up and immediately chose violence against bugs').\n"
        "3. ACT-BY-ACT CHRONOLOGY: Group the sessions into chronological Acts (e.g., '🌅 ACT I: THE OPENING ARCHITECTURE [09:15 - 12:02]', '🌋 ACT II: THE TRENCH WAR LOOP [13:45 - 16:10]'). For each act, show the exact time range [HH:MM - HH:MM] and explicitly comment on the timing (e.g., call out if they are coding at 3 AM in 'Late-Night/Goblin Mode', or early morning, or afternoon fatigue).\n"
        "4. ACT DETAIL STRUCTURE & INFER HUMANITY: Under each Act, output exactly three bullet points:\n"
        "   - ├─ 📂 Project: <Project Name> (<git branch name if checkout/branch command or commits tell you, or main branch by default>)\n"
        "   - ├─ ⌨️  Action:  <Concise description of key files modified or commands run, e.g. 'Modified parser.py and session.py sequentially.'>\n"
        "     (Note: If there is a repetitive pattern of failing commands, change this bullet to: ├─ 🔄 Pattern: High-Frustration Loop Detected. You executed a pattern of: `command` ──► `test` (Exit Code 1). This diagnostic loop repeated N times over X minutes.)\n"
        "   - └─ 🧠 Story:   <A witty 2-3 sentence narrative describing what was done, why/how, the technical struggle, and the outcome. Keep it dense and engineering-authentic.>\n"
        "5. INTEGRATE BREAKS & INFER HUMANITY: Between Acts, use the BREAK CONTEXT markers to write fun, perceptive descriptions of what they did in between sessions. For example, if it's a Lunch Time Break, infer that they went for lunch, grabbed coffee, or stared blankly at a wall. If they were stuck in a loop of failing tests/compiles, highlight their stubborn determination with dry developer humor.\n"
        "6. NO CORPORATE SLOP: Absolutely no generic, robotic wrap-ups or corporate management phrases like 'All in all, it was a productive day!'. Keep it authentic, slightly sarcastic, and developer-to-developer.\n"
        "7. THE VERDICT CARD: End the chronicle with a high-density, double-equals ASCII box summarizing the day's highlights (e.g. total active hours, test streaks broken, secrets protected) matching the exact format below:\n"
        "   ====================================================================\n"
        "   [CHRONICLE END] <1-2 sentences summarizing the day's engineering combat>\n"
        "   ====================================================================\n"
        "8. NO MARKDOWN OR EXTRA WRAPPER: Absolutely do not output code blocks (like ```text or ```), and do not add any introductory or trailing filler text. Just output the clean, terminal-formatted story.\n\n"
        
        "REFERENCE EXAMPLE TO EMULATE:\n"
        f"{example_text}\n\n"
        
        "Input Data Payload:\n"
        f"USER_HANDLE: {github_username}\n"
        f"DATE: {session_date}\n"
        "CHRONO_BLOCKS:\n"
        f"{chrono_blocks}\n\n"
        "Output format: Return ONLY the raw daily chronicle story."
    )
    return prompt



def generate_daily_chronicle(
    github_username: str,
    session_date: str,
    sessions: List,
    projects: List,
    api_key: str,
    api_base_url: str,
    model_name: str,
    provider: str
) -> Optional[str]:
    """Scrub inputs, build prompt, and call LLM chat completions endpoint to generate the Daily Chronicle."""
    if provider == "disabled" or not sessions:
        return None
        
    prompt = generate_daily_chronicle_prompt(github_username, session_date, sessions, projects)
    return _send_llm_request(prompt, api_key, api_base_url, model_name, provider)

