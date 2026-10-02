import json
import os
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class AgentManifest(BaseModel):
    agent_id: str = Field(description="Unique identifier for the agent (e.g., 'nexus_prime')")
    persona_name: str = Field(description="Human-friendly name for the agent")
    system_prompt: str = Field(description="The core instructions that define the agent's behavior")
    specialization: List[str] = Field(default_factory=list, description="List of task types this agent is an expert in")
    active_tools: List[str] = Field(default_factory=list, description="List of tool names this agent is allowed to use")
    is_head_agent: bool = Field(default=False, description="Whether this is the primary orchestrator")

class AgentRegistry:
    def __init__(self, registry_file: str = "agents.json"):
        self.registry_file = registry_file
        self.agents: Dict[str, AgentManifest] = self._load_registry()

    def _load_registry(self) -> Dict[str, AgentManifest]:
        if not os.path.exists(self.registry_file):
            return {}
        try:
            with open(self.registry_file, "r") as f:
                data = json.load(f)
                return {k: AgentManifest(**v) for k, v in data.items()}
        except (json.JSONDecodeError, IOError, Exception) as e:
            print(f"Error loading registry: {e}")
            return {}

    def save_agent(self, manifest: AgentManifest):
        self.agents[manifest.agent_id] = manifest
        self._save_to_disk()

    def delete_agent(self, agent_id: str):
        if agent_id in self.agents:
            del self.agents[agent_id]
            self._save_to_disk()

    def get_agent(self, agent_id: str) -> Optional[AgentManifest]:
        return self.agents.get(agent_id)

    def list_agents(self) -> List[AgentManifest]:
        return list(self.agents.values())

    def _save_to_disk(self):
        try:
            with open(self.registry_file, "w") as f:
                data = {k: v.model_dump() for k, v in self.agents.items()}
                json.dump(data, f, indent=4)
        except IOError as e:
            print(f"Error saving registry: {e}")

# Global registry instance
registry = AgentRegistry()
