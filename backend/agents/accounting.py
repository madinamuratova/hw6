"""Accounting: cash, invoices, payments. Can only PROPOSE payments; a human approves them."""

from backend.agents.spec import AgentSpec

SPEC = AgentSpec(
    name="accounting",
    title="Accounting",
    prompt_file="accounting.md",
    mcp_tools=(
        "get_ticket",
        "get_shop_date",
        "get_cash_and_payments",
        "list_unpaid_invoices",
        "get_rent_and_cash",
        "list_proposals",
        "propose_payment",  # no cash moves until a human approves it
    ),
)
