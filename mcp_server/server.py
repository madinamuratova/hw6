"""Campus Customs MCP server — HW 6, Problem 7 (copied from HW 5).

Tools for the agent team: tickets, shop date, stock, pricing, invoices, vendors,
cash, proposals, and draft-only messages. Agents only PROPOSE payments and
purchases. Cash changes only in approve_proposal, which needs the human key that
the backend gives its own copy of this server (backend/shop_mcp.py) and never
shows to agents. Reset copies the original database over the working one.

All shop data comes from ../data/campus_customs_new.db. Read tools open the
database read-only. ../data/campus_customs.db is only ever read (by reset).
Drafts are saved to ../output/drafts.json and are never sent.

Run from this folder (stdio):  python server.py
Run (HTTP):                    python server.py --http
HTTP URL:                      http://127.0.0.1:8001/mcp
"""

from __future__ import annotations

import argparse
import calendar
import hmac
import json
import os
import re
import shutil
import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# Env overrides exist only so tests can point at scratch copies.
DB_PATH = Path(os.environ.get("CAMPUS_CUSTOMS_DB", ROOT / "data" / "campus_customs_new.db"))
DRAFTS_PATH = Path(os.environ.get("CAMPUS_CUSTOMS_DRAFTS", ROOT / "output" / "drafts.json"))
ORIGINAL_DB_PATH = ROOT / "data" / "campus_customs.db"  # read-only source for reset

# Human-only tools (approve, reject, reset) need this key. The backend
# creates a random key at startup and passes it only to its own copy of this
# server; agents never see it. Without a key, those tools are switched off.
HUMAN_KEY = os.environ.get("CAMPUS_CUSTOMS_HUMAN_KEY", "")

# Names that can never count as a human approver for a payment.
NOT_HUMAN_APPROVERS = {
    "", "pending", "pending_human", "none", "n/a", "unknown", "system", "ai", "agent", "assistant",
    "boss", "inventory", "accounting", "facilities", "customer service", "customer_service",
}

mcp = FastMCP("campus-customs")
_drafts_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    """Open the database read-only so no tool can change it."""
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@mcp.tool
def check_stock(sku: str, size: str | None = None) -> list[dict]:
    """Show how many units of a product are on the shelf, by size.

    Reads the inventory table. Pass a SKU such as "CC-TEE-WHITE" and,
    optionally, a size such as "S". Leave size out to see every size.
    A qty of 0 means the size exists but is out of stock; an empty list
    means no product matches that SKU/size.
    """
    query = "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ?"
    params = [sku.strip().upper()]
    if size:
        query += " AND size = ?"
        params.append(size.strip().upper())
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@mcp.tool
def get_rent_and_cash(lease_id: int) -> dict:
    """Show a lease's rent and due date next to the shop's cash on hand, plus the rent already paid.

    Reads the leases, cash_accounts, and desk tables, and (once rent has been
    approved) the proposals and payments tables. Returns the lease (None if the
    id doesn't exist), every cash account balance, the shop's current date, and
    rent_payments: each human-approved rent payment for this lease with the
    covered_due_date it paid. Paying rent moves next_due forward a month, so a
    rent notice whose due date equals a covered_due_date is already paid.
    """
    with _connect() as conn:
        lease = conn.execute(
            """
            SELECT id, space_name, landlord, monthly_rent, next_due, notes
            FROM leases
            WHERE id = ?
            """,
            (lease_id,),
        ).fetchone()
        accounts = conn.execute(
            "SELECT name, balance, date FROM cash_accounts ORDER BY name"
        ).fetchall()
        desk = conn.execute("SELECT date_today FROM desk").fetchone()
        rent_payments = []
        if _has_proposals_table(conn):
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(proposals)")}
            covered = "p.covers_due" if "covers_due" in columns else "NULL"
            rent_payments = conn.execute(
                f"""
                SELECT pay.id AS payment_id, pay.amount, pay.paid_at, pay.approved_by, {covered} AS covered_due_date
                FROM proposals p JOIN payments pay ON pay.id = p.payment_id
                WHERE p.kind = 'rent' AND p.ref_id = ? AND p.status = 'approved'
                ORDER BY pay.id
                """,
                (lease_id,),
            ).fetchall()
    return {
        "today": desk["date_today"] if desk else None,
        "lease": dict(lease) if lease else None,
        "cash_accounts": [dict(a) for a in accounts],
        "rent_payments": [dict(r) for r in rent_payments],
    }


@mcp.tool
def get_pricing(sku: str) -> dict | None:
    """Get a product's unit cost and list price.

    Reads the pricing table. Pass a SKU such as "CC-HOOD-NAVY". Use this
    before agreeing to any discount so the price stays above cost.
    Returns None if the SKU isn't in the pricing table.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?",
            (sku.strip().upper(),),
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _connect_rw() -> sqlite3.Connection:
    """Open the database for writing. Only make_payment uses this."""
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def _shop_today(conn: sqlite3.Connection) -> date:
    """The shop's "today" always comes from desk.date_today, never the computer clock."""
    row = conn.execute("SELECT date_today FROM desk").fetchone()
    if row is None:
        raise RuntimeError("desk table has no date_today row")
    return date.fromisoformat(row["date_today"])


def _unpaid_invoices(conn: sqlite3.Connection, today: date, vendor_id: int | None = None) -> list[dict]:
    """Invoices whose status is anything other than 'paid', with days overdue vs desk.date_today."""
    query = """
        SELECT i.id, i.vendor_id, v.name AS vendor_name, i.amount, i.due_date, i.status, i.description
        FROM invoices i JOIN vendors v ON v.id = i.vendor_id
        WHERE i.status != 'paid'
    """
    params: list[int] = []
    if vendor_id is not None:
        query += " AND i.vendor_id = ?"
        params.append(vendor_id)
    rows = conn.execute(query + " ORDER BY i.due_date, i.id", params).fetchall()
    invoices = []
    for r in rows:
        days_late = (today - date.fromisoformat(r["due_date"])).days
        invoices.append({**dict(r), "overdue": days_late > 0, "days_overdue": max(days_late, 0)})
    return invoices


def _add_month(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=year, month=month, day=min(d.day, calendar.monthrange(year, month)[1]))


# Words that reveal internal business details. A reply to a customer, student group, or landlord
# may not contain them: draft_customer_reply refuses the draft.
INTERNAL_TERMS = re.compile(
    r"\b(?:vendors?|suppliers?|printers?|invoices?|unpaid|overdue|cash|bank|balances?|checking account"
    r"|unit[- ]costs?|our costs?|wholesale|margins?|mark-?ups?|profits?|proposal\s*#?\s*\d+)\b",
    re.I,
)
MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")


def _internal_details(conn: sqlite3.Connection, ticket: sqlite3.Row, text: str) -> list[str]:
    """Internal details in a reply to a ticket's requester: vendors, invoices, cash, costs, margins, proposals."""
    found = {m.group(0).lower() for m in INTERNAL_TERMS.finditer(text)}
    low = text.lower()
    found |= {v["name"] for v in conn.execute("SELECT name FROM vendors") if v["name"].lower() in low}
    amounts = {round(float(a.replace(",", "")), 2) for a in MONEY.findall(text)}
    for a in conn.execute("SELECT name, balance FROM cash_accounts"):
        if round(a["balance"], 2) in amounts:
            found.add(f"${a['balance']:,.2f} ({a['name']} balance)")
    for i in conn.execute("SELECT id, amount FROM invoices"):
        if round(i["amount"], 2) in amounts:
            found.add(f"${i['amount']:,.2f} (invoice {i['id']} amount)")
    if ticket["sku"]:
        price = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (ticket["sku"],)).fetchone()
        if price and price["unit_cost"] != price["list_price"] and round(price["unit_cost"], 2) in amounts:
            found.add(f"${price['unit_cost']:,.2f} (unit cost of {ticket['sku']})")
    return sorted(found)


def _save_draft(draft: dict) -> dict:
    """Append a draft to drafts.json (never overwrites earlier drafts). Nothing is sent."""
    with _drafts_lock:
        drafts = json.loads(DRAFTS_PATH.read_text()) if DRAFTS_PATH.exists() else []
        draft = {
            "draft_id": len(drafts) + 1,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            **draft,
            "status": "draft - NOT sent",
        }
        drafts.append(draft)
        DRAFTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = DRAFTS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(drafts, indent=2))
        tmp.replace(DRAFTS_PATH)
    return draft


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


@mcp.tool
def list_open_tickets() -> list[dict]:
    """List every ticket whose status is 'open'.

    Reads the tickets table. Returns id, type, requester, subject, and
    created_at for each one. Use get_ticket for the full details.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, type, requester, subject, created_at
            FROM tickets
            WHERE status = 'open'
            ORDER BY id
            """
        ).fetchall()
    return [dict(r) for r in rows]


@mcp.tool
def get_ticket(ticket_id: int) -> dict | None:
    """Get every field of one ticket (sku, size, qty, lease_id, invoice_id, notes...).

    Reads the tickets table. Returns None if the ticket id doesn't exist.
    """
    with _connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return dict(row) if row else None


@mcp.tool
def get_shop_date() -> dict:
    """Get the shop's current date from desk.date_today.

    Reads the desk table. Always use this date (not your own idea of
    today) when deciding whether something is due or overdue.
    """
    with _connect() as conn:
        row = conn.execute("SELECT date_today, notes FROM desk").fetchone()
    return dict(row) if row else {"date_today": None, "notes": None}


@mcp.tool
def list_unpaid_invoices(vendor_id: int | None = None) -> dict:
    """List vendor invoices that are not paid, with how many days overdue each one is.

    Reads the invoices, vendors, and desk tables. Overdue is measured
    against desk.date_today. Pass vendor_id to see one vendor only.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        invoices = _unpaid_invoices(conn, today, vendor_id)
    return {"today": today.isoformat(), "unpaid_invoices": invoices}


@mcp.tool
def list_vendors() -> dict:
    """List every vendor with its lead time and whether the shop may order from it.

    Reads the vendors, invoices, and desk tables. earliest_delivery is
    desk.date_today + lead_days. can_order is false whenever the vendor
    has any unpaid invoice — the shop never orders from those vendors.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        vendors = conn.execute(
            "SELECT id, name, specialty, lead_days FROM vendors ORDER BY id"
        ).fetchall()
        result = []
        for v in vendors:
            unpaid = _unpaid_invoices(conn, today, v["id"])
            result.append(
                {
                    **dict(v),
                    "earliest_delivery": (today + timedelta(days=v["lead_days"])).isoformat(),
                    "unpaid_invoice_ids": [i["id"] for i in unpaid],
                    "can_order": not unpaid,
                }
            )
    return {"today": today.isoformat(), "vendors": result}


@mcp.tool
def get_cash_and_payments() -> dict:
    """Show every cash account balance and the payments already made.

    Reads the cash_accounts, payments, and desk tables. Check payments
    before proposing a new one so nothing gets paid twice.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        accounts = conn.execute(
            "SELECT name, balance, date FROM cash_accounts ORDER BY name"
        ).fetchall()
        payments = conn.execute(
            """
            SELECT id, kind, ref_id, amount, account, paid_at, approved_by
            FROM payments
            ORDER BY id DESC
            LIMIT 20
            """
        ).fetchall()
    return {
        "today": today.isoformat(),
        "cash_accounts": [dict(a) for a in accounts],
        "payments": [dict(p) for p in payments],
    }


# ---------------------------------------------------------------------------
# Draft tools (never sent)
# ---------------------------------------------------------------------------


@mcp.tool
def draft_customer_reply(ticket_id: int, subject: str, body: str) -> dict:
    """Save a DRAFT reply to a ticket's requester (customer, student org, or landlord). Never sent.

    Reads the tickets table to find the requester; the recipient is always
    the ticket's requester. Refused if the reply mentions internal details:
    vendors, invoices, cash or balances, costs, margins, or proposal numbers
    (also reads vendors, cash_accounts, invoices, pricing). Writes the draft
    to output/drafts.json.
    """
    with _connect() as conn:
        ticket = conn.execute("SELECT id, requester, sku FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            return {"ok": False, "reason": f"Ticket {ticket_id} does not exist."}
        internal = _internal_details(conn, ticket, f"{subject}\n{body}")
    if internal:
        return {
            "ok": False,
            "reason": (
                f"Draft not saved: it mentions internal details ({', '.join(internal)}). Customer, student-group, "
                "and landlord replies may not mention vendors, invoices, cash, costs, margins, or proposal numbers. "
                "Rewrite it without them."
            ),
        }
    draft = _save_draft(
        {
            "kind": "customer_reply",
            "ticket_id": ticket_id,
            "to": ticket["requester"],
            "subject": subject,
            "body": body,
        }
    )
    return {"ok": True, "draft": draft}


@mcp.tool
def draft_vendor_message(
    vendor_id: int,
    subject: str,
    body: str,
    is_order: bool,
    ticket_id: int | None = None,
) -> dict:
    """Save a DRAFT message to a vendor. Never sent.

    Reads the vendors, invoices, and desk tables. Set is_order=true when the
    message places or requests an order: it is refused if the vendor has any
    unpaid invoice. Writes the draft to output/drafts.json.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        vendor = conn.execute("SELECT id, name, lead_days FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if vendor is None:
            return {"ok": False, "reason": f"Vendor {vendor_id} does not exist."}
        unpaid = _unpaid_invoices(conn, today, vendor_id)
    if is_order and unpaid:
        return {
            "ok": False,
            "reason": (
                f"Order refused: {vendor['name']} has unpaid invoice(s) "
                f"{[i['id'] for i in unpaid]}. The shop never orders from a vendor with an unpaid invoice."
            ),
        }
    draft = _save_draft(
        {
            "kind": "vendor_order" if is_order else "vendor_message",
            "ticket_id": ticket_id,
            "to": vendor["name"],
            "subject": subject,
            "body": body,
            "lead_days": vendor["lead_days"],
            "earliest_delivery": (today + timedelta(days=vendor["lead_days"])).isoformat(),
        }
    )
    return {"ok": True, "draft": draft}


# ---------------------------------------------------------------------------
# Tickets, proposals, and human-only actions
# ---------------------------------------------------------------------------

PROPOSALS_TABLE = """
    CREATE TABLE IF NOT EXISTS proposals (
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,          -- 'invoice' | 'rent' | 'purchase' | 'price_override'
        ref_id INTEGER NOT NULL,     -- invoices.id, leases.id, vendors.id (purchase), or tickets.id (price_override)
        sku TEXT,
        size TEXT,
        qty INTEGER,
        unit_price REAL,             -- price_override only: the price per unit a human may allow
        amount REAL NOT NULL,        -- cash that leaves the account if approved (0 for price_override)
        account TEXT NOT NULL,
        ticket_id INTEGER,
        reason TEXT,
        proposed_by TEXT NOT NULL,
        status TEXT NOT NULL,        -- 'pending' | 'approved' | 'rejected'
        created_at TEXT NOT NULL,
        decided_by TEXT,
        decided_at TEXT,
        payment_id INTEGER,
        note TEXT,
        covers_due TEXT              -- rent only: the lease due date this payment paid (next_due before approval)
    )
"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _has_proposals_table(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='proposals'").fetchone() is not None


def _begin_write() -> sqlite3.Connection:
    """Read-write connection inside an IMMEDIATE transaction, with the proposals table in place."""
    conn = _connect_rw()
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(PROPOSALS_TABLE)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(proposals)")}
    if "unit_price" not in columns:  # table created by an older version of this server
        conn.execute("ALTER TABLE proposals ADD COLUMN unit_price REAL")
    if "covers_due" not in columns:  # added so a paid rent notice can be matched to the payment for it
        conn.execute("ALTER TABLE proposals ADD COLUMN covers_due TEXT")
    return conn


def _refuse(conn: sqlite3.Connection, reason: str) -> dict:
    if conn.in_transaction:
        conn.execute("ROLLBACK")
    conn.close()
    return {"ok": False, "reason": reason}


def _human_problem(human_key: str, name: str) -> str | None:
    """Why this caller may NOT do a human-only action, or None if it may."""
    if not HUMAN_KEY:
        return "Human-only actions are switched off in this server instance; use the backend's human approval step (backend/approvals.py)."
    if not hmac.compare_digest(human_key or "", HUMAN_KEY):
        return "Wrong human key: only the backend's human approval step can do this."
    if (name or "").strip().lower() in NOT_HUMAN_APPROVERS:
        return "A named human must make this decision; agent names and placeholders are not accepted."
    return None


def _payment_problem(conn: sqlite3.Connection, kind: str, ref_id: int, amount: float, account: str) -> str | None:
    """Checks shared by propose_payment and approve_proposal (everything except the cash balance)."""
    if amount <= 0:
        return "Amount must be positive; cash only goes out."
    if conn.execute("SELECT 1 FROM cash_accounts WHERE name = ?", (account,)).fetchone() is None:
        return f"No cash account named {account!r}."
    if kind == "invoice":
        inv = conn.execute("SELECT amount, status FROM invoices WHERE id = ?", (ref_id,)).fetchone()
        if inv is None:
            return f"Invoice {ref_id} does not exist."
        if inv["status"] == "paid":
            return f"Invoice {ref_id} is already paid."
        if abs(inv["amount"] - amount) > 0.005:
            return f"Amount {amount} does not match invoice amount {inv['amount']}."
    elif kind == "rent":
        lease = conn.execute("SELECT monthly_rent FROM leases WHERE id = ?", (ref_id,)).fetchone()
        if lease is None:
            return f"Lease {ref_id} does not exist."
        if abs(lease["monthly_rent"] - amount) > 0.005:
            return f"Amount {amount} does not match monthly rent {lease['monthly_rent']}."
    else:
        return "kind must be 'invoice' or 'rent'."
    return None


def _balance(conn: sqlite3.Connection, account: str) -> float:
    return conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()["balance"]


def _pending_total(conn: sqlite3.Connection) -> float:
    return conn.execute("SELECT COALESCE(SUM(amount), 0) AS t FROM proposals WHERE status = 'pending'").fetchone()["t"]


def _insert_proposal(conn: sqlite3.Connection, **fields: object) -> dict:
    fields = {"status": "pending", "created_at": _now(), **fields}
    cols = ", ".join(fields)
    cur = conn.execute(f"INSERT INTO proposals ({cols}) VALUES ({', '.join('?' * len(fields))})", tuple(fields.values()))
    pending = _pending_total(conn)
    balance = _balance(conn, str(fields["account"]))
    conn.execute("COMMIT")
    conn.close()
    return {
        "ok": True,
        "proposal_id": cur.lastrowid,
        "status": "pending",
        "amount": fields["amount"],
        "account": fields["account"],
        "balance_now": balance,
        "all_pending_total": pending,
        "balance_if_all_pending_approved": round(balance - pending, 2),
        "message": "Waiting for a human to approve it. No cash has moved.",
    }


@mcp.tool
def list_tickets() -> list[dict]:
    """List every ticket (open and resolved) with its status.

    Reads the tickets table.
    """
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@mcp.tool
def list_proposals(status: Literal["pending", "approved", "rejected"] | None = None) -> list[dict]:
    """List proposed payments and purchases, optionally only one status.

    Reads the proposals table (empty until an agent proposes something).
    Check this before proposing, so the same thing isn't proposed twice.
    An approved purchase also shows its vendor order (reads payments, vendors,
    and output/drafts.json): vendor, paid_at, earliest_delivery (paid_at + the
    vendor's lead_days), and vendor_order_draft_id. Approving a purchase pays
    for it and saves the vendor order as a draft for a human to send, so the
    restock counts as ordered, with that delivery date.
    """
    with _connect() as conn:
        if not _has_proposals_table(conn):
            return []
        if status:
            rows = conn.execute("SELECT * FROM proposals WHERE status = ? ORDER BY id", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM proposals ORDER BY id").fetchall()
        proposals = [dict(r) for r in rows]
        for p in proposals:
            if p["kind"] == "purchase" and p["status"] == "approved" and p.get("payment_id"):
                info = conn.execute(
                    "SELECT pay.paid_at, v.name, v.lead_days FROM payments pay, vendors v WHERE pay.id = ? AND v.id = ?",
                    (p["payment_id"], p["ref_id"]),
                ).fetchone()
                if info:
                    p["vendor"] = info["name"]
                    p["paid_at"] = info["paid_at"]
                    p["earliest_delivery"] = (date.fromisoformat(info["paid_at"]) + timedelta(days=info["lead_days"])).isoformat()
                    p["vendor_order_draft_id"] = _order_draft_id(p)
    return proposals


def _order_draft_id(p: dict) -> int | None:
    """The vendor-order draft approve_proposal saved for this purchase, if it can be found."""
    if not DRAFTS_PATH.exists():
        return None
    subject = f"Order: {p['qty']} x {p['sku']} size {p['size']}"
    drafts = json.loads(DRAFTS_PATH.read_text())
    match = [d for d in drafts if d.get("kind") == "vendor_order" and d.get("ticket_id") == p["ticket_id"]
             and d.get("subject") == subject]
    return match[-1]["draft_id"] if match else None


@mcp.tool
def propose_payment(
    kind: Literal["invoice", "rent"],
    ref_id: int,
    amount: float,
    account: str,
    reason: str,
    proposed_by: str,
    ticket_id: int | None = None,
) -> dict:
    """PROPOSE paying a vendor invoice or a lease's rent. No cash moves.

    Reads invoices, leases, cash_accounts; writes a 'pending' row to
    proposals. kind="invoice": ref_id is invoices.id and amount must equal
    the invoice amount. kind="rent": ref_id is leases.id and amount must
    equal monthly_rent. Refused if the account can't cover it now, or if
    the same payment is already pending. A human approves it later;
    only that approval moves cash.
    """
    conn = _begin_write()
    problem = _payment_problem(conn, kind, ref_id, amount, account)
    if problem:
        return _refuse(conn, problem)
    dup = conn.execute(
        "SELECT id FROM proposals WHERE status = 'pending' AND kind = ? AND ref_id = ?", (kind, ref_id)
    ).fetchone()
    if dup:
        return _refuse(conn, f"Proposal #{dup['id']} for this {kind} is already waiting for approval.")
    balance = _balance(conn, account)
    if balance < amount:
        return _refuse(conn, f"Not enough cash: {account} has {balance:.2f}, payment needs {amount:.2f}.")
    return _insert_proposal(
        conn, kind=kind, ref_id=ref_id, amount=amount, account=account,
        ticket_id=ticket_id, reason=reason, proposed_by=proposed_by,
    )


@mcp.tool
def propose_purchase(
    vendor_id: int,
    sku: str,
    size: str,
    qty: int,
    reason: str,
    proposed_by: str,
    ticket_id: int | None = None,
    account: str = "checking",
) -> dict:
    """PROPOSE buying stock from a vendor. No cash moves and nothing is ordered yet.

    Reads vendors, invoices, inventory, pricing, cash_accounts, desk;
    writes a 'pending' row to proposals. Cost = qty x pricing.unit_cost.
    Refused if the vendor has ANY unpaid invoice, if the sku/size isn't a
    product we stock, or if the account can't cover the cost. When a human
    approves it, cash is paid and a vendor order is saved as a DRAFT.
    """
    if qty <= 0:
        return {"ok": False, "reason": "qty must be at least 1."}
    sku, size = sku.strip().upper(), size.strip().upper()
    conn = _begin_write()
    today = _shop_today(conn)
    vendor = conn.execute("SELECT id, name, lead_days FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
    if vendor is None:
        return _refuse(conn, f"Vendor {vendor_id} does not exist.")
    unpaid = _unpaid_invoices(conn, today, vendor_id)
    if unpaid:
        return _refuse(
            conn,
            f"Purchase refused: {vendor['name']} has unpaid invoice(s) {[i['id'] for i in unpaid]}. "
            "The shop never orders from a vendor with an unpaid invoice.",
        )
    if conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone() is None:
        return _refuse(conn, f"{sku} size {size} is not a product in inventory.")
    price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if price is None:
        return _refuse(conn, f"{sku} has no unit cost in pricing.")
    if conn.execute("SELECT 1 FROM cash_accounts WHERE name = ?", (account,)).fetchone() is None:
        return _refuse(conn, f"No cash account named {account!r}.")
    amount = round(qty * price["unit_cost"], 2)
    dup = conn.execute(
        "SELECT id FROM proposals WHERE status = 'pending' AND kind = 'purchase' AND ref_id = ? AND sku = ? AND size = ?",
        (vendor_id, sku, size),
    ).fetchone()
    if dup:
        return _refuse(conn, f"Purchase proposal #{dup['id']} for this item is already waiting for approval.")
    balance = _balance(conn, account)
    if balance < amount:
        return _refuse(conn, f"Not enough cash: {account} has {balance:.2f}, purchase needs {amount:.2f}.")
    result = _insert_proposal(
        conn, kind="purchase", ref_id=vendor_id, sku=sku, size=size, qty=qty, amount=amount,
        account=account, ticket_id=ticket_id, reason=reason, proposed_by=proposed_by,
    )
    result.update(
        vendor=vendor["name"],
        unit_cost=price["unit_cost"],
        earliest_delivery_if_approved_today=(today + timedelta(days=vendor["lead_days"])).isoformat(),
    )
    return result


@mcp.tool
def propose_price_override(
    ticket_id: int,
    sku: str,
    size: str,
    qty: int,
    unit_price: float,
    reason: str,
    proposed_by: str,
) -> dict:
    """PROPOSE a special price (e.g. a bulk discount) for a human to approve or reject. No cash moves.

    Reads tickets, inventory, pricing; writes a 'pending' row to proposals.
    unit_price must be ABOVE pricing.unit_cost and no higher than
    list_price. Revenue isn't modeled, so approving it changes no balance:
    it only records the price a human allowed, so the team can quote it.
    """
    if qty <= 0:
        return {"ok": False, "reason": "qty must be at least 1."}
    sku, size = sku.strip().upper(), size.strip().upper()
    conn = _begin_write()
    ticket = conn.execute("SELECT id, status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if ticket is None:
        return _refuse(conn, f"Ticket {ticket_id} does not exist.")
    if ticket["status"] != "open":
        return _refuse(conn, f"Ticket {ticket_id} is {ticket['status']}.")
    if conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone() is None:
        return _refuse(conn, f"{sku} size {size} is not a product in inventory.")
    price = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if price is None:
        return _refuse(conn, f"{sku} has no row in pricing.")
    if unit_price <= price["unit_cost"]:
        return _refuse(conn, f"Price {unit_price:.2f} is not above unit cost {price['unit_cost']:.2f}; never sell at or below cost.")
    if unit_price > price["list_price"]:
        return _refuse(conn, f"Price {unit_price:.2f} is above list price {price['list_price']:.2f}; an override can only lower the price.")
    dup = conn.execute(
        "SELECT id FROM proposals WHERE status = 'pending' AND kind = 'price_override' AND ref_id = ?", (ticket_id,)
    ).fetchone()
    if dup:
        return _refuse(conn, f"Price override proposal #{dup['id']} for ticket {ticket_id} is already waiting for approval.")
    cur = conn.execute(
        """
        INSERT INTO proposals (kind, ref_id, sku, size, qty, unit_price, amount, account, ticket_id, reason,
                               proposed_by, status, created_at)
        VALUES ('price_override', ?, ?, ?, ?, ?, 0, 'checking', ?, ?, ?, 'pending', ?)
        """,
        (ticket_id, sku, size, qty, round(unit_price, 2), ticket_id, reason, proposed_by, _now()),
    )
    conn.execute("COMMIT")
    conn.close()
    return {
        "ok": True,
        "proposal_id": cur.lastrowid,
        "status": "pending",
        "unit_price": round(unit_price, 2),
        "list_price": price["list_price"],
        "unit_cost": price["unit_cost"],
        "discount_pct": round(100 * (1 - unit_price / price["list_price"]), 1),
        "margin_per_unit": round(unit_price - price["unit_cost"], 2),
        "message": "Waiting for a human to approve or reject this price. No cash moves either way.",
    }


@mcp.tool
def resolve_ticket(ticket_id: int, resolution: str) -> dict:
    """Mark a ticket 'resolved'. Refused while any proposal for it is still pending.

    Reads proposals; writes tickets.status. Use only when the team has done
    everything it is allowed to do and no payment, purchase, or other human
    decision is still waiting.
    """
    conn = _begin_write()
    ticket = conn.execute("SELECT id, status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if ticket is None:
        return _refuse(conn, f"Ticket {ticket_id} does not exist.")
    if ticket["status"] == "resolved":
        return _refuse(conn, f"Ticket {ticket_id} is already resolved.")
    pending = conn.execute(
        "SELECT id FROM proposals WHERE status = 'pending' AND ticket_id = ?", (ticket_id,)
    ).fetchall()
    if pending:
        return _refuse(conn, f"Ticket {ticket_id} still has pending proposal(s) {[p['id'] for p in pending]}.")
    conn.execute("UPDATE tickets SET status = 'resolved' WHERE id = ?", (ticket_id,))
    conn.execute("COMMIT")
    conn.close()
    return {"ok": True, "ticket_id": ticket_id, "status": "resolved", "resolution": resolution}


@mcp.tool
def approve_proposal(proposal_id: int, approved_by: str, human_key: str) -> dict:
    """HUMAN ONLY. Approve a pending proposal (moving cash for payments/purchases). Agents never get this tool.

    Writes payments, cash_accounts, proposals, and invoices (marked paid) or
    leases (next_due + 1 month); reads vendors, desk. Every check is redone
    at approval time, including: is there enough cash right now, and (for a
    purchase) does the vendor have an unpaid invoice. An approved purchase
    also saves a vendor order DRAFT (never sent). Needs the backend's human key.
    """
    problem = _human_problem(human_key, approved_by)
    if problem:
        return {"ok": False, "reason": problem}
    approver = approved_by.strip()
    conn = _begin_write()
    p = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
    if p is None:
        return _refuse(conn, f"Proposal {proposal_id} does not exist.")
    if p["status"] != "pending":
        return _refuse(conn, f"Proposal {proposal_id} is already {p['status']}.")
    today = _shop_today(conn)

    if p["kind"] == "price_override":
        price = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (p["sku"],)).fetchone()
        if price is None or not (price["unit_cost"] < p["unit_price"] <= price["list_price"]):
            return _refuse(conn, "The proposed price is no longer between unit cost and list price.")
        conn.execute(
            "UPDATE proposals SET status = 'approved', decided_by = ?, decided_at = ? WHERE id = ?",
            (approver, _now(), proposal_id),
        )
        balance = _balance(conn, p["account"])
        conn.execute("COMMIT")
        conn.close()
        return {
            "ok": True,
            "proposal_id": proposal_id,
            "payment_id": None,
            "kind": "price_override",
            "amount": 0,
            "unit_price": p["unit_price"],
            "new_balance": balance,
            "approved_by": approver,
            "change": f"price override approved: {p['qty']} x {p['sku']} size {p['size']} at {p['unit_price']:.2f} each (no cash moved)",
        }

    vendor = None
    if p["kind"] == "purchase":
        vendor = conn.execute("SELECT id, name, lead_days FROM vendors WHERE id = ?", (p["ref_id"],)).fetchone()
        if vendor is None:
            return _refuse(conn, f"Vendor {p['ref_id']} no longer exists.")
        unpaid = _unpaid_invoices(conn, today, vendor["id"])
        if unpaid:
            return _refuse(conn, f"{vendor['name']} now has unpaid invoice(s) {[i['id'] for i in unpaid]}; can't order.")
    else:
        problem = _payment_problem(conn, p["kind"], p["ref_id"], p["amount"], p["account"])
        if problem:
            return _refuse(conn, problem)

    balance = _balance(conn, p["account"])
    if balance < p["amount"]:
        return _refuse(conn, f"Not enough cash: {p['account']} has {balance:.2f}, this needs {p['amount']:.2f}.")

    new_balance = round(balance - p["amount"], 2)
    conn.execute(
        "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_balance, today.isoformat(), p["account"])
    )
    payment_ref = p["id"] if p["kind"] == "purchase" else p["ref_id"]
    cur = conn.execute(
        "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
        (p["kind"], payment_ref, p["amount"], p["account"], today.isoformat(), approver),
    )
    covers_due = None
    if p["kind"] == "invoice":
        conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (p["ref_id"],))
        change = f"invoice {p['ref_id']} marked paid"
    elif p["kind"] == "rent":
        covers_due = conn.execute("SELECT next_due FROM leases WHERE id = ?", (p["ref_id"],)).fetchone()["next_due"]
        next_due = _add_month(date.fromisoformat(covers_due)).isoformat()
        conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (next_due, p["ref_id"]))
        change = f"rent due {covers_due} paid; lease {p['ref_id']} next_due moved to {next_due}"
    else:
        change = f"purchase of {p['qty']} x {p['sku']} size {p['size']} paid; stock arrives after the vendor's lead time"
    conn.execute(
        "UPDATE proposals SET status = 'approved', decided_by = ?, decided_at = ?, payment_id = ?, covers_due = ? WHERE id = ?",
        (approver, _now(), cur.lastrowid, covers_due, proposal_id),
    )
    conn.execute("COMMIT")
    conn.close()

    result = {
        "ok": True,
        "proposal_id": proposal_id,
        "payment_id": cur.lastrowid,
        "kind": p["kind"],
        "amount": p["amount"],
        "account": p["account"],
        "new_balance": new_balance,
        "approved_by": approver,
        "change": change,
    }
    if covers_due is not None:
        result["covered_due_date"] = covers_due
    if vendor is not None:
        result["order_draft"] = _save_draft(
            {
                "kind": "vendor_order",
                "ticket_id": p["ticket_id"],
                "to": vendor["name"],
                "subject": f"Order: {p['qty']} x {p['sku']} size {p['size']}",
                "body": f"Please supply {p['qty']} x {p['sku']} in size {p['size']}. "
                f"Paid {p['amount']:.2f} (payment #{cur.lastrowid}, approved by {approver}).",
                "lead_days": vendor["lead_days"],
                "earliest_delivery": (today + timedelta(days=vendor["lead_days"])).isoformat(),
            }
        )["draft_id"]
    return result


@mcp.tool
def reject_proposal(proposal_id: int, rejected_by: str, human_key: str, note: str = "") -> dict:
    """HUMAN ONLY. Reject a pending proposal; no cash moves. Agents never get this tool.

    Writes proposals. Needs the backend's human key.
    """
    problem = _human_problem(human_key, rejected_by)
    if problem:
        return {"ok": False, "reason": problem}
    conn = _begin_write()
    p = conn.execute("SELECT status FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
    if p is None:
        return _refuse(conn, f"Proposal {proposal_id} does not exist.")
    if p["status"] != "pending":
        return _refuse(conn, f"Proposal {proposal_id} is already {p['status']}.")
    conn.execute(
        "UPDATE proposals SET status = 'rejected', decided_by = ?, decided_at = ?, note = ? WHERE id = ?",
        (rejected_by.strip(), _now(), note, proposal_id),
    )
    conn.execute("COMMIT")
    conn.close()
    return {"ok": True, "proposal_id": proposal_id, "status": "rejected", "rejected_by": rejected_by.strip()}


@mcp.tool
def reset_working_database(requested_by: str, human_key: str) -> dict:
    """HUMAN ONLY. Copy the original database over the working one (fresh start).

    Reads data/campus_customs.db (never writes it) and replaces
    data/campus_customs_new.db. Proposals, payments, and ticket statuses go
    back to the original values. Drafts and the audit trail are kept.
    Needs the backend's human key.
    """
    problem = _human_problem(human_key, requested_by)
    if problem:
        return {"ok": False, "reason": problem}
    if DB_PATH.resolve() == ORIGINAL_DB_PATH.resolve():
        return {"ok": False, "reason": "The working database path points at the original; refusing to reset."}
    tmp = DB_PATH.with_suffix(".resetting")
    shutil.copyfile(ORIGINAL_DB_PATH, tmp)  # read the original, write only the temp copy
    tmp.replace(DB_PATH)
    with _connect() as conn:
        balance = conn.execute("SELECT name, balance FROM cash_accounts ORDER BY name").fetchall()
        open_tickets = conn.execute("SELECT COUNT(*) AS n FROM tickets WHERE status = 'open'").fetchone()["n"]
    return {
        "ok": True,
        "message": "Working database reset to the original values.",
        "cash_accounts": [dict(b) for b in balance],
        "open_tickets": open_tickets,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Campus Customs MCP server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve Streamable HTTP on port 8001 instead of stdio",
    )
    args = parser.parse_args()
    if args.http:
        mcp.run(transport="http", host="127.0.0.1", port=8001)
    else:
        mcp.run(show_banner=False)  # keep the startup banner out of the backend's terminal output
