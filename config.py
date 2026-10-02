import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any, Literal

class Settings(BaseSettings):
    # AI Provider Settings
    AI_PROVIDER: Literal["ollama", "gemini"] = "ollama"

    # Gemini Settings
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_FAST_MODEL: str = "gemini-2.5-flash"
    GEMINI_SEARCH_MODEL: str = "gemini-2.0-flash"

    # Ollama Settings
    OLLAMA_MODEL: str = "gemma4:e2b"
    OLLAMA_DECOMPOSER_MODEL: str = "qwen2.5:1.5b"
    OLLAMA_OPTIONS: Dict[str, Any] = {
        "temperature": 0.7,
        "num_ctx": 4096,
    }
    OLLAMA_FAST_OPTIONS: Dict[str, Any] = {
        "num_ctx": 1024,
        "num_predict": 10,
    }

    # Memory Settings
    CHROMA_DB_PATH: str = "./chroma_db"
    REFLEX_DATA_PATH: str = "./reflex_storage"
    WORKING_MEMORY_MAX_SIZE: int = 15

    # Agent Registry
    REGISTRY_FILE: str = "agents.json"
    DEFAULT_AGENT_ID: str = "nexus_prime"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Instantiate settings
settings = Settings()

# Maintain backward compatibility by exporting variables
AI_PROVIDER = settings.AI_PROVIDER
GEMINI_API_KEY = settings.GEMINI_API_KEY
GEMINI_MODEL = settings.GEMINI_MODEL
GEMINI_FAST_MODEL = settings.GEMINI_FAST_MODEL
GEMINI_SEARCH_MODEL = settings.GEMINI_SEARCH_MODEL
OLLAMA_MODEL = settings.OLLAMA_MODEL
OLLAMA_DECOMPOSER_MODEL = settings.OLLAMA_DECOMPOSER_MODEL
OLLAMA_OPTIONS = settings.OLLAMA_OPTIONS
OLLAMA_FAST_OPTIONS = settings.OLLAMA_FAST_OPTIONS
CHROMA_DB_PATH = settings.CHROMA_DB_PATH
REFLEX_DATA_PATH = settings.REFLEX_DATA_PATH
WORKING_MEMORY_MAX_SIZE = settings.WORKING_MEMORY_MAX_SIZE
DEFAULT_AGENT_ID = settings.DEFAULT_AGENT_ID

# For the system prompt, we now prefer getting it from the registry, 
# but we'll provide a fallback for initialization.
DEFAULT_SYSTEM_PROMPT = "You are a helpful, direct AI assistant. NEVER narrate your internal thought process, explain your reasoning out loud, or prefix your responses with 'The user said...' or 'Based on the context...'. Provide ONLY the final, direct answer."