## 11. AI Client

`ai.py` interfaces with any OpenAI-compatible LLM endpoint using **only Python's standard library** — no `requests`, no `openai-python`.

- **Transport:** `urllib.request.Request` with JSON payload
- **URL normalization:** Strips trailing slashes, auto-appends `/chat/completions`
- **Keyless mode:** Skips `Authorization: Bearer` header if API key is empty (Ollama compatibility)
- **Timeout:** 15 seconds to prevent blocking the TUI thread
- **Background execution:** All AI calls run in Textual `@work` async workers — UI never freezes

### Supported Providers

| Provider | Default model | Notes |
|---|---|---|
| **Groq** | `llama-3.1-8b-instant` | Fast, free tier available |
| **OpenAI** | `gpt-4o-mini` | Requires API key |
| **Ollama** | `llama3` | Fully local, no key needed |
| **Custom** | any | Any OpenAI-compatible endpoint |

