"""FastAPI backend for the Campus Customs dashboard (HW 6, Problem 8; adapted from HW 5).

Start it from the HW 6 folder:
    .venv/bin/uvicorn backend.main:app --reload --port 8000
(or from backend/ with the venv active: uvicorn main:app --reload --port 8000)

All shop data goes through the campus-customs MCP server, which only works on
data/campus_customs_new.db (reset only READS data/campus_customs.db). Agents can
only propose payments and purchases; POST /api/approvals/{id}/approve is the
only thing that moves cash. The terminal runner lives in backend/cli.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

# `uvicorn main:app` runs this file from inside backend/, so make the project root importable.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncio  # noqa: E402
import os  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
import json  # noqa: E402
from datetime import datetime  # noqa: E402
from typing import Any, Literal  # noqa: E402

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend import approvals  # noqa: E402
from backend.audit import AuditTrail  # noqa: E402
from backend.config import AUDIT_PATH, DRAFTS_PATH, MODEL_NAME, WORKING_DB_LABEL, build_model  # noqa: E402
from backend.models import ApproveRequest, RejectRequest, ResetRequest, ResolveRequest, RunInfo  # noqa: E402
from backend.shop_mcp import call_shop_tool, load_shop_mcp  # noqa: E402
from backend.team import Team, new_run_id, usage_dict  # noqa: E402


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.shop_mcp = load_shop_mcp()
    app.state.audit = AuditTrail(AUDIT_PATH)
    app.state.runs = {}  # run_id -> RunInfo (this server session only)
    app.state.active_run = None  # one agent run at a time, so cash checks don't race
    app.state.tasks = set()
    if not hasattr(app.state, "model_factory"):  # tests may swap in a scripted model
        app.state.model_factory = build_model
    async with app.state.shop_mcp:  # keep the MCP server running for the app's lifetime
        yield


app = FastAPI(title="Campus Customs API", lifespan=lifespan)
# The React dashboard (Vite dev server, usually http://localhost:5173) calls this API from the browser.
# Add more origins with FRONTEND_ORIGINS="http://host:port,http://other:port".
FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"] + [
    o.strip() for o in os.environ.get("FRONTEND_ORIGINS", "").split(",") if o.strip()
]
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_methods=["*"], allow_headers=["*"])


async def _tool(name: str, args: dict[str, Any] | None = None) -> Any:
    try:
        return await call_shop_tool(app.state.shop_mcp, name, args)
    except Exception as exc:
        raise HTTPException(502, f"MCP tool {name} failed: {exc}") from exc


def _refused(result: dict) -> HTTPException:
    reason = result.get("reason", "Refused")
    return HTTPException(404 if "does not exist" in reason else 409, reason)


# --- Health ----------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "model": MODEL_NAME, "database": WORKING_DB_LABEL, "active_run": app.state.active_run}


# --- Tickets ---------------------------------------------------------------------


@app.get("/api/tickets")
async def list_tickets() -> list[dict]:
    """All tickets with status open/resolved, pending proposals, and the latest dashboard run."""
    tickets = await _tool("list_tickets")
    pending = await _tool("list_proposals", {"status": "pending"})
    runs = sorted(app.state.runs.values(), key=lambda r: r.started_at)
    records = app.state.audit.read()
    for t in tickets:
        t["pending_proposal_ids"] = [p["id"] for p in pending if p["ticket_id"] == t["id"]]
        last = [r for r in runs if r.ticket_id == t["id"]]
        if last:
            t["last_run"] = last[-1].model_dump(include={"run_id", "status", "started_at", "finished_at"})
        else:  # e.g. after a server restart: recover the latest run for this ticket from the audit trail
            t["last_run"] = _last_run_from_audit(records, t["id"])
    return tickets


def _last_run_from_audit(records: list[dict], ticket_id: int) -> dict | None:
    # Runs from before the latest successful reset belong to an earlier "day" and don't count.
    resets = [i for i, r in enumerate(records) if r.get("phase") == "reset" and r.get("ok")]
    after = resets[-1] + 1 if resets else 0
    starts = [r for r in records[after:] if r.get("ticket_id") == ticket_id and r.get("phase") == "system_start"]
    if not starts:
        return None
    run_id = starts[-1]["run_id"]
    end = next((r for r in records if r.get("run_id") == run_id and r.get("phase") in ("system_end", "system_error")), None)
    status = "finished" if end and end["phase"] == "system_end" else "failed" if end else "unknown"
    return {"run_id": run_id, "status": status, "started_at": starts[-1]["timestamp"], "finished_at": end["timestamp"] if end else None}


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: int) -> dict:
    ticket = await _tool("get_ticket", {"ticket_id": ticket_id})
    if not ticket:
        raise HTTPException(404, f"Ticket {ticket_id} does not exist.")
    return ticket


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int) -> RunInfo:
    """Start the agent team on one ticket in the background; poll /api/runs/{run_id} and /api/events."""
    ticket = await _tool("get_ticket", {"ticket_id": ticket_id})
    if not ticket:
        raise HTTPException(404, f"Ticket {ticket_id} does not exist.")
    if ticket["status"] != "open":
        raise HTTPException(409, f"Ticket {ticket_id} is {ticket['status']}. Reset the database to run it again.")
    if app.state.active_run:
        raise HTTPException(409, f"Run {app.state.active_run} is still going. Wait for it to finish.")

    info = RunInfo(run_id=new_run_id(), ticket_id=ticket_id, status="running", started_at=_now())
    app.state.runs[info.run_id] = info
    app.state.active_run = info.run_id
    task = asyncio.create_task(_run_ticket(info))
    app.state.tasks.add(task)  # keep a reference so the task isn't garbage-collected
    task.add_done_callback(app.state.tasks.discard)
    return info


@app.post("/api/tickets/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: int, body: ResolveRequest) -> dict:
    """A human marks a ticket resolved. The MCP server refuses while any proposal for it is pending."""
    if app.state.active_run:
        raise HTTPException(409, f"Run {app.state.active_run} is still going. Resolve after it finishes.")
    result = await approvals.resolve(app.state.shop_mcp, app.state.audit, ticket_id, body.resolved_by.strip(), body.resolution)
    if not result.get("ok"):
        raise _refused(result)
    return result


async def _run_ticket(info: RunInfo) -> None:
    try:
        team = Team(
            model=app.state.model_factory(),
            shop_mcp=app.state.shop_mcp,
            audit=app.state.audit,
            run_id=info.run_id,
            ticket_id=info.ticket_id,
        )
        report, usage = await team.run_shift(f"Handle ticket {info.ticket_id} only.")
        info.status, info.report, info.usage = "finished", report.model_dump(), usage_dict(usage)
    except Exception as exc:
        info.status, info.error = "failed", f"{type(exc).__name__}: {exc}"
    finally:
        info.finished_at = _now()
        app.state.active_run = None


@app.get("/api/runs")
async def list_runs() -> list[RunInfo]:
    return sorted(app.state.runs.values(), key=lambda r: r.started_at, reverse=True)


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> RunInfo:
    if run_id not in app.state.runs:
        raise HTTPException(404, f"Run {run_id} not found (runs are kept until the server restarts).")
    return app.state.runs[run_id]


# --- Agent events (audit trail) ---------------------------------------------------


@app.get("/api/events")
async def events(
    since: int | None = Query(None, ge=0, description="Return events with id >= since (use next_since from the last call)"),
    limit: int = Query(50, ge=1, le=500),
    run_id: str | None = None,
    ticket_id: int | None = None,
) -> dict:
    """Recent agent events: who acted, what they said, which tools they used, and delegations."""
    records = app.state.audit.read()
    items = [{"id": i, **r} for i, r in enumerate(records)]
    if run_id:
        items = [e for e in items if e.get("run_id") == run_id]
    if ticket_id is not None:
        items = [e for e in items if e.get("ticket_id") == ticket_id]
    items = [e for e in items if e["id"] >= since][:limit] if since is not None else items[-limit:]
    return {"events": items, "next_since": len(records), "active_run": app.state.active_run}


# --- Approvals (the only path that moves cash) -------------------------------------


@app.get("/api/approvals")
async def list_approvals(status: Literal["pending", "approved", "rejected", "all"] = "pending") -> list[dict]:
    return await _tool("list_proposals", {"status": None if status == "all" else status})


@app.post("/api/approvals/{proposal_id}/approve")
async def approve(proposal_id: int, body: ApproveRequest) -> dict:
    """A human approved a proposed payment/purchase. The MCP server re-checks cash and rules, then pays."""
    result = await approvals.approve(app.state.shop_mcp, app.state.audit, proposal_id, body.approved_by.strip())
    if not result.get("ok"):
        raise _refused(result)
    return result


@app.post("/api/approvals/{proposal_id}/reject")
async def reject(proposal_id: int, body: RejectRequest) -> dict:
    result = await approvals.reject(app.state.shop_mcp, app.state.audit, proposal_id, body.rejected_by.strip(), body.note)
    if not result.get("ok"):
        raise _refused(result)
    return result


# --- Drafts (saved by the MCP draft tools; never sent) -----------------------------


@app.get("/api/drafts")
async def drafts(ticket_id: int | None = None) -> list[dict]:
    """Replies and vendor orders the agents saved as drafts, newest first."""
    try:
        saved = json.loads(DRAFTS_PATH.read_text()) if DRAFTS_PATH.exists() else []
    except json.JSONDecodeError as exc:
        raise HTTPException(500, f"{DRAFTS_PATH.name} is not valid JSON: {exc}") from exc
    if ticket_id is not None:
        saved = [d for d in saved if d.get("ticket_id") == ticket_id]
    return list(reversed(saved))


# --- Cash --------------------------------------------------------------------------


@app.get("/api/cash")
async def cash() -> dict:
    data = await _tool("get_cash_and_payments")
    checking = next((a for a in data["cash_accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(404, "No 'checking' row in cash_accounts.")
    pending = await _tool("list_proposals", {"status": "pending"})
    pending_total = round(sum(p["amount"] for p in pending if p["account"] == "checking"), 2)
    return {
        "account": "checking",
        "balance": checking["balance"],
        "as_of": checking["date"],
        "today": data["today"],
        "pending_total": pending_total,
        "balance_if_all_pending_approved": round(checking["balance"] - pending_total, 2),
        "recent_payments": data["payments"],
    }


# --- Reset -------------------------------------------------------------------------


@app.post("/api/reset")
async def reset(body: ResetRequest) -> dict:
    """A human copies data/campus_customs.db over data/campus_customs_new.db for a clean test run."""
    if app.state.active_run:
        raise HTTPException(409, f"Run {app.state.active_run} is still going. Reset after it finishes.")
    result = await approvals.reset(app.state.shop_mcp, app.state.audit, body.requested_by.strip())
    if not result.get("ok"):
        raise _refused(result)
    app.state.runs.clear()  # a clean start: earlier runs no longer count as a ticket's latest run
    return {**result, "tickets": await _tool("list_tickets")}
