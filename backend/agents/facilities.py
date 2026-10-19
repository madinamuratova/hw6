"""Facilities: the shop lease, rent notices, and the landlord."""

from backend.agents.spec import AgentSpec

SPEC = AgentSpec(
    name="facilities",
    title="Facilities",
    prompt_file="facilities.md",
    mcp_tools=("get_ticket", "get_shop_date", "get_rent_and_cash", "draft_customer_reply"),
    can_delegate_to=("accounting",),  # rent payments go through Accounting
)
