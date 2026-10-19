"""Campus Customs vendor-desk agent: PydanticAI + gpt-6-luna through Portkey.

Run from the project folder:
    python agent.py --doc data/practice_docs/p01_bluehen_quote.html
    python agent.py --doc data/exam_docs/e01_quote.html --doc data/attack_docs/a01_elmcity_css_quote.html
    python agent.py data/practice_docs/p01_bluehen_quote.html      (paths without --doc also work)

Each run appends to three logs in output/:
    audit_trail.json  every tool call, tool result, security event, and final answer
    usage_log.json    token usage and API cost (rates from data/prices.json)
    trap_calls.json   attempted send_email / approve_payment calls (normally empty)

Since Problem 6, every answer goes through guard_output (see guards.py) before it is returned.
"""

import json
import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # skip PydanticAI's startup banner

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RunUsage

import guards
from models import AgentDeps, VendorReport
from tools import (
    DATA_DIR, HW_DIR, OUTPUT_DIR, TRAP_LOG,
    append_json, approve_payment, now, read_vendor_document, send_email, visible_text,
)

MODEL_NAME = "gpt-6-luna"
OUTPUT_TOOL = "final_result"  # PydanticAI's name for the tool that returns the VendorReport
MILLION = Decimal(1_000_000)

# A .env in the project folder first (graders), then the course .env one folder up (local development).
load_dotenv(HW_DIR / ".env")
load_dotenv(HW_DIR.parent / ".env")


def load_instructions() -> str:
    """Prompt first, then the full handbook: the same text on every call, so the provider can cache it."""
    prompt = (HW_DIR / "prompts" / "prompt.md").read_text(encoding="utf-8")
    handbook = (DATA_DIR / "shop_handbook.md").read_text(encoding="utf-8")
    return f"{prompt}\n\n---\n\n# Shop handbook\n\n{handbook}"


def build_agent(instructions=None) -> Agent[AgentDeps, VendorReport]:
    """Build the vendor-desk agent. `instructions` defaults to load_instructions(); the cache test
    (scripts/cache_test.py) passes the same text wrapped with per-request tags."""
    key = os.environ["PORTKEY_API_KEY"]
    client = AsyncOpenAI(
        api_key=key,
        base_url=os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1"),
        default_headers={
            "x-portkey-api-key": key,
            # Portkey can replay a cached response for a repeated request. Force a real model call
            # each run so the answers are fresh and the logged usage and cost were actually incurred.
            "x-portkey-cache-force-refresh": "true",
        },
    )
    model = OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
    agent = Agent(
        model,
        output_type=VendorReport,
        deps_type=AgentDeps,
        instructions=load_instructions() if instructions is None else instructions,
        tools=[read_vendor_document, send_email, approve_payment],
    )
    agent.output_validator(guard_output)
    return agent


def guard_output(ctx: RunContext[AgentDeps], report: VendorReport) -> VendorReport:
    """Check the answer in code (guards.py). One retry with feedback, then fail closed."""
    visible, _ = visible_text(HW_DIR / ctx.deps.document)
    problems = guards.check_report(report, visible)
    if not problems:
        return report
    ctx.deps.events.append({"event": "guard_rejected_answer", "attempt": ctx.retry + 1,
                            "problems": problems, "answer": report.model_dump()})
    if ctx.retry < ctx.max_retries:
        raise ModelRetry("Your report failed the vendor desk checks: " + "; ".join(problems) + ". Report only "
                         "values shown in the visible document, apply the four handbook checks, and keep links "
                         "and contact details out of the reason.")
    fixed = guards.fail_closed(report, visible)
    ctx.deps.events.append({"event": "guard_replaced_answer", "answer": fixed.model_dump()})
    return fixed


def usage_record(run_id: str, document: str, usage: RunUsage) -> dict:
    """Token counts for one run and their cost at the data/prices.json rates."""
    rates = json.loads((DATA_DIR / "prices.json").read_text())[MODEL_NAME]
    # input_tokens is all input; cached reads and cache writes are the parts billed at their own rates.
    uncached = usage.input_tokens - usage.cache_read_tokens - usage.cache_write_tokens
    costs = {
        "uncached_input": uncached * Decimal(str(rates["input_per_1m"])) / MILLION,
        "cached_input": usage.cache_read_tokens * Decimal(str(rates["cached_input_per_1m"])) / MILLION,
        "cache_write": usage.cache_write_tokens * Decimal(str(rates["cache_write_per_1m"])) / MILLION,
        "output": usage.output_tokens * Decimal(str(rates["output_per_1m"])) / MILLION,
    }
    costs["total"] = sum(costs.values())
    return {
        "timestamp": now(),
        "run_id": run_id,
        "document": document,
        "model": MODEL_NAME,
        "requests": usage.requests,
        "tool_calls": usage.tool_calls,
        "input_tokens": usage.input_tokens,
        "uncached_input_tokens": uncached,
        "cached_input_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "output_tokens": usage.output_tokens,
        "rates_per_1m_usd": {k: v for k, v in rates.items()},
        "cost_usd": {k: float(v) for k, v in costs.items()},
    }


def audit_records(run_id: str, document: str, messages, report: VendorReport,
                  events: list[dict] | None = None) -> list[dict]:
    """One record per tool call and tool result, then any security events, then the final answer."""
    base = {"run_id": run_id, "document": document}

    def stamp(obj) -> str:
        return obj.timestamp.isoformat(timespec="seconds")

    records = [{"timestamp": stamp(messages[0]), **base, "event": "run_start", "model": MODEL_NAME}]
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart) and part.tool_name != OUTPUT_TOOL:
                records.append({"timestamp": stamp(message), **base, "event": "tool_call", "tool": part.tool_name,
                                "tool_call_id": part.tool_call_id, "arguments": part.args_as_dict()})
            elif isinstance(part, ToolReturnPart) and part.tool_name != OUTPUT_TOOL:
                records.append({"timestamp": stamp(part), **base, "event": "tool_result", "tool": part.tool_name,
                                "tool_call_id": part.tool_call_id, "result": str(part.content)})
    records += [{"timestamp": now(), **base, **event} for event in events or []]
    records.append({"timestamp": now(), **base, "event": "final_answer", "answer": report.model_dump()})
    return records


def review(agent: Agent[AgentDeps, VendorReport], document: str) -> tuple[VendorReport, dict]:
    """Run the agent on one document and append to the audit trail and usage log."""
    run_id = uuid.uuid4().hex[:8]
    deps = AgentDeps(run_id=run_id, document=document)
    try:
        result = agent.run_sync(f"Review the vendor document at {document} and return your report.", deps=deps)
    except Exception as exc:
        append_json("audit_trail.json", [{"timestamp": now(), "run_id": run_id, "document": document,
                                          "event": "run_error", "error": f"{type(exc).__name__}: {exc}"}])
        raise
    append_json("audit_trail.json", audit_records(run_id, document, result.all_messages(), result.output, deps.events))
    usage = usage_record(run_id, document, result.usage)
    append_json("usage_log.json", [usage])
    return result.output, usage


def main(paths: list[str]) -> None:
    if not paths:
        sys.exit(__doc__)
    if not (OUTPUT_DIR / TRAP_LOG).exists():
        append_json(TRAP_LOG, [])  # start an empty trap log so it exists even with no attempts
    agent = build_agent()
    for path in paths:
        document = Path(path).resolve().relative_to(HW_DIR).as_posix()
        report, usage = review(agent, document)
        print(f"\n=== {document}  (run {usage['run_id']})")
        print(report.model_dump_json(indent=2))
        print(f"tokens: {usage['input_tokens']:,} in ({usage['cached_input_tokens']:,} cached), "
              f"{usage['output_tokens']:,} out | cost: ${usage['cost_usd']['total']:.6f}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the vendor-desk agent on vendor documents (.html, .pdf, .eml).")
    parser.add_argument("--doc", action="append", default=[], metavar="PATH", help="document to review (repeatable)")
    parser.add_argument("paths", nargs="*", metavar="PATH", help="more documents")
    args = parser.parse_args()
    main(args.doc + args.paths)
