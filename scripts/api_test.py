"""Problem 8: test the dashboard API routes (backend/main.py) without the real model.

Everything runs on scratch copies: the database (copied from data/campus_customs.db), drafts.json,
and the audit trail. The agent run uses PydanticAI's TestModel (no API calls, no tools), which is
enough to test the run lifecycle: start, refuse a second run, finish, and log events. Proposals are
created through the real MCP tools, then approved or rejected through the API like the dashboard does.

Run from the HW 6 folder:  .venv/bin/python scripts/api_test.py
Writes output/api_test.json.
"""

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = Path(tempfile.mkdtemp(prefix="campus_api_test_"))
shutil.copyfile(ROOT / "data" / "campus_customs.db", SCRATCH / "db.sqlite")
# Set before importing the backend: config.py and the MCP server read these at start-up.
os.environ.update(CAMPUS_CUSTOMS_DB=str(SCRATCH / "db.sqlite"), CAMPUS_CUSTOMS_DRAFTS=str(SCRATCH / "drafts.json"),
                  CAMPUS_CUSTOMS_AUDIT=str(SCRATCH / "audit.json"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402

from backend.main import app  # noqa: E402
from backend.shop_mcp import call_shop_tool  # noqa: E402

HUMAN = "Test Approver (scratch copy)"
results = []


def check(name: str, passed: bool, **details) -> None:
    results.append({"check": name, "passed": bool(passed), **details})
    print(f"  {'PASS' if passed else 'FAIL'}  {name}", flush=True)


def main() -> None:
    app.state.model_factory = lambda: TestModel(call_tools=[])  # no real model calls in this test
    with TestClient(app) as client:
        mcp = lambda name, args: client.portal.call(call_shop_tool, app.state.shop_mcp, name, args)  # noqa: E731

        r = client.get("/api/health")
        check("GET /api/health", r.status_code == 200 and r.json()["ok"], body=r.json())

        tickets = client.get("/api/tickets").json()
        check("GET /api/tickets lists 101-103 as open, nothing pending",
              [(t["id"], t["status"], t["pending_proposal_ids"]) for t in tickets] ==
              [(101, "open", []), (102, "open", []), (103, "open", [])], tickets=tickets)
        r = client.get("/api/tickets/999")
        check("GET /api/tickets/999 -> 404", r.status_code == 404, body=r.json())

        cash = client.get("/api/cash").json()
        check("GET /api/cash: checking 3400, today 2026-08-31, nothing pending",
              cash["balance"] == 3400.0 and cash["today"] == "2026-08-31" and cash["pending_total"] == 0, body=cash)

        cors = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        check("CORS allows the Vite dev server", cors.headers.get("access-control-allow-origin") == "http://localhost:5173")

        # Run lifecycle (TestModel, no tools)
        start = client.post("/api/tickets/102/run")
        second = client.post("/api/tickets/101/run")
        run_id = start.json().get("run_id")
        for _ in range(100):
            info = client.get(f"/api/runs/{run_id}").json()
            if info["status"] != "running":
                break
            time.sleep(0.1)
        events = client.get("/api/events", params={"ticket_id": 102}).json()["events"]
        check("POST /api/tickets/102/run -> 202 with a run_id", start.status_code == 202 and run_id, body=start.json())
        check("a second run while one is going -> 409", second.status_code == 409, body=second.json())
        check("the run finishes and reports back", info["status"] == "finished" and info["report"] is not None,
              status=info["status"], error=info.get("error"))
        check("GET /api/events?ticket_id=102 returns that run's steps",
              bool(events) and all(e["run_id"] == run_id for e in events), events=len(events))
        r = client.get("/api/runs/nope")
        check("GET /api/runs/<unknown> -> 404", r.status_code == 404)

        # Approvals: proposals made through the MCP tools, decided through the API
        rent = mcp("propose_payment", {"kind": "rent", "ref_id": 1, "amount": 2400, "account": "checking",
                                       "reason": "test", "proposed_by": "accounting", "ticket_id": 102})
        inv = mcp("propose_payment", {"kind": "invoice", "ref_id": 501, "amount": 840, "account": "checking",
                                      "reason": "test", "proposed_by": "accounting", "ticket_id": 101})
        pending = client.get("/api/approvals").json()
        t102 = next(t for t in client.get("/api/tickets").json() if t["id"] == 102)
        check("GET /api/approvals and /api/tickets show the pending proposals",
              [p["id"] for p in pending] == [rent["proposal_id"], inv["proposal_id"]]
              and t102["pending_proposal_ids"] == [rent["proposal_id"]])
        cash = client.get("/api/cash").json()
        check("pending proposals don't move cash", cash["balance"] == 3400.0 and cash["pending_total"] == 3240.0, body=cash)

        r = client.post(f"/api/approvals/{rent['proposal_id']}/approve", json={"approved_by": ""})
        check("approve with an empty name -> 422", r.status_code == 422)
        r = client.post(f"/api/approvals/{rent['proposal_id']}/approve", json={"approved_by": "accounting"})
        check("approve signed with an agent name -> 409", r.status_code == 409, body=r.json())
        r = client.post("/api/tickets/102/resolve", json={"resolved_by": HUMAN})
        check("resolve while a proposal is pending -> 409", r.status_code == 409, body=r.json())
        r = client.post(f"/api/approvals/{rent['proposal_id']}/approve", json={"approved_by": HUMAN})
        check("approve rent -> paid, checking 3400 -> 1000", r.status_code == 200 and r.json()["new_balance"] == 1000.0,
              body=r.json())
        r = client.post(f"/api/approvals/{rent['proposal_id']}/approve", json={"approved_by": HUMAN})
        check("approving the same proposal twice -> 409", r.status_code == 409, body=r.json())
        r = client.post(f"/api/approvals/{inv['proposal_id']}/reject", json={"rejected_by": HUMAN, "note": "test"})
        check("reject the invoice -> no cash moves", r.status_code == 200 and client.get("/api/cash").json()["balance"] == 1000.0)
        r = client.post("/api/approvals/999/approve", json={"approved_by": HUMAN})
        check("approve an unknown proposal -> 404", r.status_code == 404, body=r.json())

        # Not enough cash: two rent proposals can't both be paid from 1000
        again = mcp("propose_payment", {"kind": "invoice", "ref_id": 501, "amount": 840, "account": "checking",
                                        "reason": "test", "proposed_by": "accounting", "ticket_id": 101})
        mcp("propose_purchase", {"vendor_id": 2, "sku": "CC-MUG-CREST", "size": "OS", "qty": 50,
                                 "reason": "test", "proposed_by": "inventory"})  # 50 x 3.50 = 175
        ok = client.post(f"/api/approvals/{again['proposal_id']}/approve", json={"approved_by": HUMAN})
        mug = next(p for p in client.get("/api/approvals").json() if p["kind"] == "purchase")
        short = client.post(f"/api/approvals/{mug['id']}/approve", json={"approved_by": HUMAN})
        check("approval refused when cash is short (160 left, purchase needs 175) -> 409",
              ok.status_code == 200 and ok.json()["new_balance"] == 160.0 and short.status_code == 409
              and "Not enough cash" in short.json()["detail"], refused=short.json())

        # Drafts
        mcp("draft_customer_reply", {"ticket_id": 101, "subject": "Your tee", "body": "Hi Tauhid, thanks for your order."})
        d101 = client.get("/api/drafts", params={"ticket_id": 101}).json()
        check("GET /api/drafts?ticket_id=101 returns the saved draft (NOT sent)",
              len(d101) == 1 and d101[0]["status"] == "draft - NOT sent", drafts=d101)

        # Reset
        r = client.post("/api/reset", json={"requested_by": ""})
        check("reset without a name -> 422", r.status_code == 422)
        r = client.post("/api/reset", json={"requested_by": HUMAN})
        cash = client.get("/api/cash").json()
        check("reset restores checking 3400 and 3 open tickets",
              r.status_code == 200 and cash["balance"] == 3400.0 and r.json()["open_tickets"] == 3, body=r.json())

    out = ROOT / "output" / "api_test.json"
    out.write_text(json.dumps({"all_passed": all(c["passed"] for c in results), "checks": results}, indent=2, default=str) + "\n")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    print(f"all passed: {all(c['passed'] for c in results)} ({sum(c['passed'] for c in results)}/{len(results)}) | wrote output/api_test.json")


if __name__ == "__main__":
    main()
