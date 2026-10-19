"""Inventory: stock levels, product cost/price, vendors, lead times. Can only PROPOSE purchases."""

from backend.agents.spec import AgentSpec

SPEC = AgentSpec(
    name="inventory",
    title="Inventory",
    prompt_file="inventory.md",
    mcp_tools=(
        "get_ticket",
        "get_shop_date",
        "check_stock",
        "get_pricing",
        "list_vendors",
        "list_proposals",
        "propose_purchase",  # a human approves it; approval pays and drafts the vendor order
        "propose_price_override",  # a human decides the price; no cash moves
    ),
)
