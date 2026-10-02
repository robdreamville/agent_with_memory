# Nexus Prime — Improvements Log

Design improvements identified during the Oct 1, 2026 review session. Each item is a concrete change with the reasoning behind it.

## 1. Dedup at write time (not cleanup time)

**Problem:** The vault sometimes stores the same fact twice (spotted in memory dumps across Tier 1 Reflex and Tier 3 vault).

**Fix:** Before the Gatekeeper writes a new memory, check whether an equivalent fact already exists (semantic similarity check against the vault + keyword check against the Reflex map). If a match is found, update/refresh the existing record instead of inserting a duplicate.

**Why:** Duplicates are retrieval noise — they dilute search results and waste space. Catching them at write time is cheaper and more reliable than periodic cleanup.

## 2. Gatekeeper should skip time-sensitive facts

**Problem:** The agent stores current events and news as shared memories. These go stale, never change future behavior, and pollute retrieval.

**Fix:** Update the Gatekeeper extraction prompt with a rule: facts about current events, news, or anything with a short shelf life should be skipped, or tagged `ephemeral` with an expiry timestamp so a later pass can purge them.

**Why:** The vault's job is durable knowledge. The retention rule: keep what changes future behavior (preferences, biographical facts, rules), drop what is ephemeral.

## 3. Add tracing (future)

**Problem:** There is no real trace logging for the agent loop — no structured record of turns, tool calls, observations, and token usage per run.

**Fix:** Log each turn to a structured trace file (JSONL): timestamp, message history length, tool calls made, observations, token counts. This is the foundation for evals and for diagnosing production failures.

**Why:** You cannot fix what you cannot see. Tracing is the prerequisite for everything in the evals block.

## Already fixed (Oct 1, 2026)

- `create_tool_on_the_fly` now compile-checks generated code in a temp file before appending to `tools.py`.
- Removed the backwards visibility heuristic that upgraded user/private memories to shared.
- `get_system_context` reports the real local timezone instead of hardcoded UTC.
- `agents.json` added to `.gitignore` (runtime state, not source).
- Dead `main.py` prototype moved to `archive/`.
