# Nexus Prime — Agent with Memory

A CLI multi-agent system with a **3-tier memory architecture**. The agent remembers facts across sessions, distills old conversations into a permanent vault, and retrieves memories through a parallel search-and-judge pipeline — running on either Google Gemini (cloud) or Ollama (local).

## Architecture

### 3-Tier Memory (`memory.py`)

| Tier | Name | What it is | Storage |
|------|------|-----------|---------|
| 1 | Reflex | Instant keyword → fact map for high-importance facts (importance ≥ 0.8) | `reflex_storage/reflex_{agent_id}.json` |
| 2 | Working Memory | Last 15 interactions; oldest 5 are distilled by a Gatekeeper LLM when full | In-memory deque |
| 3 | Permanent Vault | Semantic vector store with owner/visibility metadata filtering | ChromaDB (`chroma_db/`) |

### SPR Retrieval (per turn, `ai_engine.py`)

1. **Librarian** micro-agent decomposes the query into search terms.
2. **Vault search** (Tier 3) and **Reflex check** (Tier 1) run in parallel.
3. **Judge** micro-agent grades the Reflex result `COMPLETE` / `PARTIAL` / `NONE` — on `COMPLETE` the vault search is cancelled to save tokens.

### Agent Loop (`agent.py`)

Each turn: reload tools → build provider-specific tool schemas filtered by the agent's manifest → chat → execute tool calls concurrently (`asyncio.gather` over a thread pool) → feed observations back until a final answer → save the interaction to working memory. Commands: `archive` forces memory archival, `exit` archives then quits.

### Providers

- **Gemini** (cloud): reasoning on `gemini-2.5-flash`, grounded web search on `gemini-2.0-flash`, plus Tier-1 context caching and batch API tools.
- **Ollama** (local): reasoning on `gemma4:e2b`, micro-agents on `qwen2.5:1.5b`. Cloud tools still work in hybrid mode if `GEMINI_API_KEY` is set.

## Tools

Tool definitions live in `tools.py`, registered via a `@register_tool` decorator that auto-generates Pydantic argument models and provider-specific schemas (with validation before execution).

| Tool | What it does |
|------|--------------|
| `get_system_context` | Date, time, active provider |
| `google_web_search` | Grounded live Google search with citations |
| `calculate_sqrt` | Sample math tool |
| `create_tool_on_the_fly` | Meta-tool: writes new Python tools into `tools.py` (see warnings below) |
| `delegate_to_agent` | Spins up a sub-agent for a task |
| `spawn_new_agent` | Creates a new agent manifest in the registry |
| `ingest_large_document` | Caches files >32k tokens in Gemini context cache (1h TTL) |
| `submit_batch_job` / `check_batch_status` | GenAI batch API at 50% cost |
| `reverse_text`, `format_duration`, `list_files_with_extension` | AI-authored utility tools |

## Quickstart

**Prerequisites:** Python 3.10+, and for local mode [Ollama](https://ollama.com) with `gemma4:e2b` and `qwen2.5:1.5b` pulled. The Tkinter viewers need a system Tk install on Linux (`sudo apt install python3-tk`).

```bash
pip install -r requirements.txt
cp .env.example .env   # then add your GEMINI_API_KEY
python agent.py
```

**`.env.example`:**
```
GEMINI_API_KEY=
AI_PROVIDER=ollama
```

Useful overrides (see `config.py` for all): `GEMINI_MODEL`, `GEMINI_FAST_MODEL`, `OLLAMA_MODEL`, `OLLAMA_DECOMPOSER_MODEL`, `CHROMA_DB_PATH`, `DEFAULT_AGENT_ID`.

## Usage

```bash
python agent.py            # start the agent (choose ollama/gemini at prompt)
python vault_viewer.py     # GUI: audit/delete ChromaDB memories
python agent_viewer.py      # GUI: list/delete agent manifests
```

In-chat commands: `archive` (force memory archival), `exit` / `quit` (archive + quit).

## Project Structure

```
agent.py              # CLI entry point, agent loop
ai_engine.py          # AIEngine: LLM orchestration + SPR memory retrieval
memory.py             # MemoryManager: 3-tier memory system
tools.py              # Tool registry + all tool definitions
config.py             # pydantic-settings (secrets from .env)
registry.py           # AgentRegistry + AgentManifest
agents.json           # runtime agent registry (gitignored)
architecture_and_usage.md  # detailed architecture doc
TODO.md               # roadmap
```

## Known Limitations

- `create_tool_on_the_fly` appends LLM-generated code to `tools.py` with no sandbox and no syntax check — treat it as experimental (see `TODO.md` §2 for the planned hardening).
- The head agent (`nexus_prime`) can read all agents' vault memories by design.

## Roadmap

See `TODO.md`: knowledge-graph memory, sandboxed tool creation, retry logic with exponential backoff, schema mapper refactoring.
