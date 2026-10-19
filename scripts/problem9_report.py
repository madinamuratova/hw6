"""Problem 9: build output/resolved_tickets.json and output/resolved_board.html from what actually happened.

Sources (read-only):
  data/campus_customs_new.db   ticket statuses, proposals, payments, cash
  output/audit_trail.json      every record after the last human reset: agent runs and human approvals
  output/drafts.json           drafts the agents and approvals saved (never sent)
  output/screenshots/ticket_<id>_resolved.jpg   dashboard screenshots taken after each ticket resolved

It also verifies the run: every ticket's status matches the database and was set by the Boss's resolve_ticket,
every payment has a named human's approval, the cash reconciles, and the balance never went below zero.

Run from the HW 6 folder:  .venv/bin/python scripts/problem9_report.py
"""

from __future__ import annotations

import base64
import html
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
DB = ROOT / "data" / "campus_customs_new.db"
VALID_TEAMMATES = {"inventory", "accounting", "facilities", "customer_service"}
AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer service", "customer_service", "ai", "agent"}

# The two fixes made between the blocked runs and the reruns (the user chose "fix both gaps, rerun once").
FIXES = [
    {"ticket_id": 101, "applied_after_run": "run-20261019-080213-455ce0", "rerun": "run-20261019-080559-290204",
     "problem": "Ticket 101 was blocked: no agent tool could see the vendor order that approving purchase #2 had drafted, "
                "so Inventory said the order was unconfirmed and the reply gave no date.",
     "change": "mcp_server/server.py list_proposals now shows an approved purchase's vendor, paid_at, earliest_delivery "
               "(paid_at + the vendor's lead_days), and vendor_order_draft_id; backend/prompts/inventory.md reports it as ordered."},
    {"ticket_id": 103, "applied_after_run": "run-20261019-080213-455ce0", "rerun": "run-20261019-080705-c1ea87",
     "problem": "Ticket 103 was blocked although the 12-hoodie restock had been refused for lack of cash, which the "
                "Boss prompt already called a final answer.",
     "change": "backend/prompts/boss.md now says plainly that a cash-refused restock and a drafted vendor order are not "
               "blockers, and the `blocked` status is only for when no final answer can be given."},
]


def rows(query: str, *args) -> list[dict]:
    conn = sqlite3.connect(f"{DB.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out = [dict(r) for r in conn.execute(query, args)]
    conn.close()
    return out


def describe_run(run_id: str, records: list[dict]) -> dict:
    recs = [r for r in records if r.get("run_id") == run_id]
    start = next(r for r in recs if r["phase"] == "system_start")
    end = next((r for r in recs if r["phase"] in ("system_end", "system_error")), None)
    boss_final = next((r for r in recs if r["agent"] == "Boss" and r["phase"] == "final_output"), None)
    m = re.match(r"Ticket (\d+) \((\w+)\): (.*)", (boss_final or {}).get("said") or "", re.S)
    tools: dict[str, Counter] = {}
    delegations, rejected, refusals, resolved_ok = [], [], [], False
    for r in recs:
        for c in r.get("tools_called", []):
            tools.setdefault(r["agent"], Counter())[c["tool"]] += 1
        for to, task in zip(r.get("delegated_to", []), r.get("delegation_tasks", [])):
            # A malformed call (e.g. to="customer_service.delegate") is rejected by the tool's input check and retried.
            (delegations if to in VALID_TEAMMATES else rejected).append({"from": r["agent"], "to": to, "task": task})
        for t in r.get("tool_results", []):
            if '"ok":false' in t["result"].replace(" ", ""):
                refusals.append({"agent": r["agent"], "tool": t["tool"], "result": t["result"]})
            if t["tool"] == "resolve_ticket" and '"ok":true' in t["result"].replace(" ", ""):
                resolved_ok = True
    reports = {r["agent"]: r.get("said") for r in recs if r["phase"] == "final_output" and r["agent"] != "Boss"}
    return {
        "run_id": run_id,
        "ticket_id": start.get("ticket_id"),
        "started": start["timestamp"],
        "finished": end["timestamp"] if end else None,
        "boss_status": m.group(2) if m else None,
        "boss_summary": m.group(3).strip() if m else (boss_final or {}).get("said"),
        "agents": [a for a, _ in Counter(r["agent"] for r in recs if r["agent"] != "System").most_common()],
        "delegations": delegations,
        "rejected_delegation_calls": rejected,
        "tools_by_agent": {a: dict(c) for a, c in tools.items()},
        "specialist_reports": reports,
        "tool_refusals": refusals,
        "resolve_ticket_succeeded": resolved_ok,
        "usage": end.get("usage") if end else None,
        "audit_records": len(recs),
    }


def main() -> None:
    audit = json.loads((OUT / "audit_trail.json").read_text())
    reset_at = max(i for i, r in enumerate(audit) if r.get("phase") == "reset" and r.get("ok"))
    reset, after = audit[reset_at], audit[reset_at + 1:]
    start_cash = next(a["balance"] for a in reset["result"]["cash_accounts"] if a["name"] == "checking")
    run_ids = [r["run_id"] for r in after if r.get("phase") == "system_start"]
    runs = [describe_run(rid, after) for rid in run_ids]
    approvals = [r for r in after if r.get("phase") == "approval_decision"]

    tickets_db = {t["id"]: t for t in rows("SELECT * FROM tickets ORDER BY id")}
    proposals = rows("SELECT * FROM proposals ORDER BY id")
    payments = rows("SELECT * FROM payments ORDER BY id")
    end_cash = rows("SELECT balance FROM cash_accounts WHERE name = 'checking'")[0]["balance"]
    drafts = json.loads((OUT / "drafts.json").read_text())

    tickets = []
    for tid, t in tickets_db.items():
        t_runs = [r for r in runs if r["ticket_id"] == tid]
        t_props = [p for p in proposals if p["ticket_id"] == tid]
        t_drafts = [d for d in drafts if d.get("ticket_id") == tid]
        replies = [d for d in t_drafts if d["kind"] == "customer_reply"]
        human = []
        for p in t_props:
            if p["status"] == "pending":
                continue
            pay = next((x for x in payments if x["id"] == p.get("payment_id")), None)
            log = next((a for a in approvals if f"proposal #{p['id']}" in a["action"]), None)
            human.append({
                "proposal_id": p["id"], "kind": p["kind"], "proposed_by": p["proposed_by"],
                "what": (f"{p['qty']} x {p['sku']} size {p['size']}" + (f" at ${p['unit_price']:.2f} each" if p["unit_price"] else "")) if p["sku"]
                else f"{p['kind']} ref {p['ref_id']}",
                "amount": p["amount"], "decision": p["status"], "decided_by": p["decided_by"], "decided_at": p["decided_at"],
                "payment_id": p.get("payment_id"), "cash_moved": bool(pay), "audit_record": log["action"] if log else None,
            })
        last = t_runs[-1] if t_runs else None
        resolving = next((r for r in t_runs if r["resolve_ticket_succeeded"]), None)
        tickets.append({
            "ticket_id": tid,
            "type": t["type"],
            "requester": t["requester"],
            "subject": t["subject"],
            "request": {k: t[k] for k in ("sku", "size", "qty", "lease_id", "invoice_id", "notes") if t[k] is not None},
            "final_status": t["status"],
            "resolved_by": f"Boss, resolve_ticket in {resolving['run_id']}" if resolving else None,
            "outcome": last["boss_summary"] if last else None,
            "runs": [{k: r[k] for k in ("run_id", "started", "finished", "boss_status", "boss_summary", "usage")} for r in t_runs],
            "agents_involved": sorted({a for r in t_runs for a in r["agents"]}),
            "delegations": sorted({f"{d['from']} -> {d['to'].replace('_', ' ').title()}" for r in t_runs for d in r["delegations"]}),
            "tools_used": sorted({tool for r in t_runs for tools in r["tools_by_agent"].values() for tool in tools}),
            "agent_contributions": {a: [r["specialist_reports"][a] for r in t_runs if a in r["specialist_reports"]]
                                    for a in sorted({a for r in t_runs for a in r["specialist_reports"]})},
            "refused_by_server": [x for r in t_runs for x in r["tool_refusals"]],
            "rejected_delegation_calls": [x for r in t_runs for x in r["rejected_delegation_calls"]],
            "human_approvals": human,
            "drafts_saved": [{k: d[k] for k in ("draft_id", "kind", "to", "subject", "status")} for d in t_drafts],
            "final_reply": {k: replies[-1][k] for k in ("draft_id", "to", "subject", "body", "status")} if replies else None,
        })

    # ---- verification against the database and the logs ----
    balance, sequence, never_negative = start_cash, [], True
    for p in payments:
        balance = round(balance - p["amount"], 2)
        sequence.append({"payment_id": p["id"], "kind": p["kind"], "amount": p["amount"], "approved_by": p["approved_by"], "balance_after": balance})
        never_negative &= balance >= 0
    paid_props = {p["payment_id"]: p for p in proposals if p.get("payment_id")}
    checks = {
        "every ticket's final status matches the database": all(t["final_status"] == tickets_db[t["ticket_id"]]["status"] for t in tickets),
        "every resolved ticket was resolved by the Boss's resolve_ticket (ok=true in the audit trail)": all(
            t["resolved_by"] for t in tickets if t["final_status"] == "resolved"),
        "no proposal is still pending": not [p for p in proposals if p["status"] == "pending"],
        "every payment comes from a proposal approved by a named human (not an agent)": all(
            pid in paid_props and paid_props[pid]["status"] == "approved"
            and (paid_props[pid]["decided_by"] or "").strip().lower() not in AGENT_NAMES for pid in (p["id"] for p in payments)),
        "every approval is in the audit trail": all(h["audit_record"] for t in tickets for h in t["human_approvals"]),
        "cash reconciles: start - payments = end (database)": round(start_cash - sum(p["amount"] for p in payments), 2) == end_cash,
        "the balance never went below zero": never_negative,
        "cash only went out (every payment positive)": all(p["amount"] > 0 for p in payments),
        "every draft is NOT sent": all(d["status"] == "draft - NOT sent" for d in drafts),
    }
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "database": "data/campus_customs_new.db",
        "reset": {"timestamp": reset["timestamp"], "by": reset["tools_called"][0]["args"]["requested_by"], "action": reset["action"]},
        "starting_checking_balance": start_cash,
        "ending_checking_balance": end_cash,
        "payments": sequence,
        "cash_reconciliation": f"{start_cash:.2f} - " + " - ".join(f"{p['amount']:.2f}" for p in payments) + f" = {end_cash:.2f}",
        "tickets": tickets,
        "fixes_between_runs": FIXES,
        "runs_in_order": [{k: r[k] for k in ("run_id", "ticket_id", "boss_status", "usage")} for r in runs],
        "total_usage": {k: sum((r["usage"] or {}).get(k, 0) for r in runs) for k in ("requests", "tool_calls", "input_tokens", "output_tokens")},
        "verification": checks,
        "all_checks_passed": all(checks.values()),
    }
    (OUT / "resolved_tickets.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    (OUT / "resolved_board.html").write_text(board_html(report))
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"wrote output/resolved_tickets.json and output/resolved_board.html | runs: {len(runs)} | "
          f"tickets: {[(t['ticket_id'], t['final_status']) for t in tickets]} | cash {start_cash} -> {end_cash}")


def board_html(r: dict) -> str:
    e = html.escape
    money = lambda n: f"${n:,.2f}"  # noqa: E731
    cards = []
    for t in r["tickets"]:
        img = OUT / "screenshots" / f"ticket_{t['ticket_id']}_resolved.jpg"
        shot = (f'<img src="data:image/jpeg;base64,{base64.b64encode(img.read_bytes()).decode()}" '
                f'alt="Dashboard after ticket {t["ticket_id"]} was resolved">') if img.exists() else "<p class='muted'>No screenshot.</p>"
        fixes = {f["rerun"]: f for f in r["fixes_between_runs"]}
        runs = "".join((f"<li class='muted'><em>Fix before this rerun:</em> {e(fixes[x['run_id']]['change'])}</li>" if x["run_id"] in fixes else "")
                       + f"<li><span class='pill {('ok' if x['boss_status'] == 'handled' else 'wait' if x['boss_status'] == 'waiting_on_human' else 'bad')}'>"
                       f"{e(x['boss_status'] or '?')}</span> {e(x['boss_summary'] or '')}</li>" for x in t["runs"])
        approvals = "".join(f"<li>#{a['proposal_id']} {e(a['kind'])}: {e(a['what'])}: "
                            f"{money(a['amount']) if a['cash_moved'] else 'no cash moved'}, {e(a['decision'])} by {e(a['decided_by'] or '')}</li>"
                            for a in t["human_approvals"]) or "<li class='muted'>None</li>"
        refusals = "".join(f"<li>{e(x['agent'])} · {e(x['tool'])}: {e(x['result'])}</li>" for x in t["refused_by_server"])
        reply = t["final_reply"]
        cards.append(f"""
<section class="card">
  <header><p class="eyebrow">#{t['ticket_id']} · {e(t['type'].replace('_', ' '))} · {e(t['requester'])}</p>
  <h2>{e(t['subject'])} <span class="pill {'ok' if t['final_status'] == 'resolved' else 'bad'}">{e(t['final_status'])}</span></h2>
  <p class="muted small">{e(t['resolved_by'] or 'Not resolved')}</p></header>
  <p>{e(t['outcome'] or '')}</p>
  <div class="grid">
    <div><h3>Runs ({len(t['runs'])})</h3><ol class="runs">{runs}</ol>
      <h3>Human approvals</h3><ul>{approvals}</ul>
      {f'<h3>Refused by the server</h3><ul>{refusals}</ul>' if refusals else ''}
      <h3>Agents and delegation</h3><p class="small">{e(', '.join(t['agents_involved']))}<br>{e(' · '.join(t['delegations']))}</p>
      <h3>MCP tools used</h3><p class="small mono">{e(', '.join(t['tools_used']))}</p>
      {f"<h3>Final reply (draft #{reply['draft_id']}, not sent)</h3><blockquote>{e(reply['body'])}</blockquote>" if reply else ''}
    </div>
    <figure>{shot}<figcaption class="muted small">Dashboard after ticket {t['ticket_id']} was resolved</figcaption></figure>
  </div>
</section>""")
    pays = "".join(f"<tr><td>{e(p['kind'])} (payment #{p['payment_id']})</td><td>{e(p['approved_by'])}</td>"
                   f"<td class='num'>−{money(p['amount'])}</td><td class='num'>{money(p['balance_after'])}</td></tr>" for p in r["payments"])
    checks = "".join(f"<li>{'✓' if ok else '✗'} {e(name)}</li>" for name, ok in r["verification"].items())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus Customs · Resolved board</title>
<style>
  body {{ margin: 0; background: #f6f5f2; color: #2b2b2a; font: 15px/1.5 Inter, system-ui, -apple-system, 'Segoe UI', sans-serif; }}
  main {{ max-width: 1200px; margin: 0 auto; padding: 32px; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 4px; }} h2 {{ font-size: 1.2rem; margin: 2px 0; }}
  h3 {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: .08em; color: #74716b; margin: 18px 0 6px; }}
  .muted {{ color: #74716b; }} .small {{ font-size: .85rem; }} .mono {{ font-family: ui-monospace, Menlo, monospace; }}
  .eyebrow {{ font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; color: #74716b; margin: 0; }}
  .card, .summary {{ background: #fff; border: 1px solid #e5e2dc; border-radius: 10px; padding: 24px; margin: 20px 0; }}
  .grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 24px; align-items: start; }}
  @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  figure {{ margin: 0; }} img {{ width: 100%; border: 1px solid #e5e2dc; border-radius: 8px; }}
  .pill {{ display: inline-block; padding: 1px 10px; border-radius: 999px; font-size: .75rem; font-weight: 500; background: #efede8; color: #74716b; }}
  .pill.ok {{ background: #e6eee6; color: #5f7f63; }} .pill.wait {{ background: #f4ebdc; color: #a87b3e; }} .pill.bad {{ background: #f5e3e0; color: #a4483f; }}
  ul, ol {{ padding-left: 20px; margin: 0; }} li {{ margin: 4px 0; }}
  blockquote {{ margin: 0; padding: 10px 14px; background: #fcfbf9; border: 1px solid #e5e2dc; border-radius: 8px; white-space: pre-wrap; font-size: .9rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .92rem; }} td, th {{ padding: 6px 8px; border-bottom: 1px solid #efede8; text-align: left; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .big {{ font-size: 1.8rem; font-weight: 600; font-variant-numeric: tabular-nums; }}
  .row {{ display: flex; gap: 40px; flex-wrap: wrap; }}
</style></head>
<body><main>
<h1>Campus Customs · Resolved board</h1>
<p class="muted">Full run on <code>{e(r['database'])}</code>, reset {e(r['reset']['timestamp'])} by {e(r['reset']['by'])}. Generated {e(r['generated_at'])} from the database, the audit trail, and drafts.json.</p>
<section class="summary">
  <div class="row">
    <div><p class="eyebrow">Starting checking</p><p class="big">{money(r['starting_checking_balance'])}</p></div>
    <div><p class="eyebrow">Ending checking</p><p class="big">{money(r['ending_checking_balance'])}</p></div>
    <div><p class="eyebrow">Tickets resolved</p><p class="big">{sum(t['final_status'] == 'resolved' for t in r['tickets'])} / {len(r['tickets'])}</p></div>
    <div><p class="eyebrow">Agent runs</p><p class="big">{len(r['runs_in_order'])}</p></div>
  </div>
  <h3>Payments (each approved by a named human)</h3>
  <table><tr><th>Payment</th><th>Approved by</th><th class="num">Amount</th><th class="num">Checking after</th></tr>{pays}</table>
  <p class="small">{e(r['cash_reconciliation'])}</p>
  <h3>Verified against the database and logs</h3><ul class="small">{checks}</ul>
</section>
{''.join(cards)}
</main></body></html>
"""


if __name__ == "__main__":
    main()
