# Nexus Prime: Development Roadmap

Based on the architectural review, these are the high-priority next steps to evolve Nexus Prime from a highly capable prototype into a resilient, production-grade system.

---

## 1. 🧠 Stateful Memory (The "Knowledge Graph")

**The Problem:** Currently, the Permanent Vault stores memory as isolated text strings (e.g., "Roberto is a Lead Engineer"). If you ask "Who does Roberto report to?", the agent has to search for "Roberto" and hope the resulting strings contain the answer. 

**The Solution:** Stateful Memory involves moving from a "Document Store" to an "Entity Graph." The agent doesn't just remember sentences; it remembers relationships.

### Implementation Steps:
* [ ] **Update `MemoryFact` Schema:** Modify the extraction Pydantic schema in `memory.py` to extract `Entities` and `Relations`.
  * *Example:* Instead of extracting `"Roberto loves Python"`, the model extracts: `{"Subject": "Roberto", "Predicate": "loves", "Object": "Python"}`.
* [ ] **Create the Graph Database:** While ChromaDB is great for text, add a lightweight graph structure (like `NetworkX` or a simple JSON edge-list) to store these relationships.
* [ ] **The "Traversal" Tool:** Create a new tool called `traverse_memory(entity_name)`. When the user asks about "Roberto", the agent uses this tool to pull Roberto's entire "node" and all connected facts instantly, without relying on semantic similarity.

---

## 2. 🛡️ Sandboxed Tool Creation (Taming the Meta-Tool)

**The Problem:** The `create_tool_on_the_fly` tool allows the LLM to write directly to `tools.py`. A single hallucinated import or syntax error will break the entire system permanently.

**The Solution:** Implement a "Code Review" pipeline before executing file writes.

### Implementation Steps:
* [ ] **The Compiler Check:** Update the tool to write the generated code to a temporary file (e.g., `temp_tool.py`).
* [ ] **Sub-process Execution:** Use Python's `subprocess` or `ast` module to attempt to compile the temporary file (`python -m py_compile temp_tool.py`).
* [ ] **The Validator Micro-Agent:** If the compile fails, send the traceback to a secondary `gemini-2.5-flash` agent with the instruction: *"This code failed to compile. Fix the syntax error and return the corrected code."*
* [ ] **The Final Commit:** Only after the code passes the syntax check is it appended to the main `tools.py` file.

---

## 3. 🚦 Robust Error Handling & Retry Logic

**The Problem:** The agent currently crashes or returns unhelpful blank strings when an API endpoint times out or returns a `500 INTERNAL` error.

**The Solution:** Implement an exponential backoff strategy for all network calls.

### Implementation Steps:
* [ ] **Integrate Tenacity:** Install the `tenacity` library (`pip install tenacity`).
* [ ] **Decorate API Calls:** Wrap the `generate_content` calls in `ai_engine.py` with `@retry(wait=wait_exponential(multiplier=1, min=4, max=10))`.
* [ ] **Graceful Degradation:** If the API fails after 3 retries, have the agent fallback to the Local Provider (Ollama) automatically, ensuring the user is never left with a dead terminal.

---

## 4. 🧹 Schema Mapper Refactoring

**The Problem:** The `get_gemini_tools` function uses fragile string manipulation to convert your Pydantic tool schemas into the format Google expects.

**The Solution:** Use established schema converters.

### Implementation Steps:
* [ ] **SDK Native Mapping:** Research the newest `google-genai` SDK documentation. Google often introduces native methods for ingesting standard JSON schemas or Pydantic models directly into `GenerateContentConfig`.
* [ ] **Refactor `tools.py`:** Replace the manual dictionary building in `get_gemini_tools` with a robust, recursive schema parser that can handle nested objects and complex types.