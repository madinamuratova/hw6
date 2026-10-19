"""Shared data types for the Campus Customs agent team.

Agents hand these structured objects to each other instead of free text,
so every report says where its facts came from and what still needs a human.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from backend.team import Team

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
SpecialistName = Literal["inventory", "accounting", "facilities", "customer_service"]

AGENT_TITLES: dict[str, str] = {
    "boss": "Boss",
    "inventory": "Inventory",
    "accounting": "Accounting",
    "facilities": "Facilities",
    "customer_service": "Customer Service",
}


# --- What specialists report back ------------------------------------------------


class Fact(BaseModel):
    """One checked fact. Numbers and dates are copied exactly from a tool result."""

    statement: str
    source_tool: str = Field(description="The MCP tool (or delegated agent) that returned this fact.")


class AgentReport(BaseModel):
    """What a specialist hands back to the agent that delegated to it."""

    agent: SpecialistName
    ticket_ids: list[int] = Field(default_factory=list)
    summary: str = Field(description="Two or three sentences: what you found and what you did.")
    facts: list[Fact] = Field(default_factory=list)
    actions_taken: list[str] = Field(
        default_factory=list,
        description="Only actions a tool confirmed, e.g. 'Saved draft #3' or 'Proposed payment #1 (pending approval)'.",
    )
    needs_human: list[str] = Field(default_factory=list, description="Decisions only a human may make.")
    blockers: list[str] = Field(default_factory=list, description="Rules or missing data that stopped the work.")


# --- What the Boss reports at the end of a run -----------------------------------


class TicketOutcome(BaseModel):
    ticket_id: int
    status: Literal["handled", "waiting_on_human", "blocked"]
    summary: str
    actions_taken: list[str] = Field(default_factory=list)
    human_decisions_needed: list[str] = Field(default_factory=list)


class ShiftReport(BaseModel):
    """The Boss's final report for the whole run."""

    shop_date: str = Field(description="desk.date_today, from get_shop_date.")
    tickets: list[TicketOutcome]
    payments_made: list[str] = Field(default_factory=list)
    drafts_saved: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# --- Dashboard API (Problem 8, backend/main.py) -----------------------------------


class ApproveRequest(BaseModel):
    """Sent by the dashboard when a human clicks Approve."""

    approved_by: str = Field(min_length=1, description="The human's name.")


class RejectRequest(BaseModel):
    rejected_by: str = Field(min_length=1, description="The human's name.")
    note: str = ""


class ResolveRequest(BaseModel):
    """Sent when a human marks a ticket resolved from the dashboard."""

    resolved_by: str = Field(min_length=1, description="The human's name.")
    resolution: str = "Marked resolved from the dashboard."


class ResetRequest(BaseModel):
    requested_by: str = Field(min_length=1, description="The human's name.")


class RunInfo(BaseModel):
    """One agent-team run started from the dashboard."""

    run_id: str
    ticket_id: int
    status: Literal["running", "finished", "failed"]
    started_at: str
    finished_at: str | None = None
    report: dict[str, Any] | None = None
    error: str | None = None
    usage: dict[str, int] | None = None


# --- Run context passed to every agent --------------------------------------------


@dataclass
class TeamDeps:
    """Per-agent-run context. A new one is made for every delegation."""

    team: Team
    run_id: str
    agent: AgentName
    depth: int = 0
    called_by: AgentName | None = None
