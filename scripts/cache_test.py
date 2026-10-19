"""Problem 4: token usage with and without caching the handbook.

Runs all 12 practice documents through the vendor-desk agent twice. Both runs use the same
model, prompt, handbook, tools, user message, and output type (agent.build_agent). The only
difference is one short tag added at the end of the instructions:

  no_cache        a new random tag on every model request, so no request can reuse a cached prompt
  cache_handbook  one fixed tag for the whole run (new for this test, so the cache starts empty),
                  so requests after the first can reuse the cached prompt + handbook

The API's own cache-off setting (openai_prompt_cache_options mode="explicit") is ignored on our
Portkey/Azure route, which is why the tag is used instead.

Run from the HW 6 folder:  .venv/bin/python scripts/cache_test.py
Writes output/cache_test.json. Every run is also appended to output/audit_trail.json and
output/usage_log.json, like any other agent run.
"""

import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic_ai.messages import ModelResponse  # noqa: E402

from agent import MODEL_NAME, audit_records, build_agent, load_instructions, usage_record  # noqa: E402
from models import AgentDeps  # noqa: E402
from tools import DATA_DIR, HW_DIR, OUTPUT_DIR, TRAP_LOG, append_json, now  # noqa: E402

PRACTICE_DIR = DATA_DIR / "practice_docs"
KEY_FIELDS = ("vendor", "sku", "unit_price", "lead_time_days", "min_order", "decision")
MILLION = Decimal(1_000_000)
PRICES = json.loads((DATA_DIR / "prices.json").read_text())
RATES = {k: Decimal(str(v)) for k, v in PRICES[MODEL_NAME].items()}
DOCS_PER_DAY = 1000


def new_tag() -> str:
    return f"Request tag: {uuid.uuid4().hex[:12]}"


def cost(uncached: int, cached: int, write: int, output: int) -> dict:
    parts = {
        "uncached_input": uncached * RATES["input_per_1m"] / MILLION,
        "cached_input": cached * RATES["cached_input_per_1m"] / MILLION,
        "cache_write": write * RATES["cache_write_per_1m"] / MILLION,
        "output": output * RATES["output_per_1m"] / MILLION,
    }
    parts["total"] = sum(parts.values())
    return parts


def token_counts(usage) -> dict:
    return {
        "input_tokens": usage.input_tokens,
        "uncached_input_tokens": usage.input_tokens - usage.cache_read_tokens - usage.cache_write_tokens,
        "cached_input_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "output_tokens": usage.output_tokens,
    }


def as_float(costs: dict) -> dict:
    return {k: float(v) for k, v in costs.items()}


def run_document(agent, path: Path, key: dict) -> dict:
    """Same user message and logging as agent.review(); also keeps the per-request usage."""
    document = path.relative_to(HW_DIR).as_posix()
    run_id = uuid.uuid4().hex[:8]
    traps_before = len(json.loads((OUTPUT_DIR / TRAP_LOG).read_text()))
    try:
        result = agent.run_sync(f"Review the vendor document at {document} and return your report.",
                                deps=AgentDeps(run_id=run_id, document=document))
    except Exception as exc:
        append_json("audit_trail.json", [{"timestamp": now(), "run_id": run_id, "document": document,
                                          "event": "run_error", "error": f"{type(exc).__name__}: {exc}"}])
        return {"file": path.name, "run_id": run_id, "error": f"{type(exc).__name__}: {exc}"}

    messages = result.all_messages()
    append_json("audit_trail.json", audit_records(run_id, document, messages, result.output))
    append_json("usage_log.json", [usage_record(run_id, document, result.usage)])

    requests = []
    for m in messages:
        if isinstance(m, ModelResponse):
            t = token_counts(m.usage)
            requests.append({**t, "cost_usd": float(cost(t["uncached_input_tokens"], t["cached_input_tokens"],
                                                          t["cache_write_tokens"], t["output_tokens"])["total"])})
    totals = token_counts(result.usage)
    answer = result.output.model_dump()
    expected = key[path.name]
    wrong = [f for f in KEY_FIELDS if answer[f] != expected[f]]
    return {
        "file": path.name,
        "run_id": run_id,
        "requests": requests,
        **totals,
        "cost_usd": as_float(cost(totals["uncached_input_tokens"], totals["cached_input_tokens"],
                                  totals["cache_write_tokens"], totals["output_tokens"])),
        "answer": answer,
        "matches_key": not wrong,
        "fields_not_matching_key": wrong,
        "trap_calls": len(json.loads((OUTPUT_DIR / TRAP_LOG).read_text())) - traps_before,
    }


def summarize(docs: list[dict]) -> dict:
    ok = [d for d in docs if "error" not in d]
    sums = {f: sum(d[f] for d in ok) for f in
            ("input_tokens", "uncached_input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens")}
    costs = cost(sums["uncached_input_tokens"], sums["cached_input_tokens"],
                 sums["cache_write_tokens"], sums["output_tokens"])
    return {
        "documents_run": len(ok),
        "documents_failed": len(docs) - len(ok),
        "model_requests": sum(len(d["requests"]) for d in ok),
        **sums,
        "cost_usd": as_float(costs),
        "average_cost_per_document_usd": float(costs["total"] / len(ok)) if ok else None,
        "answers_matching_key": sum(d["matches_key"] for d in ok),
        "trap_calls": sum(d["trap_calls"] for d in ok),
    }


def main() -> None:
    key = {k["file"]: k for k in json.loads((DATA_DIR / "practice_key.json").read_text())}
    paths = sorted(PRACTICE_DIR.iterdir())
    if not (OUTPUT_DIR / TRAP_LOG).exists():
        append_json(TRAP_LOG, [])
    static = load_instructions()
    session_tag = new_tag()
    modes = {
        "no_cache": ("A new random tag at the end of the instructions on every model request.", [static, new_tag]),
        "cache_handbook": ("One fixed tag at the end of the instructions for the whole run, new for this test.",
                           [static, lambda: session_tag]),
    }

    runs = {}
    for mode, (rule, instructions) in modes.items():
        agent = build_agent(instructions=instructions)
        docs = []
        for path in paths:
            doc = run_document(agent, path, key)
            docs.append(doc)
            status = doc.get("error") or (f"in={doc['input_tokens']:,} cached={doc['cached_input_tokens']:,} "
                                          f"write={doc['cache_write_tokens']:,} out={doc['output_tokens']:,} "
                                          f"${doc['cost_usd']['total']:.6f} key={'ok' if doc['matches_key'] else doc['fields_not_matching_key']}")
            print(f"{mode:<15} {path.name:<28} {status}", flush=True)
        runs[mode] = {"tag_rule": rule, "documents": docs, "totals": summarize(docs)}

    no, yes = runs["no_cache"]["totals"], runs["cache_handbook"]["totals"]
    cached_docs = [d for d in runs["cache_handbook"]["documents"][1:] if "error" not in d]
    steady = Decimal(str(sum(d["cost_usd"]["total"] for d in cached_docs))) / len(cached_docs) if cached_docs else None
    saved = Decimal(str(no["cost_usd"]["total"])) - Decimal(str(yes["cost_usd"]["total"]))

    def per_day(avg):
        return None if avg is None else {"per_day": float(Decimal(str(avg)) * DOCS_PER_DAY),
                                         "per_30_days": float(Decimal(str(avg)) * DOCS_PER_DAY * 30),
                                         "per_365_days": float(Decimal(str(avg)) * DOCS_PER_DAY * 365)}

    comparison = {
        "total_cost_no_cache_usd": no["cost_usd"]["total"],
        "total_cost_cache_handbook_usd": yes["cost_usd"]["total"],
        "saved_usd": float(saved),
        "saved_percent": float(saved / Decimal(str(no["cost_usd"]["total"])) * 100),
        "average_cost_per_document_no_cache_usd": no["average_cost_per_document_usd"],
        "average_cost_per_document_cache_handbook_usd": yes["average_cost_per_document_usd"],
        "average_cost_per_document_cache_handbook_docs_2_to_12_usd": float(steady) if steady is not None else None,
        "projection_1000_docs_per_day_usd": {
            "no_cache": per_day(no["average_cost_per_document_usd"]),
            "cache_handbook_all_12_average": per_day(yes["average_cost_per_document_usd"]),
            "cache_handbook_docs_2_to_12_average": per_day(steady),
        },
    }
    report = {
        "test": "Problem 4: handbook caching comparison",
        "generated_at": now(),
        "model": MODEL_NAME,
        "prices_per_1m_usd": PRICES[MODEL_NAME],
        "prices_source": PRICES.get("source"),
        "method": {
            "same_for_both_runs": [
                "agent.build_agent(): same model, Portkey client (response cache bypassed), tools, and VendorReport output",
                "agent.load_instructions(): same prompts/prompt.md + data/shop_handbook.md",
                "same user message as agent.review() and the same 12 documents in the same order",
                "token counts are the API's usage data for every model request",
            ],
            "only_difference": {m: rule for m, (rule, _) in modes.items()},
            "cost_formula": "uncached input x input_per_1m + cached input x cached_input_per_1m "
                            "+ cache write x cache_write_per_1m + output x output_per_1m, all / 1,000,000",
        },
        "runs": runs,
        "comparison": comparison,
    }
    (OUTPUT_DIR / "cache_test.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
