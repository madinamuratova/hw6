"""Data models for the Campus Customs vendor-desk agent."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


class VendorReport(BaseModel):
    """The agent's answer for one vendor document (handbook section 13)."""

    vendor: str = Field(description="Name of the vendor that sent or issued the document.")
    sku: str | None = Field(description="Campus Customs SKU, e.g. CC-HD-006. null if the document does not say.")
    unit_price: float | None = Field(description="Quoted price per unit in USD. null if the document does not say.")
    lead_time_days: int | None = Field(description="Lead time in days, as stated by the vendor. null if the document does not say.")
    min_order: int | None = Field(description="Minimum order quantity in units. null if the document does not say.")
    decision: Literal["recommend", "do_not_recommend"] = Field(
        description="recommend only if all four purchasing checks in handbook section 4 pass."
    )
    reason: str = Field(description="One sentence that names the purchasing check that decided it.")


@dataclass
class AgentDeps:
    """Context for one agent run, passed to every tool."""

    run_id: str
    document: str  # path of the document being reviewed, relative to the HW 6 folder
    events: list[dict] = field(default_factory=list)  # security events from tools and guards, for the audit trail
