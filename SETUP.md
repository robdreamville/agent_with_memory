# Nexus Prime — Setup

Get a fresh clone running in four steps.

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

On Linux, the Tkinter viewers (`vault_viewer.py`, `agent_viewer.py`) also need a system Tk install:

```bash
sudo apt install python3-tk
```

## 2. Create your agent registry

`agents.json` (your private agent manifest) is gitignored and not shipped with the repo.
Start from the sanitized example:

```bash
cp agents.example.json agents.json
```

This gives you two sample agents:

- `nexus_prime` — the head agent (`DEFAULT_AGENT_ID` in `config.py`), with all built-in tools enabled.
- `research_scout` — a focused web-research specialist you can summon via the `delegate_to_agent` tool.

Edit `agents.json` freely afterwards, or use the in-chat `spawn_new_agent` tool to add more.
It is never committed, so your manifests stay private.

## 3. Configure environment variables

```bash
cp .env.example .env
```

Then edit `.env`:

- `GEMINI_API_KEY` — required if you use the `gemini` provider (or want Gemini-backed tools like `google_web_search` in hybrid mode).
- `AI_PROVIDER` — `ollama` (default) or `gemini`.

For local mode, pull the models Ollama needs first:

```bash
ollama pull gemma4:e2b
ollama pull qwen2.5:1.5b
```

## 4. Run

```bash
python agent.py
```

You'll be asked to pick a provider (default: whatever `AI_PROVIDER` is set to).
In-chat commands: `archive` forces memory archival, `exit` / `quit` archives then quits.

Other entry points: `python vault_viewer.py` (audit/delete ChromaDB memories),
`python agent_viewer.py` (list/delete agent manifests).
