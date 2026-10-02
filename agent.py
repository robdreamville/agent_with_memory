import asyncio
import sys
import importlib
from typing import List, Optional
import tools 
from ai_engine import AIEngine
from memory import ChatMessage
import config

async def agent_loop():
    print("--- Nexus Prime AI Agent (Pydantic-Enabled) Initializing ---")
    
    # Allow choosing provider
    provider_choice = input(f"Choose AI Provider (default: {config.AI_PROVIDER}): ").strip().lower()
    if provider_choice not in ['ollama', 'gemini']:
        provider_choice = config.AI_PROVIDER
    
    print(f"Using Provider: {provider_choice.upper()}")
    agent = AIEngine(provider=provider_choice)
    
    print("\nReady. Type 'exit' to quit, 'archive' to trigger memory archival.")
    
    while True:
        try:
            user_input = input("\nYou: ").strip()
            
            if user_input.lower() in ['exit', 'quit']:
                print("Triggering auto-archival before exit...")
                await agent.archive_now()
                break
            if user_input.lower() == 'archive':
                await agent.archive_now()
                print("Archival complete.")
                continue
            if not user_input: continue

            # --- START THINKING CYCLE ---
            # 'active_chain' keeps the context alive during tool calls
            active_chain: Optional[List[ChatMessage]] = None
            
            while True:
                importlib.reload(tools)
                
                # Get provider-specific tool schemas, filtering by allowed tools for this agent
                if provider_choice == "gemini":
                    available_tools = tools.get_gemini_tools(allowed_tools=agent.manifest.active_tools)
                else:
                    available_tools = tools.get_ollama_tools(allowed_tools=agent.manifest.active_tools)
                
                # We pass active_chain back into chat to maintain context
                response_message, active_chain = await agent.chat(user_input, tools=available_tools, message_history=active_chain)
                
                # Check for Tool Calls
                if response_message.tool_calls:
                    async def execute_tool(tool_call):
                        func_name = tool_call['function']['name']
                        args = tool_call['function']['arguments']
                        
                        print(f"\n[Action] Using tool: {func_name}({args})")
                        
                        # Run the synchronous validate_and_call_tool in a thread pool to allow true concurrency
                        loop = asyncio.get_running_loop()
                        observation = await loop.run_in_executor(None, tools.validate_and_call_tool, func_name, args)
                        
                        print(f"[Observation] {func_name} -> {str(observation)[:100]}...")
                        
                        return ChatMessage(
                            role="tool",
                            name=func_name,
                            content=str(observation),
                        )

                    # Execute all tools simultaneously using Tier 1 concurrency power
                    tool_tasks = [execute_tool(tc) for tc in response_message.tool_calls]
                    tool_results = await asyncio.gather(*tool_tasks)
                    
                    active_chain.extend(tool_results)
                    
                    # Loop back - the LLM now sees its own tool calls and the results in its history
                    continue 
                else:
                    # Final answer received
                    content = response_message.content
                    print(f"\nNexus Prime: {content}")
                    
                    # Now that the task is DONE, save the final interaction to memory
                    await agent.memory.add_to_working_memory(user_input, content)
                    break

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nError in agent loop: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(agent_loop())
