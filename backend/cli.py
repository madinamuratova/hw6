"""Run the Campus Customs agent team from the terminal.

From the HW 6 folder:
    .venv/bin/python -m backend.cli                    # all open tickets, then approve/reject proposals here
    .venv/bin/python -m backend.cli --tickets 102      # only the tickets you list
    .venv/bin/python -m backend.cli --no-approvals     # leave every proposal pending for a human to decide later
    .venv/bin/python -m backend.cli --review           # no agents: just approve/reject pending proposals
    .venv/bin/python -m backend.cli --reset "Your Name"  # no agents: reset the working database (human only)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from backend import approvals
from backend.audit import AuditTrail
from backend.config import AUDIT_PATH, MODEL_NAME, OUTPUT_DIR, build_model
from backend.shop_mcp import call_shop_tool, load_shop_mcp
from backend.team import Team


def build_task(ticket_ids: list[int]) -> str:
    if ticket_ids:
        return f"Handle these open tickets: {', '.join(map(str, ticket_ids))}."
    return "Handle every open ticket in the queue."


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team")
    parser.add_argument("--tickets", type=int, nargs="*", default=[], help="ticket ids (default: all open)")
    parser.add_argument("--no-approvals", action="store_true", help="don't ask; leave proposals pending")
    parser.add_argument("--review", action="store_true", help="only review pending proposals (no agents)")
    parser.add_argument("--reset", metavar="NAME", help="reset the working database to the original (no agents)")
    args = parser.parse_args()

    shop_mcp = load_shop_mcp()
    audit = AuditTrail(AUDIT_PATH)

    if args.reset or args.review:
        async with shop_mcp:
            if args.reset:
                print(json.dumps(await approvals.reset(shop_mcp, audit, args.reset), indent=2))
            if args.review:
                await approvals.review_in_terminal(shop_mcp, audit)
        return

    interactive = sys.stdin.isatty() and not args.no_approvals
    team = Team(model=build_model(), shop_mcp=shop_mcp, audit=audit)
    print(f"Run {team.run_id} | model {MODEL_NAME} | approvals: {'terminal' if interactive else 'left pending'}")
    async with shop_mcp:
        report, usage = await team.run_shift(build_task(args.tickets))
        print(json.dumps(report.model_dump(), indent=2))
        print(
            f"\n{usage.requests} model requests, {usage.tool_calls} tool calls, "
            f"{usage.input_tokens} input / {usage.output_tokens} output tokens"
        )
        if interactive:
            await approvals.review_in_terminal(shop_mcp, audit)
        else:
            pending = await call_shop_tool(shop_mcp, "list_proposals", {"status": "pending"})
            print(f"\n{len(pending)} proposal(s) left pending. Approve or reject them with: "
                  ".venv/bin/python -m backend.cli --review")
    print(f"Audit trail: {AUDIT_PATH}\nDrafts:      {OUTPUT_DIR / 'drafts.json'}")


if __name__ == "__main__":
    asyncio.run(main())
