"""Ticket 102 re-run test: does the team resolve the rent notice once a human has paid the rent?

Each trial uses a fresh scratch copy of data/campus_customs.db (never data/campus_customs_new.db), with its own
drafts and audit files:
  1. run the agent team on ticket 102        -> expect a pending rent proposal
  2. a test approver approves it through backend/approvals.py (the human step)
                                               -> rent paid, lease next_due moves forward a month
  3. run the agent team on ticket 102 again  -> expect the Boss to resolve it, with no second rent proposal

Run from the HW 6 folder:  .venv/bin/python scripts/rent_rerun_test.py [--trials N] [--label NAME]
Appends one entry per call to output/rent_rerun_test.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import approvals  # noqa: E402
from backend.audit import AuditTrail  # noqa: E402
from backend.config import build_model  # noqa: E402
from backend.shop_mcp import call_shop_tool, load_shop_mcp  # noqa: E402
from backend.team import Team, usage_dict  # noqa: E402

TEST_APPROVER = "Test Approver (scratch copy)"
TASK = "Handle ticket 102 only."  # the same task the dashboard API sends


def rows(db: Path, query: str) -> list[dict]:
    conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out = [dict(r) for r in conn.execute(query)]
    conn.close()
    return out


def outcome(report, ticket_id: int = 102) -> dict | None:
    entry = next((t for t in report.tickets if t.ticket_id == ticket_id), None)
    return entry.model_dump() if entry else None


async def trial(n: int) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="rent_rerun_"))
    db = tmp / "db.sqlite"
    shutil.copyfile(ROOT / "data" / "campus_customs.db", db)
    os.environ.update(CAMPUS_CUSTOMS_DB=str(db), CAMPUS_CUSTOMS_DRAFTS=str(tmp / "drafts.json"))
    audit = AuditTrail(tmp / "audit.json")
    shop = load_shop_mcp()
    result: dict = {"trial": n}
    try:
        async with shop:
            first, usage1 = await Team(model=build_model(), shop_mcp=shop, audit=audit, ticket_id=102).run_shift(TASK)
            pending = await call_shop_tool(shop, "list_proposals", {"status": "pending"})
            rent = [p for p in pending if p["kind"] == "rent" and p["ticket_id"] == 102]
            result["run1"] = {"outcome": outcome(first), "usage": usage_dict(usage1),
                              "pending_rent_proposals": [p["id"] for p in rent]}
            if len(rent) != 1:
                result["error"] = f"expected one pending rent proposal after run 1, found {len(rent)}"
                return result
            result["approval"] = await approvals.approve(shop, audit, rent[0]["id"], TEST_APPROVER)
            result["after_approval"] = await call_shop_tool(shop, "get_rent_and_cash", {"lease_id": 1})

            second, usage2 = await Team(model=build_model(), shop_mcp=shop, audit=audit, ticket_id=102).run_shift(TASK)
            result["run2"] = {"outcome": outcome(second), "usage": usage_dict(usage2)}

        proposals = rows(db, "SELECT id, kind, status, amount FROM proposals ORDER BY id")
        ticket = rows(db, "SELECT status FROM tickets WHERE id = 102")[0]["status"]
        cash = rows(db, "SELECT balance FROM cash_accounts WHERE name = 'checking'")[0]["balance"]
        drafts = [d for d in json.loads((tmp / "drafts.json").read_text())] if (tmp / "drafts.json").exists() else []
        result.update(
            ticket_status_after=ticket,
            checking_after=cash,
            rent_proposals_total=sum(p["kind"] == "rent" for p in proposals),
            last_landlord_draft=drafts[-1]["body"] if drafts else None,
        )
        result["passed"] = (ticket == "resolved" and result["rent_proposals_total"] == 1 and cash == 1000.0)
    except Exception as exc:  # report it rather than crash the other trials
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["passed"] = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"trial {n}: run1={(result.get('run1') or {}).get('outcome', {}) and result['run1']['outcome']['status']} "
          f"run2={(result.get('run2') or {}).get('outcome', {}) and result['run2']['outcome']['status']} "
          f"ticket={result.get('ticket_status_after')} cash={result.get('checking_after')} "
          f"rent_proposals={result.get('rent_proposals_total')} passed={result.get('passed')} {result.get('error', '')}",
          flush=True)
    return result


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--label", default="run", help="e.g. 'before fix' or 'after fix'")
    args = parser.parse_args()
    trials = [await trial(i) for i in range(1, args.trials + 1)]
    out = ROOT / "output" / "rent_rerun_test.json"
    history = json.loads(out.read_text()) if out.exists() else []
    history.append({"label": args.label, "passed": sum(t.get("passed", False) for t in trials), "trials": trials})
    out.write_text(json.dumps(history, indent=2, default=str) + "\n")
    print(f"{args.label}: {history[-1]['passed']}/{len(trials)} passed | appended to output/rent_rerun_test.json")


if __name__ == "__main__":
    asyncio.run(main())
