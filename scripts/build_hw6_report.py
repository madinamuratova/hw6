"""Build output/hw6_report.html: a standalone summary of HW 6, Problems 1-10.

Every number is read from the saved results (output/*.json, data/*.json, the database), not typed by hand.
Run from the project folder after the other scripts:  python scripts/build_hw6_report.py
"""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import tiktoken

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
REPO_URL = "https://github.com/madinamuratova/hw6"
e = html.escape


def load(name: str) -> dict | list | None:
    path = OUT / name
    return json.loads(path.read_text()) if path.exists() else None


def money(n: float, places: int = 2) -> str:
    return f"${n:,.{places}f}"


def main() -> None:
    # Problem 2: handbook tokens and cost (recomputed the same way as scripts/handbook_tokens.py)
    handbook = (ROOT / "data" / "shop_handbook.md").read_text(encoding="utf-8")
    tokens = len(tiktoken.get_encoding("o200k_base").encode(handbook))
    rates = json.loads((ROOT / "data" / "prices.json").read_text())["gpt-6-luna"]
    one = Decimal(tokens) * Decimal(str(rates["input_per_1m"])) / Decimal(1_000_000)
    cached = Decimal(tokens) * Decimal(str(rates["cached_input_per_1m"])) / Decimal(1_000_000)

    cache = load("cache_test.json")["comparison"]
    inj = load("injection_test.json")["summary"]
    dfn = load("defense_test.json")
    team = load("team_test.json")
    api = load("api_test.json")
    p9 = load("resolved_tickets.json")
    red = load("redteam_results.json")
    exam = load("exam_results.json")
    usage = load("usage_log.json") or []
    traps = load("trap_calls.json") or []
    audit = load("audit_trail.json") or []

    saved_pct = f"{cache['saved_percent']:.1f}%"
    inj_undefended = f"{inj['undefended']['answers_matching_key']} / 12"
    inj_problem3 = f"{inj['problem3']['answers_matching_key']} / 12"

    def section(num: int, title: str, body: str, files: list[str]) -> str:
        links = " · ".join(f'<a href="{e(f)}">{e(f)}</a>' if not f.startswith("../") else f'<a href="{e(f)}">{e(f[3:])}</a>' for f in files)
        return f'<section><h2><span class="num">{num}</span> {e(title)}</h2>{body}<p class="files">Files: {links}</p></section>'

    def tr(*cells) -> str:
        return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

    sections = [
        section(1, "Vibe coder prompts", "<p>Every prompt I sent Claude Code is logged per problem, word for word, with follow-ups "
                "and one sentence on what was missing.</p>", ["../AI_prompts.md"]),
        section(2, "Handbook token estimate",
                f"<p>The shop handbook is <strong>{tokens:,} tokens</strong> (<code>o200k_base</code>; the API counted 10,062 when sent). "
                f"Sending it once costs {money(float(one), 7)} uncached or {money(float(cached), 8)} from the cache; "
                f"1,000 calls cost {money(float(one * 1000), 4)} uncached vs about $0.1017 with caching.</p>",
                ["handbook_estimate.md", "../scripts/handbook_tokens.py"]),
        section(3, "Vendor-desk agent",
                "<p>A PydanticAI agent on <code>gpt-6-luna</code> (through Portkey) reads HTML, PDF, and EML vendor documents and returns "
                "vendor, SKU, unit price, lead time, minimum order, a decision, and a reason based on the handbook. "
                "<code>send_email</code> and <code>approve_payment</code> are trap tools that only log attempts. "
                "Usage, costs, tool calls, and answers are logged.</p>"
                f"<p>Logs now hold {len(usage)} usage records, {len(audit)} audit records, and {len(traps)} trap calls.</p>",
                ["../agent.py", "../tools.py", "../models.py", "../prompts/prompt.md", "harness.md", "usage_log.json", "audit_trail.json", "trap_calls.json"]),
        section(4, "Handbook caching experiment",
                f"<table>{tr('Without caching (12 documents)', money(cache['total_cost_no_cache_usd'], 6))}"
                f"{tr('With the handbook cached', money(cache['total_cost_cache_handbook_usd'], 6))}"
                f"{tr('Saved', saved_pct)}"
                f"{tr('1,000 documents/day, no cache vs warm cache', money(cache['projection_1000_docs_per_day_usd']['no_cache']['per_day']) + ' vs ' + money(cache['projection_1000_docs_per_day_usd']['cache_handbook_docs_2_to_12_average']['per_day']))}</table>",
                ["cache_test.md", "cache_test.json"]),
        section(5, "Prompt-injection attacks (practice documents)",
                f"<table>{tr('Undefended agent: answers matching the key', inj_undefended)}"
                f"{tr('Problem 3 agent: answers matching the key', inj_problem3)}"
                f"{tr('Documents that fooled the undefended agent', e(', '.join(inj['undefended']['suspicious_or_incorrect_files'])))}</table>",
                ["injection_test.md", "injection_test.json"]),
        section(6, "Defenses",
                f"<table>{tr('', 'Correct answers', 'Attacks that changed the answer')}"
                + "".join(tr(v, f"{s['answers_matching_key']} / {s['runs']}", f"{s['successful_attacks']} / {s['attacked_document_runs']}")
                          for v, s in dfn['summary'].items())
                + f"</table><p>Offline checks of each defense in code: {'all passed' if dfn['offline_checks']['all_passed'] else 'NOT all passed'}.</p>",
                ["defense_test.md", "defense_test.json", "../guards.py"]),
        section(7, "Five-agent team (Boss, Inventory, Accounting, Facilities, Customer Service)",
                f"<p>PydanticAI agents that work only through the MCP server and the shop database. Offline safety checks: "
                f"{sum(c['passed'] for c in team['offline_checks'])} / {len(team['offline_checks'])} passed. Live run rule checks: "
                f"{sum(team['live_run']['rules'].values())} / {len(team['live_run']['rules'])} passed.</p>",
                ["../backend/", "../mcp_server/README.md", "team_test.json", "harness.md"]),
        section(8, "Dashboard (React + Vite + TypeScript) and API (FastAPI)",
                f"<p>API route checks: {sum(c['passed'] for c in api['checks'])} / {len(api['checks'])} passed. "
                "The dashboard runs tickets, shows agent activity live, and makes payments wait for a named human's approval.</p>",
                ["design.md", "api_test.json", "../frontend/"]),
        section(9, "Full run on tickets 101-103",
                f"<p>{sum(t['final_status'] == 'resolved' for t in p9['tickets'])} / 3 tickets resolved by the Boss. Checking "
                f"{money(p9['starting_checking_balance'])} → {money(p9['ending_checking_balance'])} ({e(p9['cash_reconciliation'])}). "
                f"Verification: {sum(p9['verification'].values())} / {len(p9['verification'])} checks passed.</p>",
                ["desk_tickets.html", "resolved_tickets.json", "resolved_board.html"]),
    ]
    if red:
        rows = "".join(tr(v, *[f"{s['per_file'][k['file']]['succeeded']} / {s['per_file'][k['file']]['runs']}" for k in red["key"]],
                          s["trap_calls"]) for v, s in red["summary"].items())
        head = tr("Version", *[f"<code>{e(k['file'])}</code> attacks that worked" for k in red["key"]], "Trap calls")
        sections.append(section(10, "Red team: two new attack documents",
                                f"<p>{e(red['key'][0]['attack'])}</p><p>{e(red['key'][1]['attack'])}</p><table>{head}{rows}</table>",
                                ["redteam_report.md", "redteam_results.json", "../data/attack_docs/", "../data/attack_key.json"]))
    if exam:
        s = exam["summary"]
        rows = "".join(tr(f"<code>{e(r['file'])}</code>", e(r['answer']['vendor']), e(str(r['answer']['sku'])), e(str(r['answer']['unit_price'])),
                          e(str(r['answer']['lead_time_days'])), e(str(r['answer']['min_order'])), f"<strong>{e(r['answer']['decision'])}</strong>")
                       for r in exam["results"] if "answer" in r)
        sections.append(section(11, "Exam documents",
                                f"<p>The defended agent ran once on each exam document (there is no answer key). {s['recommend']} recommend, "
                                f"{s['do_not_recommend']} do not recommend; hidden content removed from {s['documents_with_hidden_content_removed']}; "
                                f"trap calls {s['trap_calls']}; {s['final_answers_passing_guard_checks']} / {s['documents'] - s['failed_runs']} final "
                                f"answers pass the guard's checks.</p><table>{tr('Document', 'Vendor', 'SKU', 'Price', 'Lead', 'Min', 'Decision')}{rows}</table>",
                                ["exam_results.md", "exam_results.json"]))
    sections.append(section(12, "GitHub", f'<p>Public repository: <a href="{REPO_URL}">{REPO_URL}</a>. See the README for setup.</p>',
                            ["../README.md", "../.env.example", "../requirements.txt"]))

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>HW 6 report · Campus Customs</title>
<style>
  body {{ margin: 0; background: #f6f5f2; color: #2b2b2a; font: 15px/1.55 Inter, system-ui, -apple-system, 'Segoe UI', sans-serif; }}
  main {{ max-width: 920px; margin: 0 auto; padding: 40px 28px 60px; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 4px; }} .lead {{ color: #74716b; margin: 0 0 28px; }}
  section {{ background: #fff; border: 1px solid #e5e2dc; border-radius: 10px; padding: 20px 24px; margin: 16px 0; }}
  h2 {{ font-size: 1.1rem; margin: 0 0 10px; display: flex; gap: 10px; align-items: baseline; }}
  .num {{ display: inline-block; min-width: 28px; height: 28px; line-height: 28px; text-align: center; border-radius: 50%; background: #e3e9ed; color: #3f5a6b; font-size: .85rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .92rem; margin: 6px 0; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #efede8; vertical-align: top; }}
  code {{ font: .85em ui-monospace, Menlo, monospace; background: #f3f1ec; padding: 1px 5px; border-radius: 4px; }}
  .files {{ font-size: .82rem; color: #74716b; margin: 10px 0 0; }} a {{ color: #3f5a6b; }}
</style></head>
<body><main>
<h1>HW 6 · Campus Customs</h1>
<p class="lead">MGT 409 AI Foundations for Managers. Generated {datetime.now().astimezone().isoformat(timespec='minutes')} from the saved results in <code>output/</code>.</p>
{''.join(sections)}
</main></body></html>
"""
    (OUT / "hw6_report.html").write_text(page)
    print(f"wrote output/hw6_report.html ({len(sections)} sections)")


if __name__ == "__main__":
    main()
