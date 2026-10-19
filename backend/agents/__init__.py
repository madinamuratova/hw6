"""The five Campus Customs roles. Each file in this folder describes one role."""

from backend.agents import accounting, boss, customer_service, facilities, inventory
from backend.agents.spec import AgentSpec, build_agent

AGENT_SPECS: dict[str, AgentSpec] = {
    spec.name: spec
    for spec in (boss.SPEC, inventory.SPEC, accounting.SPEC, facilities.SPEC, customer_service.SPEC)
}

__all__ = ["AGENT_SPECS", "AgentSpec", "build_agent"]
