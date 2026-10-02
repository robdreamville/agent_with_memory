import ollama

model = "gemma4:e2b" # Ensure the tag is correct (e.g., 2b or 7b)

# This list acts as Bob's "Short-Term Memory" (Context Window)
messages = [{"role": "system", "content": "You are Bob, a helpful assistant."}]

def ask_bob(user_input):
    # Add user message to memory
    messages.append({"role": "user", "content": user_input})
    
    stream = ollama.chat(
        model=model,
        messages=messages,
        stream=True,
    )

    print("Bob: ", end="", flush=True)
    full_response = ""
    
    for chunk in stream:
        content = chunk['message']['content']
        print(content, end="", flush=True)
        full_response += content
    
    # Add Bob's own response to memory so he remembers the context
    messages.append({"role": "assistant", "content": full_response})
    print("\n")

# Example usage
ask_bob("Hi Bob, remember my name is Roberto.")
ask_bob("What is my name?")