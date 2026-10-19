# Campus Customs Dashboard: Design (Problem 8)

The dashboard is where a shop manager runs tickets through the five-agent team, watches the agents work, and makes the money decisions the agents aren't allowed to make.

## Technology and data

| Part | Choice |
|---|---|
| Frontend | React 19 + Vite + TypeScript in `frontend/`, started with `npm run dev` (http://localhost:5173) |
| Backend | FastAPI in `backend/main.py` at http://localhost:8000, adapted from HW 5's tested API. CORS allows the Vite dev server. |
| Data | Every number, name, and status comes from the API. The API reads it through the MCP server from `data/campus_customs_new.db`, `output/audit_trail.json`, and `output/drafts.json`. The frontend contains **no hardcoded shop data**. |
| Code | About 10 small files: `api.ts` (every API call), `types.ts`, `usePolling.ts`, `App.tsx`, and five components (`TicketList`, `TicketPanel`, `ActivityFeed`, `ApprovalsPanel`, `CashPanel`) |

## Layout

Three columns follow the order of the work: **choose → watch → decide**.

```
┌ Header: shop date (desk.date_today) · model · database file · API status · Reset data ┐
│ Tickets         │ Selected ticket                         │ Cash                    │
│  #101 Open      │  details from the tickets table         │  checking balance       │
│  #102 Resolved  │  [Run agent team]                       │  waiting for approval   │
│  #103 1 waiting │  Agent activity (live)                  │  payments made          │
│                 │  What happened (Boss's report)          │ Approvals               │
│                 │  Drafts (not sent)                      │  your name · cards      │
└─────────────────┴─────────────────────────────────────────┴─────────────────────────┘
```

Below 1,100 px wide, the columns stack in the same order.

## Visual style

The look is Scandinavian-inspired, following the project's `AGENTS.md`: a warm off-white background, white panels with hairline borders, generous spacing, the system font, and no gradients or decoration. Color is used only to carry meaning, and each meaning gets one muted color:

| Color | Meaning |
|---|---|
| Slate blue | Primary actions (Run, Approve) |
| Sage | Resolved, paid, balance just updated |
| Ochre | Waiting for a human |
| Teal-grey | Agents working |
| Brick | Errors and refusals |

Every status also has a text label, so nothing depends on color alone. Money uses tabular figures, so amounts line up.

## Main UI decisions

**1. Agent activity shows the real agent loop.**
- **Data:** the feed reads `/api/events`, the same audit trail the agents write to. Each row is one agent-loop step: the agent (each with its own muted chip color), what it did, and when.
- **Tools:** tool calls appear as code chips with their arguments, e.g. `get_rent_and_cash(lease_id=1)`.
- **Delegation:** a handoff appears as "→ accounting: <task>", and steps are indented by delegation depth (Boss → specialist → peer), so you can see who asked whom.
- **Reports:** each agent's final report is quoted.
- **Hidden:** bookkeeping steps (sending the task to the model) are left out to keep the feed readable.
- **Refresh:** during a run, the feed refreshes every 1.5 seconds and scrolls to the newest step.

**2. "What happened" is the Boss's own report, labelled with its time.**
- **Content:** a status (Handled / Waiting on a human / Blocked), the summary, what the agents did, what needs a human, and the token usage.
- **Time label:** "Boss's report from the run at 02:24:29". After you approve something, the old report could otherwise look current.

**3. Resolved status comes only from the database.**
- **Badges:** the ticket list and the ticket header both show `Resolved` when `tickets.status` says so. That happens when the Boss calls `resolve_ticket`, or when a person clicks **Mark resolved**; the server refuses either one while a proposal is pending.
- **Resolved tickets:** "Run agent team" is switched off with the reason shown.

**4. Money needs a human, and the UI never pretends.**
- **Each proposal shows:**
  - what it is (pay invoice #501, pay rent, buy 300 mugs, sell 8 hoodies at $54.00);
  - the amount, or **"No cash moves"** for a price;
  - **checking before → after**, with a warning if there isn't enough cash;
  - the agent's reason and who proposed it.
- **Approve and Reject need a typed name.** The name is saved in the browser only, and the server refuses agent names.
- **Success is reported only after the server confirms it.** While a request is in flight, the button says "Waiting for the server…". There are no optimistic updates. The success message uses the server's new balance ("Checking is now $1,000.00"), and the cash panel re-reads `cash_accounts` and flashes "updated".
- **Refusals show the server's own reason** on the card ("Not enough cash: checking has 1000.00, this needs 1050.00"). The proposal stays pending, and the balance doesn't move.

**5. Safe defaults for everything else.**
- **One run at a time:** the server enforces it. While a run is going, every Run button and Reset are off, with a short explanation.
- **Drafts are labelled "Draft, not sent".**
- **Reset needs a name and a confirmation** that explains what is kept (drafts, the audit trail).
- **If the API is down:** a banner shows the exact start command, the last data received is dimmed so it isn't taken for live numbers, every action is off, and the page reconnects on its own.
- **The header names the database file in use,** so a test copy can't be mistaken for the real books.

**6. Polling, not WebSockets.** Plain `fetch` every 1.5–5 seconds is easy to follow and fast enough for a handful of tickets.

## Accessibility

- **Controls:** real `<button>` elements with visible focus outlines.
- **Screen readers:** `aria-live` regions for the activity feed and notices, and `role="alert"` on errors.
- **Labels:** text labels next to every color.

## How it was tested

- **API:** `scripts/api_test.py` runs 23 route checks on a scratch copy of the database, with no model calls. All passed.
- **Dashboard:** tested with `npm run dev` in the browser, against an API pointed at a scratch copy of the original database (through the `CAMPUS_CUSTOMS_DB`, `CAMPUS_CUSTOMS_DRAFTS`, and `CAMPUS_CUSTOMS_AUDIT` test variables), so test approvals never touched the real books.
  - **Run ticket 102:** the live feed showed the Boss → Facilities → Accounting delegation and the tool calls, and the Boss's report and the landlord draft appeared.
  - **Approve with no name:** blocked in the browser, nothing sent.
  - **Approve the rent:** the server confirmed it, and the balance went $3,400 → $1,000.
  - **Approve a $1,050 purchase:** the server refused it for lack of cash. The reason was shown, and the balance didn't move.
  - **Reject with a note:** recorded.
  - **Approve a price override:** "no cash moved", and the balance stayed the same.
  - **Mark resolved:** both badges changed, and Run was disabled.
  - **API stopped:** the banner appeared, buttons switched off, and the page reconnected by itself when the API came back.
  - **Reset:** asked for confirmation, then brought everything back to $3,400 and three open tickets.
  - **Console:** no JavaScript errors or React warnings, only the expected network errors from the offline test and the 409 from the refused purchase.
- **Real data:** the dashboard showed `data/campus_customs_new.db` correctly (3 open tickets, $3,400). No agents were run and nothing was approved, so the real database, `audit_trail.json`, and drafts were not changed.

### Bugs found and fixed while testing

- **Flicker after Run:** for about a second after you clicked Run, the panel still offered "Run again" and "Mark resolved". A run you just started now counts as running until the server reports on it.
- **Slow switch to "finished":** the panel waited up to 3 seconds for the health check. It now trusts the run's own status.
- **Stuck "updated" flash:** the cash panel's flash never switched off, because each refresh restarted its timer. It's now tied to the balance value.
- **Stale numbers offline:** the last data stayed at full strength when the API was down. It's now dimmed.
- **Wrong database label:** `/api/health` always named the working database, even on a test copy. It now reports the file actually in use.

## Known limits

- **Run reports live in the API's memory.** After an API restart, "What happened" falls back to the Boss's final words from the audit trail.
- **The approver's name is typed, not logged in**, the same as in the backend. A real shop would need sign-in and spending limits.
- **Agent issue seen in testing, now fixed:** during the dashboard test, a second run on ticket 102 marked it *Blocked* after a human paid the rent. Paying had moved the lease's next due date, and the agents couldn't tell which period the payment covered. The dashboard showed this accurately, and a person resolved the ticket with **Mark resolved**. The backend now records which due date each rent payment covered, and the agents use it. In 4 of 4 live trials since, the Boss resolved ticket 102 on its own (details in `output/harness.md`).
