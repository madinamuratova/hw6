"""The human approval path: the ONLY code that can move cash.

Agents only create pending proposals (propose_payment / propose_purchase).
These functions are called by the terminal runner (backend/cli.py). They send the backend's HUMAN_KEY
to the MCP server, which redoes every check (enough cash, unpaid invoices,
vendor rules) before it changes the balance. The key is never logged.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai.mcp import MCPToolset

from backend.audit import AuditTrail
from backend.shop_mcp import HUMAN_KEY, call_shop_tool

APPROVAL_RUN_ID = "human-decisions"


def _log(
    audit: AuditTrail, *, phase: str, action: str, tool: str, args: dict[str, Any], result: dict, ticket_id: int | None = None
) -> None:
    audit.append(
        run_id=APPROVAL_RUN_ID,
        ticket_id=ticket_id,
        agent="Human",
        depth=0,
        called_by=None,
        step=None,
        phase=phase,
        action=action,
        delegated=False,
        used_tool=True,
        tools_called=[{"tool": tool, "args": args}],  # args never include the human key
        ok=bool(result.get("ok")),
        result=result,
    )


async def _proposal_ticket(shop_mcp: MCPToolset, proposal_id: int) -> int | None:
    proposals = await call_shop_tool(shop_mcp, "list_proposals", {})
    return next((p["ticket_id"] for p in proposals if p["id"] == proposal_id), None)


async def approve(shop_mcp: MCPToolset, audit: AuditTrail, proposal_id: int, approved_by: str) -> dict:
    args = {"proposal_id": proposal_id, "approved_by": approved_by}
    ticket_id = await _proposal_ticket(shop_mcp, proposal_id)
    result = await call_shop_tool(shop_mcp, "approve_proposal", {**args, "human_key": HUMAN_KEY})
    if not result.get("ok"):
        action = f"Approval of proposal #{proposal_id} refused: {result.get('reason')}"
    elif result.get("kind") == "price_override":
        action = f"{approved_by} approved proposal #{proposal_id}: {result['change']}"
    else:
        action = f"{approved_by} approved proposal #{proposal_id}: paid {result['amount']:.2f}, balance now {result['new_balance']:.2f}"
    _log(audit, phase="approval_decision", action=action, tool="approve_proposal", args=args, result=result, ticket_id=ticket_id)
    return result


async def reject(shop_mcp: MCPToolset, audit: AuditTrail, proposal_id: int, rejected_by: str, note: str = "") -> dict:
    args = {"proposal_id": proposal_id, "rejected_by": rejected_by, "note": note}
    ticket_id = await _proposal_ticket(shop_mcp, proposal_id)
    result = await call_shop_tool(shop_mcp, "reject_proposal", {**args, "human_key": HUMAN_KEY})
    action = (
        f"{rejected_by} rejected proposal #{proposal_id}"
        if result.get("ok")
        else f"Rejection of proposal #{proposal_id} refused: {result.get('reason')}"
    )
    _log(audit, phase="approval_decision", action=action, tool="reject_proposal", args=args, result=result, ticket_id=ticket_id)
    return result


async def reset(shop_mcp: MCPToolset, audit: AuditTrail, requested_by: str) -> dict:
    args = {"requested_by": requested_by}
    result = await call_shop_tool(shop_mcp, "reset_working_database", {**args, "human_key": HUMAN_KEY})
    action = "Working database reset to original values" if result.get("ok") else f"Reset refused: {result.get('reason')}"
    _log(audit, phase="reset", action=action, tool="reset_working_database", args=args, result=result)
    return result


async def resolve(shop_mcp: MCPToolset, audit: AuditTrail, ticket_id: int, resolved_by: str, resolution: str) -> dict:
    """A human marks a ticket resolved (refused by the server while a proposal for it is pending)."""
    args = {"ticket_id": ticket_id, "resolution": f"{resolution} (by {resolved_by})"}
    result = await call_shop_tool(shop_mcp, "resolve_ticket", args)
    action = (
        f"{resolved_by} marked ticket {ticket_id} resolved"
        if result.get("ok")
        else f"Resolving ticket {ticket_id} refused: {result.get('reason')}"
    )
    _log(audit, phase="ticket_resolved", action=action, tool="resolve_ticket", args=args, result=result, ticket_id=ticket_id)
    return result


async def review_in_terminal(shop_mcp: MCPToolset, audit: AuditTrail) -> None:
    """Ask a human at the terminal to approve or reject each pending proposal (used by backend/cli.py)."""
    pending = await call_shop_tool(shop_mcp, "list_proposals", {"status": "pending"})
    if not pending:
        print("\nNo proposals waiting for approval.")
        return
    for p in pending:
        what = f"{p['qty']} x {p['sku']} size {p['size']} from vendor {p['ref_id']}" if p["kind"] == "purchase" else f"{p['kind']} {p['ref_id']}"
        print(f"\nPROPOSAL #{p['id']} by {p['proposed_by']}: pay {p['amount']:.2f} from {p['account']} for {what}")
        print(f"  Reason: {p['reason']}")
        answer = input("Type your full name to APPROVE, 'r' to reject, or Enter to leave it pending: ").strip()
        if answer.lower() == "r":
            name = input("Your name (for the record): ").strip() or "terminal user"
            print(await reject(shop_mcp, audit, p["id"], name))
        elif answer:
            print(await approve(shop_mcp, audit, p["id"], answer))
