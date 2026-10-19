"""Boss: reads the ticket queue, delegates each ticket, resolves finished tickets, writes the report."""

from backend.agents.spec import AgentSpec
from backend.models import ShiftReport

SPEC = AgentSpec(
    name="boss",
    title="Boss",
    prompt_file="boss.md",
    mcp_tools=("list_open_tickets", "get_ticket", "get_shop_date", "list_proposals", "resolve_ticket"),
    can_delegate_to=("inventory", "accounting", "facilities", "customer_service"),
    output_type=ShiftReport,
)
