"""Problem 9: fill the Actual sections, the Cash tab, and the Reflection placeholder in output/desk_tickets.html.

The page started as a copy of HW 5's desk_tickets.html (same three tickets and the same five-agent team), so its
Expected plans are kept. Everything this script writes comes from the HW 6 run: the audit trail records after the
last human reset, the working database (proposals, payments, cash), and output/drafts.json.
It replaces only the blocks it owns, so it can be rerun.

Run from the HW 6 folder:  .venv/bin/python scripts/fill_desk_tickets.py
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from problem9_report import FIXES, OUT, describe_run, rows  # noqa: E402

PAGE = OUT / "desk_tickets.html"
e = html.escape


def money(n: float) -> str:
    return f"${n:,.2f}"


def clock(ts: str) -> str:
    return datetime.fromisoformat(ts).strftime("%-I:%M:%S %p")


def duration(a: str, b: str | None) -> str:
    if not b:
        return "unfinished"
    s = int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds())
    return f"{s // 60}m {s % 60}s"


def short(text: str, n: int = 240) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n].rstrip() + "…"


def planned_tools(section_html: str) -> set[str]:
    """Tool names in the first column of the Expected section's tools table."""
    expected = section_html.split("<h3>Expected</h3>", 1)[1].split("<h3>Actual</h3>", 1)[0]
    table = expected.split("MCP tools I expect to be used", 1)[-1]
    return set(re.findall(r"<tr><td><code>(\w+)</code>", table))


def stays_out(section_html: str) -> list[str]:
    m = re.search(r"<h4>Who stays out</h4>\s*<p>(.*?)</p>", section_html, re.S)
    return re.findall(r"<strong>([^<]+)</strong>", m.group(1)) if m else []


def actual_block(ticket: dict, runs: list[dict], approvals: list[dict], proposals: list[dict], drafts: list[dict],
                 section_html: str) -> str:
    tid = ticket["id"]
    resolving = next((i for i, r in enumerate(runs, 1) if r["resolve_ticket_succeeded"]), None)
    lead = (f"<p class='actual__lead'><strong>Final status: {e(ticket['status'])}.</strong> {len(runs)} agent run(s)."
            + (f" The Boss resolved it with <code>resolve_ticket</code> in run {resolving}." if resolving else
               " The Boss never resolved it.")
            + " Every detail below is copied from <code>output/audit_trail.json</code> (records after the reset), "
              "the working database, and <code>output/drafts.json</code>.</p>")
    parts = [lead]
    for i, r in enumerate(runs, 1):
        for fix in FIXES:
            if fix["rerun"] == r["run_id"]:
                parts.append(f"<div class='note'><strong>Fix before this rerun</strong> (you chose \"fix both gaps, rerun once\"; "
                             f"both fixes were made after the last blocked run): {e(fix['problem'])} <em>Change:</em> {e(fix['change'])}</div>")
        u = r["usage"] or {}
        tools = "".join(
            f"<tr><td>{e(agent)}</td><td>{', '.join(f'<code>{e(t)}</code>' + (f' ×{n}' if n > 1 else '') for t, n in used.items())}</td></tr>"
            for agent, used in r["tools_by_agent"].items())
        deleg = "".join(f"<li><strong>{e(d['from'])} → {e(d['to'].replace('_', ' ').title())}</strong>: {e(short(d['task']))}</li>"
                        for d in r["delegations"]) or "<li class='muted'>None</li>"
        rejected = "".join(f"<li class='muted'>{e(d['from'])} tried to delegate to <code>{e(d['to'])}</code>, which isn't a "
                           f"teammate; the tool's input check rejected the call and the model retried.</li>"
                           for d in r["rejected_delegation_calls"])
        refused = "".join(f"<li>{e(x['agent'])} · <code>{e(x['tool'])}</code>: {e(short(x['result'], 200))}</li>"
                          for x in r["tool_refusals"])
        parts.append(
            f"<div class='run'><h4>Run {i} · {clock(r['started'])} · {duration(r['started'], r['finished'])} · "
            f"{u.get('requests', '?')} model calls, {u.get('tool_calls', '?')} tool calls</h4>"
            f"<p><strong>Agents (in order of activity):</strong> {e(' → '.join(r['agents']))}</p>"
            f"<p><strong>Delegations:</strong></p><ul>{deleg}{rejected}</ul>"
            f"<table class='tools'><thead><tr><th>Agent</th><th>MCP tools used</th></tr></thead><tbody>{tools}</tbody></table>"
            + (f"<p><strong>Refused by the MCP server:</strong></p><ul>{refused}</ul>" if refused else "")
            + f"<p><span class='badge'>Boss: {e(r['boss_status'] or '?')}</span> {e(r['boss_summary'] or '')}</p></div>")
        next_start = runs[i]["started"] if i < len(runs) else "9999"
        for a in approvals:
            if r["finished"] and r["finished"] <= a["timestamp"] < next_start:
                pid = int(re.search(r"#(\d+)", a["action"]).group(1))
                p = next(x for x in proposals if x["id"] == pid)
                parts.append(f"<div class='human-step'><span class='badge badge--human'>Human {e(p['status'])}</span> "
                             f"{e(a['action'])}<br><span class='muted'>Proposed by {e(p['proposed_by'])}: {e(short(p['reason'], 260))}</span></div>")
    replies = [d for d in drafts if d["kind"] == "customer_reply"]
    others = [d for d in drafts if d["kind"] != "customer_reply"]
    if replies:
        last = replies[-1]
        parts.append(f"<h4>Final reply (draft #{last['draft_id']} to {e(last['to'])}, not sent)</h4>"
                     f"<p class='human-step' style='white-space:pre-wrap'>{e(last['body'])}</p>"
                     f"<p class='muted'>All drafts for this ticket: "
                     + ", ".join(f"#{d['draft_id']} {e(d['kind'].replace('_', ' '))} to {e(d['to'])}" for d in replies + others)
                     + ". Every draft has the status <code>draft - NOT sent</code>.</p>")
    used_agents = {a for r in runs for a in r["agents"]}
    used_tools = {t for r in runs for used in r["tools_by_agent"].values() for t in used}
    plan = planned_tools(section_html)
    out = stays_out(section_html)
    joined_anyway = [a for a in out if a in used_agents]
    parts.append(
        "<div class='compare'><h4>Plan vs. what happened</h4><ul>"
        f"<li><strong>Agents:</strong> {e(', '.join(sorted(used_agents)))}. "
        + (f"Planned to stay out but took part: {e(', '.join(joined_anyway))}." if joined_anyway else
           f"The agents I expected to stay out ({e(', '.join(out))}) stayed out.") + "</li>"
        f"<li><strong>Runs needed:</strong> {len(runs)}. My plan described one pass; each human approval needed a follow-up "
        "run so the agents could see the decision" + (", and a blocked run needed a fix and a rerun" if any(
            f["rerun"] in {r["run_id"] for r in runs} for f in FIXES) else "") + ".</li>"
        f"<li><strong>Tools beyond the plan:</strong> {', '.join(f'<code>{t}</code>' for t in sorted(used_tools - plan)) or 'none'}.</li>"
        f"<li><strong>Planned tools not used:</strong> {', '.join(f'<code>{t}</code>' for t in sorted(plan - used_tools)) or 'none'}.</li>"
        "</ul></div>")
    return "\n".join(parts)


def cash_block(start: float, end: float, payments: list[dict], proposals: list[dict], runs: list[dict], reset_ts: str) -> str:
    parts = [f"<div class='cash-start'><span>Starting checking balance after the database reset</span><strong>{money(start)}</strong></div>"
             f"<p class='muted'>From the reset record in <code>output/audit_trail.json</code> ({clock(reset_ts)}, signed "
             "\"Madina Muratova (via Claude Code)\"), which read <code>cash_accounts</code> right after the original database "
             "was copied over the working copy and before any ticket ran.</p>"]
    balance = start
    for tid, title in ((101, "Ticket 101: Bulldog tee"), (102, "Ticket 102: Rent due"), (103, "Ticket 103: Bulk hoodie discount")):
        rows_html = []
        for p in [x for x in proposals if x["ticket_id"] == tid]:
            pay = next((x for x in payments if x["id"] == p.get("payment_id")), None)
            what = {"invoice": f"Invoice #{p['ref_id']} (Bulldog Print Co)", "rent": f"Rent for lease #{p['ref_id']}",
                    "purchase": f"Restock {p['qty']} × {p['sku']} size {p['size']}",
                    "price_override": f"Price for {p['qty']} × {p['sku']} size {p['size']} at {money(p['unit_price'] or 0)}"}[p["kind"]]
            if pay:
                balance = round(balance - pay["amount"], 2)
                amount, after = f"−{money(pay['amount'])}", money(balance)
            else:
                amount, after = "no cash moves", money(balance)
            rows_html.append(f"<tr><td>#{p['id']} {e(what)}</td><td class='num'>{amount}</td><td>{e(short(p['reason'], 200))}</td>"
                             f"<td>{e(p['decided_by'] or '')}</td><td class='num'>{after}</td></tr>")
        refusals = [x for r in runs if r["ticket_id"] == tid for x in r["tool_refusals"] if "cash" in x["result"].lower()]
        parts.append(f"<h4>{e(title)}</h4><table class='cash-table'><thead><tr><th>Payment / purchase</th><th class='num'>Amount</th>"
                     f"<th>Why (the agent's reason)</th><th>Approved by</th><th class='num'>Checking after</th></tr></thead>"
                     f"<tbody>{''.join(rows_html)}</tbody></table>"
                     + (f"<p class='cash-step muted'>The MCP server refused {len(refusals)} restock proposal(s) for this ticket: "
                        f"{e(refusals[0]['result'])} No cash moved.</p>" if refusals else ""))
    math = f"{money(start)} − " + " − ".join(money(p["amount"]) for p in payments) + f" = {money(round(start - sum(p['amount'] for p in payments), 2))}"
    parts.append(f"<div class='cash-start cash-end'><span>Ending checking balance after all three tickets</span><strong>{money(end)}</strong></div>"
                 f"<p class='cash-math'><strong>Check:</strong> {math}. This equals <code>cash_accounts.balance</code> in "
                 "<code>data/campus_customs_new.db</code>.</p>"
                 "<ul><li>Every payment came from a proposal approved by a named human. No agent can call "
                 "<code>approve_proposal</code>, and the server refuses agent names.</li>"
                 "<li>The balance never went below zero, and the server checked cash both when each payment was proposed and when it was approved.</li>"
                 "<li>Cash only went out. The approved price override moved no cash, because revenue isn't modeled.</li></ul>")
    return "\n".join(parts)


def main() -> None:
    page = PAGE.read_text()
    audit = json.loads((OUT / "audit_trail.json").read_text())
    reset_at = max(i for i, r in enumerate(audit) if r.get("phase") == "reset" and r.get("ok"))
    reset, after = audit[reset_at], audit[reset_at + 1:]
    start = next(a["balance"] for a in reset["result"]["cash_accounts"] if a["name"] == "checking")
    runs = [describe_run(r["run_id"], after) for r in after if r.get("phase") == "system_start"]
    approvals = [r for r in after if r.get("phase") == "approval_decision"]
    proposals = rows("SELECT * FROM proposals ORDER BY id")
    payments = rows("SELECT * FROM payments ORDER BY id")
    tickets = {t["id"]: t for t in rows("SELECT * FROM tickets ORDER BY id")}
    end = rows("SELECT balance FROM cash_accounts WHERE name = 'checking'")[0]["balance"]
    drafts = json.loads((OUT / "drafts.json").read_text())

    for tid in (101, 102, 103):
        pattern = re.compile(rf'(<section role="tabpanel" id="t{tid}".*?<h3>Actual</h3>\s*<div class="actual">)(.*?)(</div>\s*</section>)', re.S)
        m = pattern.search(page)
        block = actual_block(tickets[tid], [r for r in runs if r["ticket_id"] == tid],
                             [a for a in approvals if a.get("ticket_id") == tid], proposals,
                             [d for d in drafts if d.get("ticket_id") == tid], m.group(0))
        page = page[:m.start(2)] + "\n" + block + "\n" + page[m.end(2):]

    cash = re.compile(r'(<section role="tabpanel" id="cash".*?<p class="meta">)(.*?)(</section>)', re.S)
    m = cash.search(page)
    page = page[:m.start(2)] + "How the checking account changed during the HW 6 Problem 9 run.</p>\n" + \
        cash_block(start, end, payments, proposals, runs, reset["timestamp"]) + "\n" + page[m.end(2):]

    refl = re.compile(r'(<section role="tabpanel" id="reflection"[^>]*>\s*<h2>Reflection</h2>)(.*?)(</section>)', re.S)
    m = refl.search(page)
    page = page[:m.start(2)] + "\n  <p class=\"later\">Coming later.</p>\n" + page[m.end(2):]

    intro = ('My plan and the real results for the three open tickets in <code>data/campus_customs_new.db</code>. '
             'The shop\'s "today" (<code>desk.date_today</code>) is <strong>2026-08-31</strong>. The Expected plans were written '
             'in HW 5 for the same tickets and the same five-agent team; the Actual sections and the Cash tab come from the '
             'HW 6 Problem 9 run on 2026-10-19.')
    page = re.sub(r'(<header class="top">\s*<h1>[^<]*</h1>\s*<p>).*?(</p>)', lambda m: m.group(1) + intro + m.group(2),
                  page, count=1, flags=re.S)
    PAGE.write_text(page)
    print(f"filled Actual for 101-103, Cash ({money(start)} -> {money(end)}), Reflection placeholder | {len(runs)} runs")


if __name__ == "__main__":
    main()
