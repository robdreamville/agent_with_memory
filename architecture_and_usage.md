# Nexus Prime: Architecture & Usage Guide

This document provides a simple, high-level overview of how the Nexus Prime multi-agent system operates, the specific logic branches it takes during a conversation, and how you can interact with its advanced features.

---

## 🏗️ Core Architecture Overview

The system is built on a **Provider-Agnostic Engine** that seamlessly switches between Cloud (Google Gemini) and Local (Ollama) inference, backed by a **3-Tier Memory System**.

### 1. Dual-Provider Model Routing (`config.py` & `ai_engine.py`)
At startup, you choose your AI provider. The agent orchestrates its tasks differently based on this choice to optimize for speed, cost, and privacy.

#### The Cloud Provider (Google Gemini - Tier 1)
Optimized for massive context, near-instant speed, and web connectivity.
*   **Main Reasoning (The Orchestrator):** Handled by `gemini-2.5-flash`. Manages the conversation and complex tool execution.
*   **Utility Operations (The Micro-Agents):** Handled by `gemini-2.5-flash` in the background for query decomposition and memory evaluation.
*   **Search Grounding:** Handled by `gemini-2.0-flash`. Dedicated solely to executing highly accurate, real-time Google web searches with citations.

#### The Local Provider (Ollama - Private & Hybrid)
Optimized for privacy and local control. While reasoning is local, the agent can operate in a **Hybrid Mode** to access advanced cloud tools.
*   **Main Reasoning:** Handled by `gemma4:e2b`. A heavy local model designed for logic and tool orchestration.
*   **Utility Operations:** Handled by `qwen2.5:1.5b`. A lightning-fast, small local model optimized strictly for breaking down queries and formatting JSON memory evaluations.
*   **Hybrid Tool Capability:** Even when running locally, the agent can call cloud-based tools (`google_web_search`, `submit_batch_job`) as long as an internet connection and `GEMINI_API_KEY` are present. 
*   **Exception:** **Context Caching** is unavailable for local models. Large documents must be read directly into the local context window, as Google's server-side cache is only accessible by Gemini models.

### 2. The 3-Tier Memory System (`memory.py`)
Memory is designed to mimic human recall, moving from immediate context to permanent storage.

*   **Tier 1: Reflex (Instant Recall):** A lightweight JSON map (`reflex_storage/`) that links specific keywords (e.g., "Eagle One") to highly important facts. If the user mentions a keyword, the fact is injected instantly.
*   **Tier 2: Working Memory (Short-Term):** The active conversation buffer (last 15 messages). It provides conversational continuity.
*   **Tier 3: Permanent Vault (Long-Term):** A semantic vector database (ChromaDB). When the Working Memory fills up, the agent distills the conversation into core facts (with rationales) and permanently stores them here.

---

## 🔀 The Execution Process (Step-by-Step)

When you type a message and press Enter, the system executes the following branching logic:

### Phase 1: Context Gathering (Asynchronous)
1.  **Query Decomposition:** The Librarian micro-agent breaks your input into clean search terms.
2.  **Vault Search:** The system queries ChromaDB (Tier 3) using those search terms.
3.  **Reflex Check:** The system simultaneously checks the Tier 1 Reflex map for any exact keyword matches.
4.  **The Judge Evaluation:** A micro-agent evaluates the retrieved memories:
    *   *Branch A (COMPLETE):* If the Reflex memories perfectly answer the prompt, the agent ignores the Vault to save tokens.
    *   *Branch B (PARTIAL/NONE):* If Reflex isn't enough, the agent merges the Vault search results into the prompt.

### Phase 2: The "Thinking" Cycle (Tool Loop)
1.  **Model Generation:** The main model analyzes your prompt + the injected memories.
2.  **Tool Evaluation:** 
    *   *Branch A (Use Tools):* The model outputs one or more tool calls (e.g., `google_web_search`, `calculate_sqrt`).
    *   *Branch B (Direct Answer):* The model has enough info and formulates a final response.
3.  **Concurrent Execution:** If tools are called, the system executes all of them **simultaneously** using `asyncio.gather`.
4.  **Feedback Loop:** The results of the tools are fed back into the model's history, and the cycle repeats until the model chooses Branch B (Direct Answer).

### Phase 3: Final Output & Cleanup
1.  **Response:** Nexus Prime delivers the final synthesized answer.
2.  **Memory Management:** The prompt and response are added to Working Memory. If the buffer exceeds 15 messages, the oldest 5 are sent to the Gatekeeper micro-agent to be distilled and stored in the Permanent Vault.

---

## 🛠️ Usage & Advanced Capabilities

### Basic Interaction
Start the agent by running:
```bash
python agent.py
```
Type your query and press Enter. 

### Triggering Tier 1 Cloud Features

The system has been upgraded to support Google GenAI Tier 1 capabilities. You can invoke them using natural language:

*   **Grounded Web Search:** 
    *   *Usage:* "What is the latest news regarding SpaceX?"
    *   *Action:* The agent uses the `google_web_search` tool, reaching out to the live internet and returning a fact-checked summary.
*   **Large Document Caching (Context Pinning):**
    *   *Usage:* "Ingest this large codebase: `C:/path/to/massive_file.txt`"
    *   *Action:* If the file is >32,768 tokens, the agent uses `ingest_large_document` to lock it into Google's Tier 1 Cache for 1 hour. Subsequent questions about the file will be answered almost instantly with massive cost savings.
*   **Batch Processing (High-Volume):**
    *   *Usage:* "Submit this JSONL file for batch processing: `prompts.jsonl`"
    *   *Action:* The agent uses `submit_batch_job` to send thousands of tasks to Google's asynchronous queue at a 50% discount. You can later ask, "Check the status of my batch job [ID]."

### System Commands
While chatting, you can use these exact text commands:
*   `archive`: Forces the agent to instantly evaluate Working Memory and commit important facts to the Permanent Vault.
*   `exit` or `quit`: Safely shuts down the agent, triggering a final memory archival before closing.

### Vault Management
To view, audit, or delete what the agent remembers:
```bash
python vault_viewer.py
```
This opens a GUI showing all facts stored in ChromaDB, including their tags, importance score, and the AI's rationale for saving them.