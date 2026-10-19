# Campus Customs MCP Server (HW 6)

## What it does

This is a small [FastMCP](https://gofastmcp.com) server, copied from HW 5 for HW 6 Problem 7. It's the only way the five agents in `../backend/` (and Claude Code, through `../.mcp.json`) read or change Campus Customs shop data. Every tool reads the real database, and none of them invent values.

- **Read tools** open the database read-only.
- **Agents can only propose** payments, purchases, and price overrides. No cash moves when they do.
- **Only `approve_proposal` moves cash.** It needs a human's name plus a secret *human key*. The backend creates the key at startup (`backend/shop_mcp.py`) and gives it only to its own copy of this server; the human approval step (`backend/approvals.py`) is the only code that sends it. Agents never see the key or the tool. Claude Code's copy, started from `../.mcp.json`, has no key, so approve, reject, and reset are switched off there.
- **Draft tools** save messages to `../output/drafts.json` with the status `draft - NOT sent`. Nothing is ever emailed. Replies to customers, student groups, and landlords are refused if they mention internal details (vendors, invoices, cash, costs, margins, or proposal numbers).

## Database

- **Working copy:** the server works on `../data/campus_customs_new.db`.
- **Original:** `../data/campus_customs.db` is only ever **read**, by `reset_working_database`. Both files were copied from HW 5's original database, so HW 6 starts from clean data.
- **Tables:** `desk`, `tickets`, `inventory`, `pricing`, `vendors`, `invoices`, `cash_accounts`, `payments`, `leases`. The server adds a `proposals` table the first time something is proposed.
- **"Today"** is always `desk.date_today` (2026-08-31 in the original data), never the computer's clock.

## Tools (20)

### Read tools

| Tool | Input | Tables | What it's for | Agents |
|---|---|---|---|---|
| `get_shop_date` | — | `desk` | The shop's "today" (`desk.date_today`), used for every due or overdue check | all five |
| `list_open_tickets` | — | `tickets` | The open ticket queue | Boss |
| `list_tickets` | — | `tickets` | Every ticket with its status | none (CLI and tests) |
| `get_ticket` | `ticket_id` | `tickets` | Every field of one ticket (sku, size, qty, lease_id, invoice_id, notes) | all five |
| `check_stock` | `sku`, optional `size` | `inventory` | Units on the shelf by size, and the aisle | Inventory, Customer Service |
| `get_pricing` | `sku` | `pricing` | Unit cost and list price | Inventory, Customer Service |
| `list_vendors` | — | `vendors`, `invoices`, `desk` | Each vendor's `lead_days` from the vendors table, earliest delivery (`date_today` + `lead_days`), and `can_order` (false if the vendor has any unpaid invoice) | Inventory |
| `list_unpaid_invoices` | optional `vendor_id` | `invoices`, `vendors`, `desk` | Unpaid invoices, with days overdue measured against `desk.date_today` | Accounting |
| `get_cash_and_payments` | — | `cash_accounts`, `payments`, `desk` | Cash balances and the payments already made | Accounting |
| `get_rent_and_cash` | `lease_id` | `leases`, `cash_accounts`, `desk`; `proposals`, `payments` once rent is paid | A lease's rent and due date, next to the cash and today's date, plus `rent_payments`: each human-approved rent payment with the `covered_due_date` it paid. A notice whose due date is a `covered_due_date` is already paid. | Accounting, Facilities |
| `list_proposals` | optional `status` | `proposals`; for approved purchases also `payments`, `vendors`, `output/drafts.json` | Proposed payments, purchases, and prices, and whether each is pending, approved, or rejected. An approved purchase also shows its `vendor`, `paid_at`, `earliest_delivery` (paid date + `lead_days`), and `vendor_order_draft_id`, so agents can see the restock is ordered. | Boss, Inventory, Accounting |

### Agent action tools (propose, resolve, draft)

| Tool | Input | Tables / files | What it does | Agents |
|---|---|---|---|---|
| `propose_payment` | `kind` (`invoice` or `rent`), `ref_id`, `amount`, `account`, `reason`, `proposed_by`, optional `ticket_id` | reads `invoices`, `leases`, `cash_accounts`; writes `proposals` | Creates a **pending** payment. The amount must match the invoice or rent exactly and be positive. It's refused if the account can't cover it or the same payment is already pending. **No cash moves.** | Accounting |
| `propose_purchase` | `vendor_id`, `sku`, `size`, `qty`, `reason`, `proposed_by`, optional `ticket_id`, `account` | reads `vendors`, `invoices`, `inventory`, `pricing`, `cash_accounts`, `desk`; writes `proposals` | Creates a **pending** restock costing qty × `unit_cost`. **It's refused if the vendor has any unpaid invoice** or if cash can't cover it. No cash moves. | Inventory |
| `propose_price_override` | `ticket_id`, `sku`, `size`, `qty`, `unit_price`, `reason`, `proposed_by` | reads `tickets`, `inventory`, `pricing`; writes `proposals` | Creates a **pending** special price for a human to decide. It must be above `unit_cost` and no higher than `list_price`. No cash moves, because revenue isn't modeled. | Inventory |
| `resolve_ticket` | `ticket_id`, `resolution` | reads `proposals`; writes `tickets.status` | Marks a ticket resolved. It's refused while any proposal for that ticket is pending. | Boss |
| `draft_customer_reply` | `ticket_id`, `subject`, `body` | reads `tickets`, `vendors`, `cash_accounts`, `invoices`, `pricing`; writes `output/drafts.json` | Saves a **draft** to the ticket's requester (customer, student group, or landlord). Not sent. **Refused** if the reply mentions internal details: a vendor name or words like vendor, supplier, printer, invoice, unpaid, overdue, cash, balance, bank, unit cost, margin, or "proposal #N"; a $ amount equal to a cash balance or an invoice; or the ticket product's unit cost. The agent gets the reason and must rewrite. | Facilities, Customer Service |
| `draft_vendor_message` | `vendor_id`, `subject`, `body`, `is_order`, optional `ticket_id` | reads `vendors`, `invoices`, `desk`; writes `output/drafts.json` | Saves a **draft** to a vendor, and refuses an order draft while the vendor has an unpaid invoice | none (approved purchases draft the vendor order automatically) |

### Human-only tools (need the backend's human key; no agent can see them)

| Tool | Input | Tables | What it does |
|---|---|---|---|
| `approve_proposal` | `proposal_id`, `approved_by`, `human_key` | writes `proposals`, `payments`, `cash_accounts`, and `invoices` (marked paid) or `leases` (`next_due` + 1 month); reads `vendors`, `desk` | **The only tool that moves cash.** It redoes every check, including whether there is enough cash *now* and whether the vendor has an unpaid invoice. For rent, it also records which due date the payment covered (`proposals.covers_due`) before moving `next_due` forward a month. Agent names and placeholders aren't accepted as the approver. An approved purchase also saves a vendor order draft. An approved price override moves no cash. |
| `reject_proposal` | `proposal_id`, `rejected_by`, `human_key`, optional `note` | writes `proposals` | Rejects a pending proposal. No cash moves. |
| `reset_working_database` | `requested_by`, `human_key` | reads `campus_customs.db`; replaces `campus_customs_new.db` | Copies the original over the working copy for a clean start. Drafts and the audit trail are kept. |

If nothing matches, a tool returns an empty result (`[]`, `None`, or `{"ok": false, "reason": ...}`). It never returns made-up values.

## Which tools the open tickets need

I checked the database and tickets 101, 102, and 103 against the tool list. The 20 tools already cover everything the three tickets need, so I added no new tools.

| Ticket | What the data shows | Tools |
|---|---|---|
| **101** customer order: 1 × `CC-TEE-WHITE` size S, linked to invoice 501 | 0 in stock. The apparel vendor, Bulldog Print Co (5 lead days), has unpaid invoice 501: $840, due 2026-08-28, so 3 days overdue on 2026-08-31. It can't be ordered from until the invoice is paid. | `get_ticket`, `check_stock`, `list_vendors`, `list_unpaid_invoices`, `get_cash_and_payments`, `propose_payment`, then `propose_purchase` once the invoice is paid, `draft_customer_reply` |
| **102** rent notice from Elm City Properties, lease 1 | $2,400 due 2026-09-02 (2 days away). Cash is $3,400. | `get_ticket`, `get_rent_and_cash`, `propose_payment` (rent), `draft_customer_reply` (to the landlord) |
| **103** bulk discount: 20 × `CC-HOOD-NAVY` size M | 8 in stock, so 12 short. Unit cost $22, list price $58. Restocking needs the same apparel vendor. | `get_ticket`, `check_stock`, `get_pricing`, `list_vendors`, `propose_price_override`, `propose_purchase` (if allowed and affordable), `draft_customer_reply` |

**Cash is shared across all three tickets.** $3,400 − $2,400 rent − $840 invoice leaves $160. A 12-hoodie restock (12 × $22 = $264) would then be refused for lack of cash.

## Files

```
mcp_server/
├── server.py          # the server and all 20 tools
├── requirements.txt   # fastmcp
└── README.md
```

## Setup

HW 6 uses one project `.venv` for everything; `fastmcp` is in the root `requirements.txt`. Usually you don't start the server yourself: the backend and Claude Code start it from `../.mcp.json` (`.venv/bin/python mcp_server/server.py`). To run it alone from the `HW 6` folder:

```bash
.venv/bin/python mcp_server/server.py
```

Add `--http` to serve it at http://127.0.0.1:8001/mcp instead of over stdio.

**For tests only:**
- `CAMPUS_CUSTOMS_DB` and `CAMPUS_CUSTOMS_DRAFTS` point the server at scratch copies (`scripts/team_test.py` does this).
- `CAMPUS_CUSTOMS_HUMAN_KEY` turns on the human-only tools. The backend sets it automatically.
