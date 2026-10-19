"""Customer Service: drafts replies to customers and student groups (never sends them)."""

from backend.agents.spec import AgentSpec

SPEC = AgentSpec(
    name="customer_service",
    title="Customer Service",
    prompt_file="customer_service.md",
    mcp_tools=("get_ticket", "get_shop_date", "check_stock", "get_pricing", "draft_customer_reply"),
    can_delegate_to=("inventory",),  # restock questions go to Inventory
)
