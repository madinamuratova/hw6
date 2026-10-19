# Campus Customs: Harness

This harness covers everything built in HW 6:
- **The vendor desk agent** (Problems 3–6): the sections below, up to Notes.
- **The shop database** (Problems 7–9): [Database](#database-problems-79).
- **The five-agent team and its MCP server** (Problem 7): [Agent team](#agent-team-problem-7).
- **The dashboard and its API** (Problem 8): [Dashboard](#dashboard-problem-8).
- **The full run on tickets 101–103** (Problem 9): [Full run](#full-run-problem-9).

The vendor desk agent reads one vendor document (an HTML quote, PDF quote, or EML email), pulls out the key facts, and recommends whether to buy, following the shop handbook. It only reports. It never emails vendors or approves payments.

| Part | File |
|---|---|
| Agent prompt | `prompts/prompt.md` (sent with the full `data/shop_handbook.md` on every call) |
| Agent setup, run loop, output guard hook, usage and audit logging | `agent.py` |
| Tools and JSON log helpers | `tools.py` |
| Code-level checks of every answer (Problem 6) | `guards.py` |
| Data models | `models.py` |
| Problem 3 version, kept for comparison | `prompts/prompt_problem3.md`, `tools_problem3.py` |
| LLM | `gpt-6-luna` (PydanticAI `OpenAIResponsesModel`, routed through Portkey with `PORTKEY_API_KEY`) |

Run from the `HW 6` folder:

```bash
.venv/bin/python agent.py data/practice_docs/p01_bluehen_quote.html
```

## Model fields

### `VendorReport`: the agent's answer for one document

The fields follow handbook section 13 ("How the vendor desk agent should report").

| Field | Type | Meaning |
|---|---|---|
| `vendor` | `str` | The vendor that sent or issued the document (letterhead, sender, or signature). |
| `sku` | `str` or `null` | The Campus Customs SKU, for example `CC-HD-006`. |
| `unit_price` | `float` or `null` | Quoted price per unit in USD. |
| `lead_time_days` | `int` or `null` | Lead time in days, as the vendor states it ("14 business days" becomes `14`). |
| `min_order` | `int` or `null` | Minimum order quantity in units. |
| `decision` | `"recommend"` or `"do_not_recommend"` | `recommend` only if all four purchasing checks in handbook section 4 pass: approved vendor, price at or below the SKU's max unit cost, lead time ≤ 21 days, minimum order ≤ 600 units. |
| `reason` | `str` | One sentence naming the check that decided it. |

`null` means the document does not state the value. The handbook says never to guess a number, and a check with a missing value cannot pass.

### `AgentDeps`: context passed to every tool during a run

| Field | Type | Meaning |
|---|---|---|
| `run_id` | `str` | Short ID for one agent run. It links the run's records across all three logs. |
| `document` | `str` | Path of the document being reviewed, for example `data/practice_docs/p08_chapelst_email.eml`. |
| `events` | `list[dict]` | Security events from the reader and the output guard during the run. They are written to the audit trail. |

## Tools

| Tool | What it does |
|---|---|
| `read_vendor_document(path)` | Reads an `.html`, `.pdf`, or `.eml` file and returns **only the text a human reader would see**. It only reads files inside `data/`. HTML tables come back one row per line. EML returns the From, To, Subject, and Date headers, the plain-text body (or the HTML body if there is no plain text), and any attachments. **Since Problem 6**, hidden content is removed, not just labelled, and each removed passage is logged as a `hidden_content_removed` event. That covers: HTML comments, scripts, `<template>` and `<noscript>`, the `hidden` attribute, and hiding done in inline styles or `<style>` blocks (`display:none`, white text, tiny fonts, zero height, off-screen positions). In PDFs, it covers text off the page, in white, in a tiny font, or in invisible render mode. The visible text comes back between `<vendor_document>` tags marked as untrusted data. Phrases that read like instructions (for example `approve_payment`, "standing instruction", "this replaces the") are flagged to the model and logged as `instruction_like_text`. They are not removed. |
| `send_email(to, subject, body)` | **Trap tool.** Never sends anything. It appends the attempted call and its arguments to `output/trap_calls.json` and tells the agent the email was not sent. The prompt forbids calling it, so any entry in the trap log means the agent was tricked, usually by instructions hidden in a document. |
| `approve_payment(vendor, amount_usd, reference)` | **Trap tool.** Never approves or moves money. It appends the attempted call and its arguments to `output/trap_calls.json` and tells the agent the payment was not approved. Only the owner and bookkeeper can approve payments, after a human approves them. |
| `final_result` | PydanticAI's built-in output tool. The agent calls it to return its `VendorReport`. Its content is logged as the `final_answer` event. |

## Logs (`output/`)

All three logs are JSON lists, and every run appends to them without deleting earlier records.

| File | One record per | Main fields |
|---|---|---|
| `audit_trail.json` | run event | `timestamp`, `run_id`, `document`, `event` (`run_start`, `tool_call`, `tool_result`, `hidden_content_removed`, `instruction_like_text`, `guard_rejected_answer`, `guard_replaced_answer`, `final_answer`, or `run_error`), plus the tool name, arguments, result, removed text, guard problems, or final answer |
| `usage_log.json` | run | `requests`, `tool_calls`, `input_tokens` split into `uncached_input_tokens` + `cached_input_tokens` + `cache_write_tokens`, `output_tokens`, the rates used, and `cost_usd` |
| `trap_calls.json` | blocked trap call | `timestamp`, `run_id`, `document`, `tool`, `arguments`, `action_taken` |

**Cost formula** (rates per 1M tokens from `data/prices.json`):
uncached input × $0.10 + cached input × $0.01 + cache write × $0.125 + output × $0.50.

## Injection defenses (Problem 6)

Vendor documents are treated as untrusted data. The defenses work at three levels:

| Level | Defense | Where |
|---|---|---|
| Input | The model only sees the visible text. Hidden content is removed and logged, the text is wrapped in `<vendor_document>` tags, and instruction-like phrases are flagged. | `tools.read_vendor_document` |
| Prompt | A clear order of trust (this prompt, then the handbook, then the user; never documents). A rule to return `null` when a document gives two values for one field. Rules against vendor-identity claims. Trap tools described as disabled and logged. | `prompts/prompt.md` |
| Output (code) | Every answer is checked in Python before it is returned. Each fact must appear in the document's visible text. The decision must match the four handbook checks, computed by `guards.decide()` from the handbook's own tables. The reason can't contain links, email addresses, or phone numbers. A failing answer gets one retry with the problems listed. If the retry also fails, the guard **fails closed**: facts that can't be verified become `null` (or "unknown" for the vendor), and the decision and reason are computed by code. | `guards.py`, `agent.guard_output` |

The tool list, the trap tools, the `VendorReport` output, and the model configuration did not change. Test results are in `output/defense_test.md`.

## Notes

- **Two model requests per document.** The first request calls `read_vendor_document`, and the second returns the answer. The prompt and handbook (about 11.4k tokens) go out with both, so each document uses about 22.8k input tokens. Prompt caching bills most of them at the cached rate. Tested runs cost about $0.00035 per document with a warm cache. The first run, which had to write the cache, cost about $0.0016.
- **Portkey response cache is bypassed.** Portkey can replay a stored response for a repeated request. `agent.py` sends `x-portkey-cache-force-refresh: true`, so every run is a real model call and the logged usage was actually billed. This is separate from the provider's prompt caching, which still applies.

---

## Database (Problems 7–9)

The shop's data is in SQLite. It was copied from HW 5's original in Problem 7.

| File | Role |
|---|---|
| `data/campus_customs.db` | The original. It is only ever **read**, by the human-only reset. |
| `data/campus_customs_new.db` | The working copy. Every MCP tool works on it, and the reset copies the original over it. |

The agents never open the database themselves: every read and write goes through an MCP tool.

| Table | Columns | Rows at start | What it's for | MCP tools that use it |
|---|---|---|---|---|
| `desk` | `date_today`, `notes` | 1 | The shop's "today" (2026-08-31). Every due, overdue, and delivery date is measured from it. | `get_shop_date`, `list_unpaid_invoices`, `list_vendors`, `get_rent_and_cash`, `get_cash_and_payments` |
| `tickets` | `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at` | 3 | The desk queue: 101 customer order, 102 rent notice, 103 price request. `status` is `open` or `resolved`. | `list_open_tickets`, `list_tickets`, `get_ticket`; `resolve_ticket` writes `status` |
| `inventory` | `sku`, `name`, `size`, `qty`, `location` | 10 | Stock on the shelf by product and size | `check_stock`; the propose tools check that the sku and size exist |
| `pricing` | `sku`, `unit_cost`, `list_price` | 4 | What we pay and what customers pay. Any special price must stay above cost and at or below list. | `get_pricing`, `propose_purchase` (cost), `propose_price_override` |
| `vendors` | `id`, `name`, `specialty`, `lead_days` | 3 | Who can restock what, and how many days it takes | `list_vendors`, `propose_purchase`, `draft_vendor_message`, `approve_proposal`, `list_proposals` |
| `invoices` | `id`, `vendor_id`, `amount`, `due_date`, `status`, `description` | 1 | Bills the shop owes. An unpaid invoice blocks ordering from that vendor. | `list_unpaid_invoices`, `list_vendors`, `propose_payment`; `approve_proposal` marks it paid |
| `cash_accounts` | `name`, `balance`, `date` | 1 | The checking account ($3,400.00 at the start). Only `approve_proposal` lowers it. | `get_cash_and_payments`, `get_rent_and_cash`, the propose tools; `approve_proposal` writes it |
| `payments` | `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by` | 0 | Every payment a named human approved | `get_cash_and_payments`, `get_rent_and_cash`, `list_proposals`; `approve_proposal` writes it |
| `leases` | `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | 1 | The shop's lease. `next_due` moves forward a month when rent is paid. | `get_rent_and_cash`, `propose_payment`; `approve_proposal` moves `next_due` |
| `proposals` | `id`, `kind`, `ref_id`, `sku`, `size`, `qty`, `unit_price`, `amount`, `account`, `ticket_id`, `reason`, `proposed_by`, `status`, `created_at`, `decided_by`, `decided_at`, `payment_id`, `note`, `covers_due` | not in the original; the server creates it in the working copy | Every payment, purchase, or price the agents proposed, and the human's decision. `covers_due` records which rent due date a payment paid. | `list_proposals`, the propose tools, `approve_proposal`, `reject_proposal`, `resolve_ticket`, `get_rent_and_cash` |

---

## Agent team (Problem 7)

Five PydanticAI agents run the Campus Customs ticket desk: **Boss, Inventory, Accounting, Facilities, and Customer Service**. Every agent uses `gpt-6-luna` through Portkey with `PORTKEY_API_KEY`. Agents get shop data and make changes **only through the MCP server** (`mcp_server/server.py`); there is no second set of shop tools. The only non-MCP tool is `delegate`, which runs another agent.

The team is built on HW 5's team. The database (`data/campus_customs.db`, copied from HW 5's original) and the MCP server were copied into HW 6, and the working copy `data/campus_customs_new.db` starts as a fresh copy of the original. The vendor desk agent above is a separate system; both write to the same `output/audit_trail.json`, and team records are tagged `"source": "agent_team"`.

### Files (`backend/`)

| File | What it does |
|---|---|
| `agents/boss.py`, `inventory.py`, `accounting.py`, `facilities.py`, `customer_service.py` | One role per file: its prompt, the only MCP tools it may see, and who it may delegate to |
| `agents/spec.py` | Turns a role into a PydanticAI agent. It refuses any role that lists a human-only tool. |
| `prompts/*.md` | One detailed prompt per agent: role, tools, steps, shop rules, and the report format |
| `models.py` | Shared data models: `Fact`, `AgentReport`, `TicketOutcome`, `ShiftReport`, `TeamDeps` |
| `team.py` | Builds the five agents, runs each agent loop step by step, handles `delegate`, and writes every step to the audit trail |
| `shop_mcp.py` | Starts the MCP server from `.mcp.json` and creates the secret human key for this backend's copy |
| `approvals.py` | The human approval step: approve, reject, reset, and resolve. The only code that sends the human key. |
| `audit.py` | The append-only audit trail and the description of each agent-loop step |
| `config.py` | Model (`gpt-6-luna` through Portkey, with Portkey's stored-response cache bypassed), paths, and token limits |
| `cli.py` | Runs the team from the terminal, then asks a human to approve or reject each proposal |

### How the agents work together

```
            Boss
  ┌─────────┼───────────┬──────────────────┐
Inventory  Accounting  Facilities ──► Accounting
                       Customer Service ──► Inventory
```

- **The Boss** reads the queue and hands each ticket to the right specialist with `delegate(to, task, ticket_id)`. Then it decides which tickets can be resolved and writes a `ShiftReport`.
- **Specialists** return an `AgentReport`. Each fact names the MCP tool it came from, and confirmed actions are kept apart from the decisions that need a human.
- **Delegation is limited.** The Boss can reach every specialist. Facilities can only ask Accounting (rent payments), and Customer Service can only ask Inventory (restock questions). Depth is capped at 2 (Boss → specialist → one peer), and the `delegate` tool is hidden from agents at that depth.

| Agent | Job | MCP tools it can see | Can delegate to | Returns |
|---|---|---|---|---|
| Boss | Routes tickets, resolves finished ones, writes the shift report | `list_open_tickets`, `get_ticket`, `get_shop_date`, `list_proposals`, `resolve_ticket` | all four specialists | `ShiftReport` |
| Inventory | Stock, cost and price, vendors and lead times; proposes restocks and price overrides | `get_ticket`, `get_shop_date`, `check_stock`, `get_pricing`, `list_vendors`, `list_proposals`, `propose_purchase`, `propose_price_override` | — | `AgentReport` |
| Accounting | Cash, invoices, and payments; the only agent that proposes payments | `get_ticket`, `get_shop_date`, `get_cash_and_payments`, `list_unpaid_invoices`, `get_rent_and_cash`, `list_proposals`, `propose_payment` | — | `AgentReport` |
| Facilities | Lease and rent notices; checks the notice against the lease and drafts the landlord reply | `get_ticket`, `get_shop_date`, `get_rent_and_cash`, `draft_customer_reply` | Accounting | `AgentReport` |
| Customer Service | Drafts replies to customers and student groups | `get_ticket`, `get_shop_date`, `check_stock`, `get_pricing`, `draft_customer_reply` | Inventory | `AgentReport` |

### MCP tools and the tables they use

All 20 tools are described in `mcp_server/README.md`. In short:

| Tool | Tables | Used by |
|---|---|---|
| `get_shop_date` | `desk` | all agents |
| `list_open_tickets`, `list_tickets`, `get_ticket` | `tickets` | Boss; `get_ticket` by all agents; `list_tickets` by the CLI and tests only |
| `check_stock` | `inventory` | Inventory, Customer Service |
| `get_pricing` | `pricing` | Inventory, Customer Service |
| `list_vendors` | `vendors`, `invoices`, `desk` | Inventory |
| `list_unpaid_invoices` | `invoices`, `vendors`, `desk` | Accounting |
| `get_cash_and_payments` | `cash_accounts`, `payments`, `desk` | Accounting |
| `get_rent_and_cash` | `leases`, `cash_accounts`, `desk`; `proposals` and `payments` for rent already paid (`rent_payments` with `covered_due_date`) | Accounting, Facilities |
| `list_proposals` | `proposals`; for approved purchases also `payments`, `vendors`, and `output/drafts.json` (vendor, paid date, `earliest_delivery`, vendor-order draft id) | Boss, Inventory, Accounting |
| `propose_payment` | reads `invoices`, `leases`, `cash_accounts`; writes `proposals` | Accounting |
| `propose_purchase` | reads `vendors`, `invoices`, `inventory`, `pricing`, `cash_accounts`, `desk`; writes `proposals` | Inventory |
| `propose_price_override` | reads `tickets`, `inventory`, `pricing`; writes `proposals` | Inventory |
| `resolve_ticket` | reads `proposals`; writes `tickets` | Boss |
| `draft_customer_reply` | reads `tickets`; writes `output/drafts.json` | Facilities, Customer Service |
| `draft_vendor_message` | reads `vendors`, `invoices`, `desk`; writes `output/drafts.json` | no agent (approved purchases draft the vendor order) |
| `approve_proposal` *(human only)* | writes `proposals`, `payments`, `cash_accounts`, `invoices` or `leases`; reads `vendors`, `desk` | `backend/approvals.py` only |
| `reject_proposal` *(human only)* | writes `proposals` | `backend/approvals.py` only |
| `reset_working_database` *(human only)* | reads `campus_customs.db`; replaces `campus_customs_new.db` | `backend/approvals.py` only |

**Which tools the tickets need.** I checked the database and tickets 101–103 against these tools. They cover everything, so no new tools were needed:
- **101:** a tee in size S, 0 in stock. The vendor is blocked by overdue invoice 501.
- **102:** $2,400 rent, due 2026-09-02.
- **103:** 20 hoodies in size M, 8 in stock, with a discount request.

`mcp_server/README.md` shows which tools each ticket uses.

### Safety guardrails

The shop rules are enforced **in the MCP server's code**, so they hold even if an agent ignores its prompt. The offline checks test each one directly.

| Rule | How it's enforced |
|---|---|
| Use `desk.date_today` for overdue checks | `get_shop_date`, `list_unpaid_invoices` (`days_overdue`), `list_vendors`, and `get_rent_and_cash` all compute against `desk.date_today`, never the computer's clock |
| Vendor lead times come from the vendors table | `list_vendors` returns `lead_days` from `vendors` and earliest delivery = `date_today` + `lead_days`. Purchases report the same. |
| Never order from a vendor with an unpaid invoice | Refused in three places: `propose_purchase`, an order draft in `draft_vendor_message`, and again in `approve_proposal` |
| Payments need human approval | Agents only have `propose_*`. `approve_proposal` needs the backend's secret key and a human name (agent names are refused), and no agent can see it (`HUMAN_ONLY_TOOLS` in `spec.py`). |
| No payment without enough cash | Checked when a payment is proposed **and again when it's approved**. In a test, one purchase was approved and a second one was refused after the first used the cash. |
| Cash only goes out | Amounts must be positive and match the invoice, rent, or qty × unit cost. A price override moves no cash, and revenue is never counted. |
| Messages are drafts, never sent | The draft tools save to `output/drafts.json` with the status `draft - NOT sent`. There is no send tool. |
| Replies reveal no internal details | `draft_customer_reply` **refuses** a reply to a customer, student group, or landlord that mentions internal details. That means a vendor name, or words like vendor, supplier, printer, invoice, unpaid, overdue, cash, balance, bank, unit cost, margin, or "proposal #N". It also covers a $ amount equal to a cash balance or an invoice, and the ticket product's unit cost. The agent gets the reason and has to rewrite the reply. |
| No resolving with open money questions | `resolve_ticket` is refused while any proposal for the ticket is pending |
| Least privilege | Each agent sees only its own MCP tools. Delegation is limited to an allow-list and capped at depth 2. |
| Facts come from tools | Each `Fact` must name its `source_tool`, and prompts forbid made-up numbers. Customers never see costs, margins, vendors, or cash. |
| Audit everything | Each agent-loop step is one record in `output/audit_trail.json`: agent, who called it, depth, step, phase, action, what it said, tools called with arguments, delegations with the task, and tokens. Human decisions are logged too, never with the key. The file is append-only, and the code refuses to overwrite it if it can't be read. |

**What a real business would still need:** logged-in approvers (here, a typed name is trusted), spending limits and a second approver for large payments, protection against prompt injection in ticket text (the Problem 6 defenses only protect the vendor desk agent), and a rate limit on runs.

### Controlling token usage

- **A shared budget per run:** at most 60 model requests and 400,000 tokens across all five agents (`USAGE_LIMITS` in `config.py`). If it's exceeded, the whole run stops.
- **Delegation depth 2:** agents can't bounce work back and forth forever.
- **Least-privilege tools:** each agent's requests only describe its own 4–8 tools, not all 20.
- **Lean prompts:**
  - One clear task per delegation.
  - At most about two delegations per ticket.
  - No repeated lookups.
  - Short structured reports instead of free text.
- **Compact outputs:** tool results are compact. The audit trail stores shortened previews (400 characters).
- **Prompt caching:** each agent's prompt is the same on every call, so the provider can cache it. In Problem 4, caching cut the vendor desk's cost by 84–88%.
- **Smaller runs:** `--tickets 102` runs only the tickets you name.
- **Timeouts:** a model call times out after 120 seconds (with 2 retries) instead of hanging.
- **Measured:** the latest live 3-ticket run used **34 model requests, 48 tool calls, 87,470 input and 8,599 output tokens**. The first run used 32 requests and 82,217 / 8,757 tokens. That's 57% of the request budget but only 24% of the token budget, so the 60-request limit is the one a longer queue would hit first. Even if every input token were billed at the highest rate in `prices.json` (cache write, $0.125/1M), the run would cost under $0.016.

### How to run

From the `HW 6` folder:

```bash
.venv/bin/python -m backend.cli --no-approvals
.venv/bin/python -m backend.cli --review
.venv/bin/python -m backend.cli --reset "Your Name"
```

- **`--no-approvals`** runs the team on all open tickets and leaves its proposals pending.
- **`--review`** asks a human to approve or reject each pending proposal.
- **`--reset "Your Name"`** is a human-only reset of the working database.
- Without `--no-approvals`, the CLI asks for approvals right after the run.

### Test results (`scripts/team_test.py`, saved in `output/team_test.json`)

**Offline checks (25 of 25 passed, no model calls).** Each rule above was tested through the MCP tools on a scratch copy of the original database:
- overdue days for invoice 501 (3, from `desk.date_today`) and vendor lead times from `vendors`;
- purchases and order drafts refused for the vendor with unpaid invoice 501;
- replies with internal details refused: the real leaked ticket 101 sentence ("once our printer is able to accept orders again"), a vendor name, "invoice 501", the $3,400 cash balance, and the $22 hoodie unit cost. A clean customer reply and the real landlord and Yale AI Club drafts are still saved (no false refusals);
- payments as proposals only, with refusals for duplicates, wrong amounts, and negative amounts;
- approval refused without the key or by an agent name;
- the payment math: $3,400 − $2,400 − $840 = $160;
- a restock costing more than the cash refused, and cash re-checked at approval time;
- an at-cost price refused, and an approved discount moving no cash;
- reset limited to a human, and the original database unchanged.

**Live run (9 of 9 rule checks passed).** The latest real team run on tickets 101, 102, and 103, on a fresh scratch copy (run `run-20261019-015051-32b627`, after the draft check was added):
- **Activity:** 94 audit records (Boss 15, Inventory 24, Accounting 22, Facilities 13, Customer Service 18, System 2) and 7 delegations: Boss → Inventory ×2, Accounting, Facilities, Customer Service ×2; Facilities → Accounting.
- **Proposals, all pending:**
  - #1: pay overdue invoice 501, $840.
  - #2: a price of $54.00 for the 8 hoodies on hand (list price $58).
  - #3: pay rent, $2,400. The two payments together leave $160.
- **Restocks:** none was proposed, correctly, because Bulldog Print Co is blocked until invoice 501 is paid.
- **Drafts:** three, to the landlord, Tauhid Zaman, and Yale AI Club. None mentions an internal detail (re-checked with the server's own check). The ticket 101 reply now says only that "we're looking into whether restocking can proceed".
- **The draft check never had to step in.** All 3 draft attempts were saved on the first try, and 0 were refused. So the check was not exercised during this live run; its refusals are proven by the offline checks above.
- **Unchanged:** no cash moved, no ticket was resolved, and every ticket is `waiting_on_human`, which is right for a first run before any human decision.

**Problem found in the first live run, now fixed:** in run `run-20261019-014357-ed9588`, the ticket 101 customer draft said "We'll reconsider restocking once our printer is able to accept orders again". That hinted at an internal vendor problem, and only the prompt forbade it. `draft_customer_reply` now refuses such replies in code, and the Customer Service and Facilities prompts say so.

**Limits of the draft check:** it is a word and number filter. It can't catch a paraphrase that uses none of its words (for example "our supply partner is behind") or a cost written without a `$` sign. The prompt rule is still the first line of defense.

**Real working database:** the full run on `data/campus_customs_new.db` is in [Full run (Problem 9)](#full-run-problem-9).

**Fix: ticket 102 no longer gets stuck after the rent is paid** (`scripts/rent_rerun_test.py`, results in `output/rent_rerun_test.json`).
- **The bug:** paying rent moves the lease's `next_due` forward a month. On a second run of ticket 102, the agents sometimes saw the notice's September 2 date not matching the new October 2 `next_due` and reported the ticket *Blocked*, because "the payment history does not say which period it covered". It happened in 1 of 3 second runs observed before the fix (the dashboard test). The 2 scripted trials before the fix happened to pass.
- **The fix, in data and prompts:**
  - `approve_proposal` now records the due date each rent payment covered.
  - `get_rent_and_cash` returns `rent_payments` with `covered_due_date`.
  - Facilities checks that first and reports a covered notice as "already paid", with no blocker and no second payment.
  - Accounting never re-proposes a covered due date.
  - The Boss resolves an already-paid notice.
- **Results:** 4 of 4 live trials after the fix were resolved on the second run, with one rent proposal and checking at $1,000 (no double payment). Every second-run summary says the payment covered the September 2 due date. The second run also got cheaper: 8–9 model requests and about 21–24k input tokens, against 12 requests and about 30k before.
- **Limits:** the model still varies run to run, so 4 trials show the fix works but don't prove the bug can never return. The offline check "paid rent records the due date it covered" tests the new data path in code on every run of `scripts/team_test.py`.

---

## Dashboard (Problem 8)

A React + Vite + TypeScript dashboard (`frontend/`) talks to a FastAPI backend (`backend/main.py`, adapted from HW 5) at http://localhost:8000. All data comes from the real project through the MCP server; the frontend has no hardcoded data. Design decisions and test results are in `output/design.md`.

### How to start it

From the `HW 6` folder, in two terminals. The first starts the API:

```bash
.venv/bin/uvicorn backend.main:app --port 8000
```

The second starts the dashboard:

```bash
npm --prefix frontend run dev
```

Then open http://localhost:5173. CORS allows `localhost:5173` and `127.0.0.1:5173`. Add others with `FRONTEND_ORIGINS`.

### API routes (`backend/main.py`)

| Route | What it does |
|---|---|
| `GET /api/health` | API status, the model, the database file in use, and the active run (if any) |
| `GET /api/tickets` | All tickets with `open`/`resolved` status, pending proposal ids, and the latest run |
| `GET /api/tickets/{id}` | Every field of one ticket |
| `POST /api/tickets/{id}/run` | Starts the agent team on one ticket in the background. Refused (409) if the ticket is resolved or another run is going. |
| `POST /api/tickets/{id}/resolve` | A named human marks a ticket resolved. Refused while a proposal for it is pending. |
| `GET /api/runs`, `GET /api/runs/{run_id}` | Run status (`running`/`finished`/`failed`), with the Boss's report and token usage |
| `GET /api/events?ticket_id=…` | Agent-loop steps from the audit trail: agent, action, tools called, delegations, final reports |
| `GET /api/approvals?status=pending` | Proposed payments, purchases, and prices |
| `POST /api/approvals/{id}/approve` | A named human approves. **The only route that moves cash.** The MCP server re-checks cash and the rules first. |
| `POST /api/approvals/{id}/reject` | A named human rejects, with an optional note. No cash moves. |
| `GET /api/cash` | Checking balance from `cash_accounts`, the pending total, the balance if all are approved, and recent payments |
| `GET /api/drafts?ticket_id=…` | Drafts saved by the agents (never sent). New in HW 6. |
| `POST /api/reset` | A named human restores the working database from the original. Drafts and the audit trail are kept. |

### Tests

- **`scripts/api_test.py`:** 23 of 23 route checks passed on a scratch copy, with no model calls.
- **Browser tests** of the dashboard with `npm run dev`: see `output/design.md`. They covered a live agent run, approve, refuse, reject, a price override, resolve, offline, and reset.

---

## Full run (Problem 9)

All three tickets ran through the real system: React dashboard → FastAPI → five-agent team → MCP server → `data/campus_customs_new.db`. All results are generated from the database and the audit trail by `scripts/problem9_report.py` and `scripts/fill_desk_tickets.py`.

**Start**
- **Reset:** on 2026-10-19 at 07:54:38, through the human-only reset, signed "Madina Muratova (via Claude Code)". It is audit record 851. The working copy was then byte-identical to the original.
- **Starting checking balance:** **$3,400.00**.
- **Approvals:** you chose to have me approve proposals signed "Madina Muratova (via Claude Code)". The server still checked cash and the rules on every one.

| Ticket | Runs (the Boss's status each time) | Human approvals | Final status |
|---|---|---|---|
| 101 tee order | 4: waiting → waiting → **blocked** → handled | #1 pay invoice 501, −$840.00; #2 restock 1 × CC-TEE-WHITE size S, −$8.00 | **resolved** by the Boss (`resolve_ticket`, run 4) |
| 102 rent notice | 2: waiting → handled | #3 rent for lease 1, −$2,400.00 (it covered the 2026-09-02 due date) | **resolved** by the Boss (run 2) |
| 103 bulk hoodies | 3: waiting → **blocked** → handled | #4 price: 8 × CC-HOOD-NAVY size M at $52.00 (no cash moves). The 12-hoodie restock was refused by the server 3 times: "Not enough cash: checking has 152.00, purchase needs 264.00." | **resolved** by the Boss (run 3) |

**Cash:** $3,400.00 − $840.00 − $8.00 − $2,400.00 = **$152.00**. That equals `cash_accounts` in the database. The balance never went below zero, and every payment has a named human's approval.

**Fixes made during the run.** Two runs ended *blocked*. You chose to fix both gaps and rerun once:
1. **Ticket 101:** no agent tool showed the vendor order that approving purchase #2 had drafted, so the agents treated the restock as unconfirmed. Fix: `list_proposals` now shows an approved purchase's vendor, paid date, `earliest_delivery`, and vendor-order draft id, and the Inventory prompt treats that as ordered.
2. **Ticket 103:** the Boss didn't treat the cash-refused restock as a final answer, although its prompt already said to. Fix: the Boss prompt now says plainly that a refused restock or a drafted vendor order is not a blocker.

On their reruns, both tickets were resolved by the Boss. No ticket was marked resolved by hand.

**Usage across the 9 runs:** 126 model requests, 162 tool calls, 367,501 input and 29,389 output tokens. Even if every input token were billed at the highest rate in `prices.json`, that would be under $0.061.

**Verified against the database and logs** (all 9 checks passed, saved in `resolved_tickets.json`):
- Ticket statuses match the database, and each resolved ticket was resolved by the Boss's `resolve_ticket` (ok=true in the audit trail).
- No proposal is still pending.
- Every payment comes from a proposal a named human approved, and every approval is in the audit trail.
- The cash reconciles, the balance never went below zero, and cash only went out.
- Every draft is not sent.

| Output | What it contains |
|---|---|
| `output/desk_tickets.html` | HW 5's Expected plans, with HW 6's real Actual sections (agents, delegations, MCP tools, refusals, approvals, fixes, final replies, plan vs. actual) and the Cash tab. Reflection says "Coming later". |
| `output/resolved_tickets.json` | Per ticket: final status, who resolved it, the outcome, each run, agents, delegations, tools, each agent's contributions, server refusals, human approvals, drafts, and the final reply. Also the cash reconciliation, the fixes, the usage, and the verification. |
| `output/resolved_board.html` | A standalone page (screenshots embedded, opens by double-click): the cash summary, the payments, the verification, and one card per ticket with its dashboard screenshot |
| `output/screenshots/ticket_10{1,2,3}_resolved.jpg` | The dashboard right after each ticket was resolved |
| `output/audit_trail.json` | Records 851–1221 are this run: the reset, 366 agent-loop records across the 9 runs, and 4 approvals. The 850 earlier records are kept. |
| `output/drafts.json` | 10 drafts: 9 replies and 1 vendor order. None was sent. |
