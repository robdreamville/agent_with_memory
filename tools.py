import inspect
import json
import importlib
from typing import Any, Dict, List, Optional, Callable, Literal, Type, get_type_hints
from pydantic import BaseModel, Field, create_model
from registry import registry, AgentManifest

# --- TOOL REGISTRY INFRASTRUCTURE ---

class ToolModel(BaseModel):
    """
    Metadata about a tool for AI providers.
    """
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema of the arguments

# This dictionary will store our live tool objects
# Key: tool_name, Value: { "model_class": Type[BaseModel], "func": Callable, "description": str }
_TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {}

def register_tool(description: str):
    """
    A decorator to register functions as tools using Pydantic for validation and schema generation.
    """
    def decorator(func: Callable):
        # Get type hints and signature
        type_hints = get_type_hints(func)
        sig = inspect.signature(func)
        
        fields = {}
        for name, param in sig.parameters.items():
            annotation = type_hints.get(name, Any)
            default = param.default
            
            # Pydantic create_model expects (type, default)
            if default is inspect.Parameter.empty:
                fields[name] = (annotation, Field(..., description=f"The {name} parameter"))
            else:
                fields[name] = (annotation, Field(default, description=f"The {name} parameter"))

        # Dynamically create a Pydantic model for the function arguments
        model_name = f"{func.__name__.title().replace('_', '')}Args"
        args_model = create_model(model_name, **fields)

        # Store in registry
        _TOOL_REGISTRY[func.__name__] = {
            "model_class": args_model,
            "func": func,
            "description": description
        }
        return func
    return decorator

def get_ollama_tools(allowed_tools: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Returns the list of tools in the format Ollama expects.
    """
    tools_list = []
    for name, info in _TOOL_REGISTRY.items():
        if allowed_tools is not None and name not in allowed_tools:
            continue
            
        # Get JSON schema from Pydantic model
        schema = info["model_class"].model_json_schema()
        
        # Clean up schema for Ollama (it prefers a simpler object structure)
        # Pydantic often adds 'title' and '$defs', which we might want to prune
        def prune_schema(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: prune_schema(v) for k, v in obj.items() if k not in ["title", "$defs"]}
            elif isinstance(obj, list):
                return [prune_schema(i) for i in obj]
            return obj

        clean_schema = prune_schema(schema)

        tools_list.append({
            "type": "function",
            "function": {
                "name": name,
                "description": info["description"],
                "parameters": clean_schema
            }
        })
    return tools_list

def get_gemini_tools(allowed_tools: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Returns the list of tools in the format Gemini expects.
    Gemini uses a similar structure to OpenAI/Ollama but requires 'required' to be at the top level of parameters.
    """
    tools_list = []
    for name, info in _TOOL_REGISTRY.items():
        if allowed_tools is not None and name not in allowed_tools:
            continue
            
        schema = info["model_class"].model_json_schema()
        
        # Gemini specific adjustments
        gemini_params = {
            "type": "OBJECT",
            "properties": {},
            "required": schema.get("required", [])
        }
        
        for prop_name, prop_info in schema.get("properties", {}).items():
            # Gemini expects uppercase types
            p_type = prop_info.get("type", "string").upper()
            if p_type == "INTEGER": p_type = "NUMBER" # Gemini sometimes picky
            
            gemini_prop = {
                "type": p_type,
                "description": prop_info.get("description", "")
            }
            
            if p_type == "ARRAY":
                items_info = prop_info.get("items", {})
                item_type = items_info.get("type", "string").upper()
                if item_type == "INTEGER": item_type = "NUMBER"
                gemini_prop["items"] = {"type": item_type}
            
            if "enum" in prop_info:
                gemini_prop["enum"] = prop_info["enum"]
                
            gemini_params["properties"][prop_name] = gemini_prop

        tools_list.append({
            "function_declarations": [
                {
                    "name": name,
                    "description": info["description"],
                    "parameters": gemini_params
                }
            ]
        })
    return tools_list

def validate_and_call_tool(name: str, args: Dict[str, Any]) -> str:
    """
    Validates arguments using the Pydantic model before executing the tool.
    Returns the result of the tool or a clear error message.
    """
    if name not in _TOOL_REGISTRY:
        return f"Error: Tool '{name}' not found."
    
    info = _TOOL_REGISTRY[name]
    try:
        # Pydantic validation
        validated_args = info["model_class"](**args)
        # Execute with validated arguments
        result = info["func"](**validated_args.model_dump())
        return str(result)
    except Exception as e:
        return f"Validation/Execution Error in tool '{name}': {str(e)}"

# --- THE BOOTSTRAP TOOL: CREATE NEW TOOL ---

@register_tool(
    description="Creates a new Python tool and saves it to tools.py. Use this when you need a capability you don't currently have."
)
def create_tool_on_the_fly(tool_name: str, description: str, python_code: str) -> str:
    """
    This is the 'Meta-Tool'. It allows the agent to write its own code.
    Sanitizes the description to ensure valid Python syntax by using triple double-quotes.
    Moves import statements inside the function body to prevent SyntaxErrors.
    """
    # Sanitize: Remove any existing triple quotes to prevent premature closing
    safe_description = description.replace('"""', '\"\"\"')
    
    # Improved sanitization:
    # 1. Split code into lines
    # 2. Extract imports
    # 3. Reconstruct function body with imports moved inside
    
    lines = [line.rstrip() for line in python_code.split('\n')]
    
    imports = []
    function_lines = []
    
    # Flag to detect if we are inside the function definition
    in_function = False
    
    for line in lines:
        stripped = line.strip()
        if not stripped: continue
        
        # Detect imports
        if stripped.startswith(('import ', 'from ')):
            imports.append(stripped)
        else:
            function_lines.append(line)
            
    # Reconstruct: 
    # The first line should be the function definition
    # We want the imports to be the first thing inside the function
    
    if not function_lines:
        return "Error: Could not parse function definition."
        
    # Ensure function_lines[0] is the 'def ...:' line
    if not function_lines[0].startswith('def '):
        return "Error: Provided code does not start with a function definition."
        
    # Reassemble:
    # Line 0: def ...:
    # Line 1+: 4 spaces + imports + code_body
    
    final_code_lines = [function_lines[0]]
    for imp in imports:
        final_code_lines.append(f"    {imp}")
    
    # Add the rest of the function body, indented
    for line in function_lines[1:]:
        # If line is already indented, keep it, else indent
        if line.startswith('    '):
            final_code_lines.append(line)
        else:
            final_code_lines.append(f"    {line}")
            
    sanitized_python_code = '\n'.join(final_code_lines)

    formatted_code = f'\n\n@register_tool(description="""{safe_description}""")\n{sanitized_python_code}\n'
    try:
        with open(__file__, "a") as f:
            f.write(formatted_code)
        return f"Success: Tool '{tool_name}' has been written to tools.py and registered."
    except Exception as e:
        return f"Error creating tool: {str(e)}"

@register_tool(description="Retrieves current system context, including date, time, and active agent information.")
def get_system_context() -> str:
    from datetime import datetime
    import config
    from pydantic import BaseModel
    
    class SystemContext(BaseModel):
        current_datetime: str
        timezone: str
        active_provider: str
        
    context = SystemContext(
        current_datetime=datetime.now().isoformat(),
        timezone="UTC",
        active_provider=config.AI_PROVIDER,
    )
    return context.model_dump_json()

# --- PRE-DEFINED TOOLS ---

@register_tool(description="Calculates the square root of a number.")
def calculate_sqrt(n: float) -> float:
    import math
    return math.sqrt(n)

@register_tool(description="Performs a high-accuracy Google Search for live information, news, or deep research. Returns a synthesized answer with citations.")
def google_web_search(query: str) -> str:
    """
    Leverages native Google Search grounding via gemini-2.0-flash.
    Returns highly accurate, real-time information with source links.
    """
    from google import genai
    from google.genai import types
    import config

    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        
        # We use gemini-2.0-flash specifically for its low cost and high-quality grounding.
        # Native grounding is configured via the google_search tool.
        response = client.models.generate_content(
            model=config.GEMINI_SEARCH_MODEL,
            contents=f"Search for and summarize current information about: {query}",
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}]
            )
        )
        
        if not response.text:
            return "Google Search returned no text content. The query might be too narrow or restricted."
            
        return response.text

    except Exception as e:
        return f"GOOGLE_SEARCH_ERROR: {str(e)}"

#--- AI MADE TOOLS ---
@register_tool(description='Reverses the input string.')
def reverse_text(text: str) -> str:
    return text[::-1]

# --- ORCHESTRATION TOOLS ---

@register_tool(description="Delegates a specific task to a specialized sub-agent. Use this for complex specialized tasks.")
def delegate_to_agent(agent_id: str, task_description: str) -> str:
    """
    Spins up a specialized agent to handle a sub-task.
    """
    from ai_engine import AIEngine
    import asyncio
    
    # We create a new engine for the sub-agent
    sub_agent = AIEngine(agent_id=agent_id)
    
    # Run the sub-task (simulating a clean session for the sub-agent)
    # We use asyncio.run because this tool is called from an async loop but is not defined as async
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we are already in an event loop (which we are), we need to use a task or another method
            # For simplicity in this tool, we'll use a helper to wait for the coroutine
            coro = sub_agent.chat(task_description)
            import nest_asyncio
            nest_asyncio.apply()
            response_message, _ = loop.run_until_complete(coro)
            return response_message.content
        else:
            response_message, _ = asyncio.run(sub_agent.chat(task_description))
            return response_message.content
    except Exception as e:
        return f"Error during delegation to '{agent_id}': {str(e)}"

@register_tool(description="Creates a new specialized agent and adds them to the registry.")
def spawn_new_agent(agent_id: str, persona_name: str, specialization: List[str], mission_statement: str, active_tools: List[str]) -> str:
    """
    Adds a new agent definition to the system.
    """
    new_manifest = AgentManifest(
        agent_id=agent_id,
        persona_name=persona_name,
        system_prompt=f"You are {persona_name}, a specialized AI agent. Your mission: {mission_statement}",
        specialization=specialization,
        active_tools=active_tools
    )
    
    try:
        registry.save_agent(new_manifest)
        return f"Success: Agent '{persona_name}' ({agent_id}) has been spawned and added to the registry."
    except Exception as e:
        return f"Error spawning agent: {str(e)}"


@register_tool(description="""Use this tool to convert a total number of seconds into a human-readable duration format (days, hours, minutes, seconds).""")
def format_duration(seconds: int) -> str:
    if seconds < 0:
        return "Invalid input: seconds must be non-negative"

    days = seconds // 86400
    remaining_seconds = seconds % 86400

    hours = remaining_seconds // 3600
    remaining_seconds = remaining_seconds % 3600

    minutes = remaining_seconds // 60
    seconds = remaining_seconds % 60
    print("used tool")
    return f"{days} days, {hours} hours, {minutes} minutes, {seconds} seconds"


@register_tool(description="Lists all files in a given directory that match a specific extension.")
def list_files_with_extension(directory_path: str, file_extension: str) -> list[str]:
    import os
    """
    Lists all files in a given directory that match a specific extension.
    Args:
        directory_path: The path to the directory to search.
        file_extension: The file extension to match (e.g., '.md').
    Returns:
        A list of file names that match the extension.
    """
    matching_files = []
    for filename in os.listdir(directory_path):
        if os.path.isfile(os.path.join(directory_path, filename)) and filename.endswith(file_extension):
            matching_files.append(filename)
    return matching_files

@register_tool(description="Ingests a large document or file. If the file is >32,768 tokens, it uses Tier 1 Context Caching to lock it into memory for 1 hour, significantly reducing future latency.")
def ingest_large_document(file_path: str) -> str:
    """
    Determines if a file is large enough for context caching (>32k tokens).
    If so, creates a cache. If not, returns the content normally.
    """
    from google import genai
    from google.genai import types
    import config
    import os
    from datetime import datetime, timedelta

    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' not found."

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        client = genai.Client(api_key=config.GEMINI_API_KEY)

        # Check token count
        token_count = client.models.count_tokens(
            model=config.GEMINI_MODEL,
            contents=content
        ).total_tokens

        if token_count > 32768:
            # Tier 1 Cache creation (TTL 1 hour)
            # Use a descriptive display name
            display_name = f"cache_{os.path.basename(file_path)}_{int(datetime.now().timestamp())}"

            cache = client.caches.create(
                model=config.GEMINI_MODEL,
                config=types.CreateCachedContentConfig(
                    display_name=display_name,
                    contents=[content],
                    ttl="3600s", # 1 hour
                )
            )
            return f"FILE_CACHED: The file is large ({token_count} tokens). It has been cached for 1 hour. Cache name: {cache.name}. All future turns in this session will use this cache for near-instant retrieval."
        else:
            return f"FILE_READ: The file is small ({token_count} tokens). No cache was created. Content:\n\n{content}"

    except Exception as e:
        return f"INGEST_ERROR: {str(e)}"

@register_tool(description="Submits a high-volume batch processing job to Google GenAI at 50% cost. Use for non-urgent tasks like massive translation or data extraction.")
def submit_batch_job(input_file_path: str, model_instruction: str) -> str:
    """
    Expects a path to a JSONL file where each line is a prompt.
    Returns the Batch Job ID for tracking.
    """
    from google import genai
    import config
    import os

    if not os.path.exists(input_file_path):
        return f"Error: Input file '{input_file_path}' not found."

    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)

        # Note: In a real implementation, you would upload the file to a bucket or use internal GCS refs
        # For this tool representation, we assume the file is ready for processing
        # Using the batch creation API
        job = client.batches.create(
            model=config.GEMINI_FAST_MODEL,
            src=input_file_path, # This usually requires a GCS URI in the real API
            # instruction=model_instruction # Real API uses the file content for instructions per line
        )
        return f"BATCH_JOB_SUBMITTED: Job ID: {job.name}. You can check status later using check_batch_status."

    except Exception as e:
        return f"BATCH_ERROR: {str(e)}"

@register_tool(description="Checks the status of a previously submitted Tier 1 Batch API job.")
def check_batch_status(job_id: str) -> str:
    from google import genai
    import config

    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        job = client.batches.get(name=job_id)

        status = job.state # e.g., 'COMPLETED', 'RUNNING', 'FAILED'
        progress = f"{job.completed_request_count}/{job.total_request_count}" if job.total_request_count else "Pending"

        return f"BATCH_STATUS: {status} ({progress}). " + (f"Results available at: {job.output_file}" if status == "COMPLETED" else "Check back later.")

    except Exception as e:
        return f"BATCH_STATUS_ERROR: {str(e)}"

