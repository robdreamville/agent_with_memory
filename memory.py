import hashlib
import json
import os
from collections import deque
from datetime import datetime
from typing import List, Dict, Any, Optional, Literal
import chromadb
import ollama

from pydantic import BaseModel, Field

class MemoryFact(BaseModel):
    content: str = Field(description="The factual description of the memory")
    keywords: List[str] = Field(description="2-3 trigger words for retrieval")
    tags: List[str] = Field(description="Context tags (user, identity, shared, private)")
    importance_score: float = Field(description="0.0-1.0 importance score")
    visibility: Literal['shared', 'private'] = Field(description="Visibility level")
    rationale: str = Field(description="Brief explanation of why this memory is worth keeping")

class MemoryExtraction(BaseModel):
    memories: List[MemoryFact]

class ReflexMemory(BaseModel):
    content: str
    tags: List[str]
    importance_score: float
    id: Optional[str] = None

class ChatMessage(BaseModel):
    role: Literal['system', 'user', 'assistant', 'tool']
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

class JudgeEvaluation(BaseModel):
    """Enforces that the local model can only return valid JSON matching this schema."""
    evaluation: Literal['COMPLETE', 'PARTIAL', 'NONE']

class MemoryManager:
    """
    MemoryManager implements a tiered memory system for multi-agent environments.
    Tier 1: Reflex (Isolated per Agent)
    Tier 2: Working Memory (Isolated per Agent)
    Tier 3: Permanent Vault (Single shared ChromaDB collection with metadata filtering)
    """

    def __init__(self, agent_id: str, db_path: str = "./chroma_db", model: str = "gemma4:e2b", provider: str = "ollama", is_head_agent: bool = False):
        self.agent_id = agent_id
        self.model = model
        self.db_path = db_path
        self.provider = provider
        self.is_head_agent = is_head_agent
        
        # Ensure db_path exists
        os.makedirs(db_path, exist_ok=True)
        
        # Tier 1: Entity Map (Refactored from Reflex Cache)
        # Stores: { "keyword": [ReflexMemory, ...] }
        
        reflex_dir = "./reflex_storage" 
        os.makedirs(reflex_dir, exist_ok=True)

        self.reflex_file = os.path.join(reflex_dir, f"reflex_{agent_id}.json")
        self.entity_map: Dict[str, List[ReflexMemory]] = self._load_entity_map()

        # Tier 2: Working Memory (Conversation Buffer)
        self.working_memory: deque[Dict[str, Any]] = deque(maxlen=15)

        # Tier 3: Permanent Vault (ChromaDB)
        self.chroma_client = chromadb.PersistentClient(path=db_path)
        self.collection = self.chroma_client.get_or_create_collection(
            name="permanent_vault",
            metadata={"hnsw:space": "cosine"}
        )

    def _load_entity_map(self) -> Dict[str, List[ReflexMemory]]:
        """Loads the Tier 1 keyword map from disk."""
        if os.path.exists(self.reflex_file):
            try:
                with open(self.reflex_file, "r") as f:
                    data = json.load(f)
                    return {k: [ReflexMemory(**m) for m in v] for k, v in data.items()}
            except (json.JSONDecodeError, IOError, Exception):
                return {}
        return {}

    def _save_entity_map(self):
        """Saves the Tier 1 keyword map to disk."""
        with open(self.reflex_file, "w") as f:
            data = {k: [m.model_dump() for m in v] for k, v in self.entity_map.items()}
            json.dump(data, f, indent=4)

    async def add_to_working_memory(self, user_input: str, assistant_response: str, success_score: float = 1.0):
        """Adds interaction to Tier 2 (Working Memory) and checks for archival."""
        timestamp = datetime.now().isoformat()
        interaction = {
            "timestamp": timestamp,
            "user": user_input,
            "assistant": assistant_response,
            "success_score": success_score
        }
        self.working_memory.append(interaction)

        # Archive oldest 5 messages when buffer hits 15
        if len(self.working_memory) >= 15:
            to_archive = [self.working_memory.popleft() for _ in range(5)]
            await self.review_and_archive(batch=to_archive)

    def add_to_entity_map(self, keywords: List[str], memory_obj: ReflexMemory):
        """Promotes a memory to Tier 1 for fast keyword-based retrieval."""
        for kw in keywords:
            kw = kw.lower().strip()
            if kw not in self.entity_map:
                self.entity_map[kw] = []
            
            # Avoid duplicate content for the same keyword
            if not any(m.content == memory_obj.content for m in self.entity_map[kw]):
                self.entity_map[kw].append(memory_obj)
        
        # Always save immediately after modification
        self._save_entity_map()

    async def get_all_reflexes(self, query: str) -> List[str]:
        """
        Tier 1 Retrieval: Scans query for keywords and validates context via tags.
        Returns ALL valid matching facts.
        """
        import re
        
        query_lower = query.lower()
        matches: List[ReflexMemory] = []

        # 1. Keyword Scanning (Collect all potential matches)
        for kw, potential_memories in self.entity_map.items():
            if kw in query_lower:
                matches.extend(potential_memories)

        if not matches:
            return []

        # 2. Contextual Validation
        user_markers = [r"\bmy\b", r"\bi\b", r"\bme\b", r"\bmine\b", r"\broberto\b"]
        query_has_user_marker = any(re.search(marker, query_lower) for marker in user_markers)
        
        valid_contents = []
        unique_contents = set() # Avoid duplicates across keywords

        for m in matches:
            content = m.content
            if content in unique_contents:
                continue

            tags = [t.lower() for t in m.tags]
            
            # IDENTITY PROTECTION: 
            # If the memory is tagged as 'user' or 'identity', we REQUIRE 
            # an identity marker in the query (e.g., "my", "i", "me", "roberto").
            if "user" in tags or "identity" in tags:
                if not query_has_user_marker:
                    continue 

            valid_contents.append(content)
            unique_contents.add(content)

        return valid_contents

    def get_working_context(self) -> List[Dict[str, Any]]:
        """Tier 2: Retrieve recent conversation context."""
        return list(self.working_memory)

    async def search_permanent(self, query: str, n_results: int = 5, include_shared: bool = True) -> List[Dict[str, Any]]:
        """Tier 3: Semantic search in ChromaDB Vault."""
        if self.is_head_agent:
            # God-mode: Head agent sees everything
            where_clause = None
        elif include_shared:
            where_clause = {"$or": [{"owner_id": self.agent_id}, {"visibility": "shared"}]}
        else:
            where_clause = {"owner_id": self.agent_id}

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_clause
        )
        
        formatted_results = []
        if results['documents']:
            for i in range(len(results['documents'][0])):
                doc_content = results['documents'][0][i]
                metadata = results['metadatas'][0][i]
                
                if metadata.get('visibility') == 'private' and metadata.get('owner_id') != self.agent_id:
                    continue
                    
                formatted_results.append({
                    "content": doc_content,
                    "metadata": metadata,
                    "distance": results['distances'][0][i]
                })
        return formatted_results
        

    async def review_and_archive(self, batch: Optional[List[Dict[str, Any]]] = None):
        """
        The Gatekeeper Protocol: Distills history into tagged, keyword-indexed memories.
        """
        target_memory = batch if batch else list(self.working_memory)
        if not target_memory: return

        history_str = "\n".join([f"U: {i['user']}\nA: {i['assistant']}" for i in target_memory])

        prompt = f"""
        Extract key facts from the history.
        
        TAGGING RULES:
        - Use 'user' tag for facts about the human.
        - Use 'identity' tag for names or birthdays.
        - Use 'shared' for general knowledge, 'private' for agent logic.

        Return ONLY a JSON list:
        [
            {{
                "content": "fact description",
                "keywords": ["2-3 trigger words"],
                "tags": ["context tags"],
                "importance_score": 0.0-1.0,
                "visibility": "shared/private",
                "rationale": "Brief explanation of why this memory is worth keeping"
            }}
        ]

        History:
        {history_str}
        """

        try:
            if self.provider == "gemini":
                from google import genai
                from google.genai import types
                import config
                
                client = genai.Client(api_key=config.GEMINI_API_KEY)
                
                response = client.models.generate_content(
                    model=config.GEMINI_FAST_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=MemoryExtraction
                    )
                )
                extracted_data = MemoryExtraction.model_validate_json(response.text)
                extracted = extracted_data.memories
            else:
                response = ollama.chat(
                    model=self.model, 
                    messages=[{"role": "user", "content": prompt}], 
                    format=MemoryExtraction.model_json_schema()
                )
                extracted_data = MemoryExtraction.model_validate_json(response['message']['content'])
                extracted = extracted_data.memories
            
            # Batch collections for Tier 3 Vault insertion
            docs_to_add = []
            metas_to_add = []
            ids_to_add = []

            for item in extracted:
                content = item.content
                if not content: continue
                
                importance = item.importance_score
                visibility = item.visibility
                tags = item.tags
                keywords = item.keywords
                rationale = item.rationale

                doc_id = f"mem_{self.agent_id}_{datetime.now().timestamp()}_{len(docs_to_add)}"
                
                docs_to_add.append(content)
                metas_to_add.append({
                    "owner_id": self.agent_id,
                    "visibility": visibility,
                    "tags": ",".join(tags),
                    "importance_score": importance,
                    "rationale": rationale,
                    "timestamp": datetime.now().isoformat()
                })
                ids_to_add.append(doc_id)

                # Store in Tier 1 (Entity Map) if important enough
                # Lowered threshold to 0.8 as discussed
                if importance >= 0.8:
                    self.add_to_entity_map(keywords, ReflexMemory(
                        content=content,
                        tags=tags,
                        importance_score=importance,
                        id=doc_id
                    ))
            
            # Perform a single batch insert into Tier 3 (Vault)
            if docs_to_add:
                self.collection.add(
                    documents=docs_to_add,
                    metadatas=metas_to_add,
                    ids=ids_to_add
                )
            
        except Exception as e:
            print(f"Error in review_and_archive: {e}")
            pass
