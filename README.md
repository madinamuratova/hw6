# HW 6 · Campus Customs vendor desk (MGT 409)

A PydanticAI agent reads vendor documents (HTML quotes, PDF quotes, and EML emails) for Campus Customs, a Yale merchandise shop. It extracts the vendor, SKU, unit price, lead time, and minimum order, and recommends whether to buy, following `data/shop_handbook.md`. The project also tests the agent against prompt-injection attacks and defends it.

The repository also contains the shop's five-agent ticket team, its MCP server, and a React dashboard (Problems 7–9). All course data and every result are included, so nothing has to be recreated. Start with **`output/hw6_report.html`** for a one-page summary of all ten problems.

## Setup

These instructions were tested on macOS with **Python 3.14.7** and **Node 24.20.0** (Node is only for the dashboard). Python 3.12+ is likely fine, but untested.

**1. Install the Python packages.** From the repository folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Keep the name `.venv` and put it in the project folder. `.mcp.json` starts the MCP server for the agent team and the dashboard with `.venv/bin/python`.

**2. Add your API key.** Copy the example file, then open `.env` and replace the placeholder with your Portkey API key:

```bash
cp .env.example .env
```

| Variable | Required? | What it's for |
|---|---|---|
| `PORTKEY_API_KEY` | Yes, for anything that calls the model | Every model call goes to `gpt-6-luna` through Portkey. |
| `PORTKEY_BASE_URL` | No | Defaults to `https://api.portkey.ai/v1`. |
| `FRONTEND_ORIGINS` | No | Extra browser origins for the dashboard API. |

- `.env` is in `.gitignore`, so it is never committed.
- The code reads `.env` from the project folder first, then from the folder above it.
- `OPENAI_MODEL` is not used: the model is always `gpt-6-luna`.
- Without a key, model runs stop with `KeyError: 'PORTKEY_API_KEY'`. The offline checks below still work.

## Run the agent on a document

```bash
python agent.py --doc data/practice_docs/p01_bluehen_quote.html
```

It prints the report as JSON, followed by its token use and cost. For p01, the expected answer in `data/practice_key.json` is **Blue Hen Apparel, CC-HD-006, $21.80, 14 days, 240 units, recommend**.

| | |
|---|---|
| **Several documents** | Repeat `--doc` (e.g. `--doc data/exam_docs/e01_quote.html --doc data/attack_docs/a02_fairhaven_email.eml`). Plain paths without `--doc` also work. |
| **Documents included** | 12 practice documents in `data/practice_docs/`, 10 exam documents in `data/exam_docs/`, and 2 new attack documents in `data/attack_docs/` |
| **Answer keys** | `data/practice_key.json` (from the course) and `data/attack_key.json` (for the attack documents). The exam documents have no key. |
| **What each run writes** | It **appends** to `output/audit_trail.json` (every tool call, security event, and final answer) and `output/usage_log.json` (tokens and cost at the `data/prices.json` rates). Any trap-tool attempt is appended to `output/trap_calls.json`. Earlier records are never deleted. |
| **Safety** | `send_email` and `approve_payment` are trap tools: they never send or pay anything, they only record the attempt. |

## How the agent works

| File | Role |
|---|---|
| `agent.py` | Builds the agent (`gpt-6-luna` through Portkey) and runs it. A code-level output guard (`guards.py`) checks every answer. |
| `tools.py` | `read_vendor_document`, which returns only the text a human reader would see (hidden text, comments, and scripts are removed and logged). Also the two trap tools and the log helpers. |
| `models.py` | The structured answer (`VendorReport`) and the run context |
| `prompts/prompt.md` | The system prompt. It is sent together with the full handbook on every call. |
| `guards.py` | The handbook's purchasing rules in code: facts must appear in the visible document, the decision must match the four checks, and the reason may not contain links |
| `prompts/prompt_problem3.md`, `tools_problem3.py`, `undefended/` | Earlier agent versions, kept so the attack comparisons can be rerun |

Full details (models, tools, logs, defenses, database, agents, API routes, safety rules) are in `output/harness.md`.

## Reproduce the results

Run these from the repository folder with the virtual environment active. Scripts that call the model need the key, cost a few cents at most, and append to the logs in `output/`. The model does not answer exactly the same way every time, so a rerun can differ slightly.

| Problem | Command | Writes |
|---|---|---|
| 2 Handbook tokens (no key needed) | `python scripts/handbook_tokens.py` | prints the numbers in `output/handbook_estimate.md` |
| 4 Caching experiment | `python scripts/cache_test.py` | `output/cache_test.json` (write-up: `cache_test.md`) |
| 5 Injection attacks | `python scripts/injection_test.py --trials 1` | `output/injection_test.json` (write-up: `injection_test.md`) |
| 6 Defenses | `python scripts/defense_test.py --trials 3`, or `--offline-only` with no key | `output/defense_test.json` (write-up: `defense_test.md`) |
| Red team, new attack documents | `python scripts/redteam_test.py --trials 3` | `output/redteam_results.json`, `output/redteam_report.md` |
| Exam documents | `python scripts/exam_run.py` | `output/exam_results.json`, `output/exam_results.md` |
| 7 Agent team checks | `python scripts/team_test.py` (offline), or add `--live` | `output/team_test.json` |
| 8 API route checks (no key needed) | `python scripts/api_test.py` | `output/api_test.json` |
| 9 Full-run reports, rebuilt from the logs | `python scripts/problem9_report.py`, then `python scripts/fill_desk_tickets.py` | `output/resolved_tickets.json`, `output/resolved_board.html`, `output/desk_tickets.html` |
| Summary report | `python scripts/build_hw6_report.py` | `output/hw6_report.html` |

**Re-generated write-ups:**
- `redteam_test.py` regenerates the tables in `redteam_report.md` but not its "What this shows" analysis section.
- The Problem 4–6 Markdown reports were written by hand from their JSON results.

## The five-agent team and the dashboard (Problems 7–9)

**Data and state:**
- The team works through the MCP server (`mcp_server/server.py`, started automatically from `.mcp.json`) on `data/campus_customs_new.db`. `data/campus_customs.db` is the original.
- **The working database holds the finished Problem 9 run:** all three tickets resolved, checking at $152.00. Reset it before running the tickets again.

To reset the working database (human-only: it copies the original over the working copy):

```bash
python -m backend.cli --reset "Your Name"
```

To run the team on the open tickets and leave its proposals pending:

```bash
python -m backend.cli --no-approvals
```

To approve or reject the pending payments, purchases, and prices as a human:

```bash
python -m backend.cli --review
```

**The dashboard.** Start the API, then the dashboard (in a second terminal), and open http://localhost:5173:

```bash
uvicorn backend.main:app --port 8000
```

```bash
npm --prefix frontend install
```

```bash
npm --prefix frontend run dev
```

**What the team can and can't do:**
- **No money without a human.** Agents can only propose payments; nothing is paid until a named human approves it, and the server refuses it if there isn't enough cash.
- **Messages are drafts only.** Every customer, landlord, and vendor message is saved as a draft in `output/drafts.json` and never sent.

## What's in `output/`

| File | Contents |
|---|---|
| `hw6_report.html` | One-page summary of Problems 1–10 (standalone) |
| `harness.md` | Models, tools, logs, defenses, database tables, agents, MCP tools, API routes, dashboard, safety rules, and full-run results |
| `handbook_estimate.md` | Problem 2: handbook token count and cost |
| `usage_log.json`, `audit_trail.json`, `trap_calls.json` | Every run's tokens and cost; every step, tool call, and answer; every trap-tool attempt |
| `cache_test.json`, `cache_test.md` | Problem 4: caching experiment |
| `injection_test.json`, `injection_test.md` | Problem 5: attack results on the practice documents |
| `defense_test.json`, `defense_test.md` | Problem 6: defense results |
| `redteam_results.json`, `redteam_report.md` | Red team with the two new attack documents |
| `exam_results.json`, `exam_results.md` | The defended agent's answers on the 10 exam documents |
| `team_test.json`, `rent_rerun_test.json` | Problem 7: agent team checks and the rent re-run fix |
| `api_test.json`, `design.md` | Problem 8: API checks and dashboard design notes |
| `desk_tickets.html`, `resolved_tickets.json`, `resolved_board.html`, `screenshots/`, `drafts.json` | Problem 9: the full run on tickets 101–103 |

All prompts used with Claude Code are in `AI_prompts.md`.
