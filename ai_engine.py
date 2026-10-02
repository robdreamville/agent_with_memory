import ollama
import inspect
from google import genai
from google.genai import types
from typing import List, Dict, Any, Optional, Literal
from memory import MemoryManager, ChatMessage, JudgeEvaluation
from registry import registry, AgentManifest
import config

if config.GEMINI_API_KEY:
    # Legacy global config removed as google-genai uses client-based auth
    pass

class AIEngine:
    """
    The brain of the agent. Orchestrates memory retrieval and LLM inference.
    """

    def __init__(self, agent_id: str = config.DEFAULT_AGENT_ID, provider: str = config.AI_PROVIDER):
        # Fetch manifest from registry
        self.manifest = registry.get_agent(agent_id)
        if not self.manifest:
            # Fallback to a default manifest if not found
            self.manifest = AgentManifest(
                agent_id=agent_id,
                persona_name=agent_id.replace("_", " ").title(),
                system_prompt=config.DEFAULT_SYSTEM_PROMPT
            )
        
        self.agent_id = self.manifest.agent_id
        self.system_prompt = self.manifest.system_prompt
        self.provider = provider
        
        self.memory = MemoryManager(
            agent_id=self.agent_id, 
            db_path=config.CHROMA_DB_PATH, 
            model=config.OLLAMA_MODEL, 
            provider=provider,
            is_head_agent=self.manifest.is_head_agent
        )
        
        if self.provider == "gemini":
            self.client = genai.Client(api_key=config.GEMINI_API_KEY)

    async def _evaluate_retrieval(self, query: str, context: str) -> str:
        """[THE JUDGE] Categorizes if the reflex info is enough."""
        prompt = f"""[GOAL] Evaluate if the Fact answers the Query.\n\nRULES:\n1. If Fact directly and completely answers the Query -> COMPLETE\n2. If Query asks for multiple things but Fact only provides some -> PARTIAL\n3. If Fact is unrelated or missing the answer completely -> NONE\n\nActual Evaluation:\nQuery: {query}\nFact: {context}"""
        try:
            if self.provider == "gemini":
                response = self.client.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=JudgeEvaluation
                    )
                )
                return JudgeEvaluation.model_validate_json(response.text).evaluation

            response = ollama.chat(
                model=config.OLLAMA_DECOMPOSER_MODEL,
                messages=[{"role": "user", "content": prompt.strip()}],
                format=JudgeEvaluation.model_json_schema(),
                options={**config.OLLAMA_FAST_OPTIONS, "temperature": 0.0}
            )
            return JudgeEvaluation.model_validate_json(response['message']['content']).evaluation
        except Exception as e: 
            print(f"Evaluation Error: {e}")
            return "PARTIAL"

    async def _decompose_query(self, query: str) -> List[str]:
        """[THE LIBRARIAN] Extracts clean search terms."""
        if len(query.split()) < 4: return [query]
        prompt = f"Instructions: Extract core search subjects as a comma-separated list.\n\nText: {query}\nKeywords:"
        try:
            if self.provider == "gemini":
                gemini_prompt = prompt + "\n\nIMPORTANT: Return ONLY the comma-separated list. No other text."
                response = self.client.models.generate_content(
                    model=config.GEMINI_FAST_MODEL,
                    contents=gemini_prompt
                )
                terms = response.text.strip().split(",")
                return [t.strip().strip("'\"-") for t in terms if len(t.strip()) > 1]

            response = ollama.chat(
                model=config.OLLAMA_DECOMPOSER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={**config.OLLAMA_FAST_OPTIONS, "stop": ["\n"]}
            )
            terms = response['message']['content'].strip().split(",")
            return [t.strip().strip("'\"-") for t in terms if len(t.strip()) > 1]
        except Exception: return [query]

    async def chat(self, user_input: str, tools: Optional[List[Dict[str, Any]]] = None, message_history: Optional[List[ChatMessage]] = None):
        """
        Modified chat method: 
        If 'message_history' is provided, we continue that conversation instead of starting a new one.
        This prevents context loss during tool-calling loops.
        """
        import asyncio

        # If we are in the middle of a tool-calling chain, we don't re-retrieve memory
        if message_history:
            messages = message_history
        else:
            # NEW TURN: Run SPR retrieval logic
            async def get_vault_context():
                sub_queries = await self._decompose_query(user_input)
                all_results = []
                search_tasks = [self.memory.search_permanent(q, n_results=2) for q in sub_queries]
                search_results = await asyncio.gather(*search_tasks)
                for res_list in search_results: all_results.extend(res_list)
                return "\n".join([f"- {m['content']}" for m in {m['content']: m for m in all_results}.values()])

            async def get_reflex_and_status():
                reflexes = await self.memory.get_all_reflexes(user_input)
                reflex_text = "\n".join([f"- {r}" for r in reflexes])
                status = await self._evaluate_retrieval(user_input, reflex_text) if reflexes else "NONE"
                return reflex_text, status

            reflex_task = asyncio.create_task(get_reflex_and_status())
            vault_task = asyncio.create_task(get_vault_context())
            reflex_text, status = await reflex_task
            
            mem_context = ""
            if status == "COMPLETE":
                vault_task.cancel()
                mem_context = f"Relevant facts:\n{reflex_text}"
            else:
                try:
                    vault_text = await vault_task
                    mem_context = f"Contextual facts:\n{reflex_text}\n\nSpecific details:\n{vault_text}" if status == "PARTIAL" else vault_text
                except Exception: mem_context = f"Relevant facts:\n{reflex_text}"

            # Build the fresh message chain
            history = self.memory.get_working_context()
            messages = [ChatMessage(role="system", content=self.system_prompt)]
            if mem_context:
                messages.append(ChatMessage(role="assistant", content=f"Relevant background information:\n{mem_context}"))
            for interaction in history:
                messages.append(ChatMessage(role="user", content=interaction['user']))
                messages.append(ChatMessage(role="assistant", content=interaction['assistant']))
            messages.append(ChatMessage(role="user", content=user_input))

        try:
            if self.provider == "gemini":
                # Convert messages to Gemini format
                contents = []
                
                # Handle system message separately
                system_instruction = None
                start_idx = 0
                if messages and messages[0].role == 'system':
                    system_instruction = messages[0].content
                    start_idx = 1

                # Check for active cache name in tool observations from history
                active_cache_name = None
                for msg in messages:
                    if msg.role == 'tool' and "FILE_CACHED" in msg.content:
                        # Extract 'cached_contents/...' from tool observation
                        import re
                        match = re.search(r"cachedContents/[a-zA-Z0-9_-]+", msg.content)
                        if match:
                            active_cache_name = match.group(0)

                for msg in messages[start_idx:]:
                    role = "user" if msg.role == "user" or msg.role == "tool" else "model"
                    parts = []
                    
                    if msg.role == 'tool':
                        # Tool results must be wrapped in FunctionResponse
                        parts.append(types.Part.from_function_response(
                            name=msg.name or "unknown",
                            response={"result": msg.content}
                        ))
                    else:
                        if msg.content:
                            parts.append(types.Part.from_text(text=msg.content))
                        
                        if msg.tool_calls:
                            role = "model" # Ensure role is model if it contains tool calls
                            for tc in msg.tool_calls:
                                parts.append(types.Part.from_function_call(
                                    name=tc['function']['name'],
                                    args=tc['function']['arguments']
                                ))
                    
                    if parts:
                        contents.append(types.Content(role=role, parts=parts))

                # Initialize tools
                gemini_tools = []
                if tools:
                    # Flatten function declarations from the registry's nested format
                    all_decls = []
                    for t in tools:
                        if "function_declarations" in t:
                            all_decls.extend(t["function_declarations"])
                    if all_decls:
                        gemini_tools = [types.Tool(function_declarations=all_decls)]
                
                # Call generate_content with the full history and optional cache
                response = self.client.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=gemini_tools if gemini_tools else None,
                        cached_content=active_cache_name
                    )
                )
                
                # Map Gemini response back to our internal format
                response_message = ChatMessage(role="assistant", content="")
                tool_calls = []
                
                if response.candidates and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if part.function_call:
                            tool_calls.append({
                                "function": {
                                    "name": part.function_call.name,
                                    "arguments": part.function_call.args
                                }
                            })
                        elif part.text:
                            response_message.content += part.text
                
                if tool_calls:
                    response_message.tool_calls = tool_calls
                
                messages.append(response_message)
                return response_message, messages

            else:
                # Convert ChatMessage objects back to dicts for Ollama
                ollama_messages = [m.model_dump(exclude_none=True) for m in messages]
                
                response = ollama.chat(
                    model=config.OLLAMA_MODEL,
                    messages=ollama_messages,
                    tools=tools,
                    options=config.OLLAMA_OPTIONS,
                )
                
                # Append the assistant's response (which might be a tool call) to the local history
                msg_dict = response['message'].model_dump() if hasattr(response['message'], 'model_dump') else dict(response['message'])
                assistant_msg = ChatMessage(**msg_dict)
                messages.append(assistant_msg)
                return assistant_msg, messages

        except Exception as e:
            import traceback
            traceback.print_exc()
            err_msg = ChatMessage(role="assistant", content=f"Error: {e}")
            return err_msg, messages + [err_msg]

    async def archive_now(self):
        await self.memory.review_and_archive()
