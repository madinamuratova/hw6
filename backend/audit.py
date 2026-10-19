"""Append-only audit trail (output/audit_trail.json).

Every agent-loop step becomes one record: which agent, who called it, what it
did, and whether it delegated or used a tool. Records are only ever appended;
if the file can't be read, we stop instead of overwriting it.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import RetryPromptPart, TextPart, ThinkingPart, ToolCallPart, ToolReturnPart

DELEGATE_TOOL = "delegate"
PREVIEW_CHARS = 400


def _short(value: Any, limit: int = PREVIEW_CHARS) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + f"... (+{len(text) - limit} chars)"


def _is_output_tool(name: str) -> bool:
    return name.startswith("final_result")


def _said(output: Any) -> str:
    """A one-glance version of an agent's final answer for the audit trail."""
    if hasattr(output, "summary"):  # AgentReport
        return _short(output.summary, 600)
    if hasattr(output, "tickets"):  # ShiftReport
        return _short(" ".join(f"Ticket {t.ticket_id} ({t.status}): {t.summary}" for t in output.tickets), 900)
    return _short(output, 600)


class AuditTrail:
    def __init__(self, path: Path):
        self.path = path

    def append(self, **record: Any) -> None:
        records = self._load()
        # "source" tells team records apart from the vendor-desk records in the same file.
        records.append({"timestamp": datetime.now().astimezone().isoformat(timespec="seconds"), "source": "agent_team", **record})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(records, indent=2, default=str))
        tmp.replace(self.path)

    def read(self) -> list[dict[str, Any]]:
        """All records, oldest first."""
        return self._load()

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text())  # raises on a corrupt file: never overwrite it
        if not isinstance(data, list):
            raise RuntimeError(f"{self.path} is not a JSON list; refusing to overwrite it.")
        return data


def describe_node(node: Any) -> dict[str, Any]:
    """Turn one PydanticAI agent-loop node into an audit record body."""
    base: dict[str, Any] = {"delegated": False, "delegated_to": [], "used_tool": False, "tools_called": []}

    if Agent.is_user_prompt_node(node):
        if node.user_prompt is None:  # a run resumed with the human's approval decision
            return {**base, "phase": "resumed", "action": "Resumed after the human approval decision"}
        return {**base, "phase": "task_received", "action": f"Received task: {_short(node.user_prompt)}"}

    if Agent.is_model_request_node(node):
        results = [
            {"tool": p.tool_name, "result": _short(p.model_response_str())}
            for p in node.request.parts
            if isinstance(p, ToolReturnPart) and not _is_output_tool(p.tool_name)
        ]
        retries = [_short(p.model_response()) for p in node.request.parts if isinstance(p, RetryPromptPart)]
        if results:
            action = f"Sent {len(results)} tool result(s) back to the model"
        elif retries:
            action = "Asked the model to fix an invalid tool call or answer"
        else:
            action = "Sent the task to the model"
        record = {**base, "phase": "model_request", "action": action, "tool_results": results}
        if retries:
            record["retries"] = retries
        return record

    if Agent.is_call_tools_node(node):
        response = node.model_response
        calls = [p for p in response.parts if isinstance(p, ToolCallPart)]
        delegations = [c for c in calls if c.tool_name == DELEGATE_TOOL]
        tool_calls = [c for c in calls if c.tool_name != DELEGATE_TOOL and not _is_output_tool(c.tool_name)]
        gives_answer = any(_is_output_tool(c.tool_name) for c in calls)
        text = " ".join(p.content for p in response.parts if isinstance(p, TextPart)).strip()

        pieces = []
        if delegations:
            pieces.append("Delegated to " + ", ".join(str(c.args_as_dict().get("to")) for c in delegations))
        if tool_calls:
            pieces.append("Called " + ", ".join(c.tool_name for c in tool_calls))
        if gives_answer:
            pieces.append("Gave its final answer")
        if not pieces:
            pieces.append(f"Replied with text: {_short(text, 200)}" if text else "Model response with no action")

        record = {
            "phase": "model_response",
            "action": "; ".join(pieces),
            "said": _short(text, 600) if text else None,
            "delegated": bool(delegations),
            "delegated_to": [c.args_as_dict().get("to") for c in delegations],
            "used_tool": bool(tool_calls),
            "tools_called": [{"tool": c.tool_name, "args": c.args_as_dict()} for c in tool_calls],
            "delegation_tasks": [_short(c.args_as_dict().get("task", ""), 300) for c in delegations],
            "tokens": {"input": response.usage.input_tokens, "output": response.usage.output_tokens},
        }
        if any(isinstance(p, ThinkingPart) for p in response.parts):
            record["model_reasoned"] = True  # reasoning text itself is not logged
        return record

    if Agent.is_end_node(node):
        output = node.data.output
        dumped = output.model_dump() if hasattr(output, "model_dump") else output
        return {
            **base,
            "phase": "final_output",
            "action": f"Finished with {type(output).__name__}",
            "said": _said(output),
            "output": _short(dumped, 1500),
        }

    return {**base, "phase": type(node).__name__, "action": "Unrecognised loop step"}
