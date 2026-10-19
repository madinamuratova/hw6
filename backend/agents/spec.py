"""How a role is described (AgentSpec) and turned into a PydanticAI agent."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset

from backend.config import PROMPTS_DIR
from backend.models import AgentName, AgentReport, SpecialistName, TeamDeps

# MCP tools no agent may ever see: they need a human (backend/approvals.py).
HUMAN_ONLY_TOOLS = frozenset({"approve_proposal", "reject_proposal", "reset_working_database"})


@dataclass(frozen=True)
class AgentSpec:
    name: AgentName
    title: str
    prompt_file: str  # file in backend/prompts/
    mcp_tools: tuple[str, ...]  # the only MCP tools this agent can see
    can_delegate_to: tuple[SpecialistName, ...] = ()
    output_type: type = AgentReport

    def __post_init__(self) -> None:
        if HUMAN_ONLY_TOOLS & set(self.mcp_tools):
            raise ValueError(f"{self.title} may not use human-only tools {sorted(HUMAN_ONLY_TOOLS & set(self.mcp_tools))}")

    def instructions(self) -> str:
        return (PROMPTS_DIR / self.prompt_file).read_text()


def build_agent(
    spec: AgentSpec,
    model: Model,
    shop_mcp: MCPToolset,
    delegation_tools: AbstractToolset[TeamDeps],
) -> Agent[TeamDeps, object]:
    allowed = frozenset(spec.mcp_tools)
    tools = shop_mcp.filtered(lambda ctx, tool_def: tool_def.name in allowed)
    toolsets = [tools, delegation_tools] if spec.can_delegate_to else [tools]
    return Agent(
        model,
        name=spec.title,
        instructions=spec.instructions(),
        deps_type=TeamDeps,
        output_type=spec.output_type,
        toolsets=toolsets,
        retries=2,
    )
