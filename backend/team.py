"""The Campus Customs agent team.

Builds the five agents, runs each one step by step (logging every step to the
audit trail), and lets agents delegate to each other. Agents can only PROPOSE
payments and purchases; a human approves them later through the human approval
step (backend/approvals.py), which is the only path that moves cash.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from functools import partial
from typing import Any

from pydantic_ai import FunctionToolset, ModelRetry, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage, UsageLimits

from backend.agents import AGENT_SPECS, build_agent
from backend.audit import DELEGATE_TOOL, AuditTrail, describe_node
from backend.config import MAX_DELEGATION_DEPTH, USAGE_LIMITS
from backend.models import AGENT_TITLES, AgentName, AgentReport, ShiftReport, SpecialistName, TeamDeps

delegation_tools: FunctionToolset[TeamDeps] = FunctionToolset()


@delegation_tools.tool(name=DELEGATE_TOOL)
async def delegate(
    ctx: RunContext[TeamDeps], to: SpecialistName, task: str, ticket_id: int | None = None
) -> AgentReport | str:
    """Hand one clear task to a teammate and get their report back.

    Args:
        to: The teammate who should do the work.
        task: What you need, including the ticket fields and facts already confirmed.
        ticket_id: The ticket this task is about, if any.
    """
    deps = ctx.deps
    allowed = AGENT_SPECS[deps.agent].can_delegate_to
    if to not in allowed:
        raise ModelRetry(f"{AGENT_TITLES[deps.agent]} can only delegate to: {', '.join(allowed)}.")
    if deps.depth >= MAX_DELEGATION_DEPTH:
        raise ModelRetry("Delegation limit reached. Finish with the information you have.")

    about = f" about ticket {ticket_id}" if ticket_id is not None else ""
    message = f"Task from {AGENT_TITLES[deps.agent]}{about}:\n{task}"
    try:
        return await deps.team.run_agent(to, message, depth=deps.depth + 1, called_by=deps.agent, usage=ctx.usage)
    except UsageLimitExceeded:
        raise  # the token budget is for the whole team, so stop everything
    except Exception as exc:  # one teammate failing shouldn't crash the whole shift
        deps.team.log(
            agent=to, depth=deps.depth + 1, called_by=deps.agent, phase="error",
            action=f"{AGENT_TITLES[to]} failed: {type(exc).__name__}: {exc}",
        )
        return f"{AGENT_TITLES[to]} could not finish this task ({type(exc).__name__}: {exc})."


def new_run_id() -> str:
    return f"run-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


class Team:
    def __init__(
        self,
        *,
        model: Model,
        shop_mcp: MCPToolset,
        audit: AuditTrail,
        usage_limits: UsageLimits = USAGE_LIMITS,
        run_id: str | None = None,
        ticket_id: int | None = None,
    ):
        self.shop_mcp = shop_mcp
        self.audit = audit
        self.usage_limits = usage_limits
        self.run_id = run_id or new_run_id()
        self.ticket_id = ticket_id  # set for single-ticket runs; tags every audit record
        # Hide the delegate tool from agents that are already at the depth limit.
        visible_delegation = delegation_tools.filtered(lambda ctx, tool_def: ctx.deps.depth < MAX_DELEGATION_DEPTH)
        self.agents = {
            name: build_agent(spec, model, shop_mcp, visible_delegation) for name, spec in AGENT_SPECS.items()
        }

    def log(
        self,
        *,
        agent: AgentName | None,
        phase: str,
        action: str,
        depth: int = 0,
        called_by: AgentName | None = None,
        step: int | None = None,
        **extra: Any,
    ) -> None:
        self.audit.append(
            run_id=self.run_id,
            ticket_id=self.ticket_id,
            agent=AGENT_TITLES[agent] if agent else "System",
            depth=depth,
            called_by=AGENT_TITLES[called_by] if called_by else None,
            step=step,
            phase=phase,
            action=action,
            **{"delegated": False, "used_tool": False, **extra},
        )

    async def run_shift(self, task: str) -> tuple[ShiftReport, RunUsage]:
        """Run the Boss on a task. The MCP server stays up for the whole run."""
        usage = RunUsage()
        async with self.shop_mcp:
            await self._check_tools()
            self.log(agent=None, phase="system_start", action=f"Run started: {task}")
            try:
                report = await self.run_agent("boss", task, depth=0, called_by=None, usage=usage)
            except BaseException as exc:  # includes Ctrl-C / cancellation, so the trail shows why it stopped
                self.log(agent=None, phase="system_error", action=f"{type(exc).__name__}: {exc}", usage=usage_dict(usage))
                raise
            self.log(agent=None, phase="system_end", action="Run finished", usage=usage_dict(usage))
        return report, usage

    async def run_agent(
        self,
        name: AgentName,
        task: str,
        *,
        depth: int,
        called_by: AgentName | None,
        usage: RunUsage,
    ) -> Any:
        """Run one agent's loop, logging each step to the audit trail."""
        agent = self.agents[name]
        deps = TeamDeps(team=self, run_id=self.run_id, agent=name, depth=depth, called_by=called_by)
        log = partial(self.log, agent=name, depth=depth, called_by=called_by)
        asked_by = f" (asked by {AGENT_TITLES[called_by]})" if called_by else ""
        log(phase="agent_start", action=f"{AGENT_TITLES[name]} started{asked_by}")

        step = 0
        async with agent.iter(task, deps=deps, usage=usage, usage_limits=self.usage_limits) as run:
            async for node in run:
                step += 1
                log(step=step, **describe_node(node))
        return run.result.output

    async def _check_tools(self) -> None:
        """Fail fast if a role lists an MCP tool the server doesn't have."""
        available = {tool.name for tool in await self.shop_mcp.list_tools()}
        missing = sorted(
            f"{spec.name}:{tool}" for spec in AGENT_SPECS.values() for tool in spec.mcp_tools if tool not in available
        )
        if missing:
            raise RuntimeError(f"MCP server is missing tools: {missing}")


def usage_dict(usage: RunUsage) -> dict[str, int]:
    return {
        "requests": usage.requests,
        "tool_calls": usage.tool_calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }
