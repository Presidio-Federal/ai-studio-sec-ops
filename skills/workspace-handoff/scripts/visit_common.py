#!/usr/bin/env python3
"""Helpers for a visit script that calls MCP from code.

MCP tools are callable only from execute_command with
execution_type mcp_orchestration, via hai_mcp.call_mcp.
"""
import json
import sys
from pathlib import Path


def mcp_call(tool, args, retries=1):
    """Call one attached MCP tool. Returns the raw envelope.

    ImportError means this process is not mcp_orchestration. A raise
    from call_mcp is a failed envelope, not a traceback. Tool-not-found
    is not retried. One retry when the envelope says success false.
    Never reads or prints the environment.
    """
    try:
        from hai_mcp import call_mcp
    except ImportError:
        print(
            '{"error": "hai_mcp unavailable; run with execution_type mcp_orchestration"}',
            file=sys.stderr,
        )
        sys.exit(1)
    last = None
    for attempt in range(retries + 1):
        try:
            last = call_mcp(tool, args)
        except Exception as exc:
            text = str(exc).split("Available tools:")[0].strip()
            last = {"success": False, "error": text[:200] or "call_mcp raised"}
            if "not found" in text.lower():
                return last
        if isinstance(last, dict) and last.get("success"):
            return last
        if attempt < retries:
            continue
    return last if isinstance(last, dict) else {"success": False, "error": "empty envelope"}


def tool_body(envelope):
    """Return (payload, error) for a tool dict inside a hai_mcp envelope.

    result is a list. result[0] is the tool dict, or a JSON string of
    that dict. result[1], when present, is ignored. A bare tool dict
    that already has ok is accepted.
    """
    if not isinstance(envelope, dict):
        return None, "envelope not an object"
    if "ok" in envelope and "success" not in envelope:
        if envelope.get("ok") is False:
            return None, str(envelope.get("error") or "ok false")[:200]
        return envelope, None
    if not envelope.get("success"):
        return None, str(envelope.get("error") or "success false")[:200]
    outer = envelope.get("result")
    raw = outer[0] if isinstance(outer, list) and outer else outer
    if isinstance(raw, str):
        try:
            raw = json.loads(raw, strict=False)
        except json.JSONDecodeError:
            return None, "result[0] not json"
    if not isinstance(raw, dict):
        return None, "inner envelope not an object"
    if raw.get("ok") is False:
        return None, str(raw.get("error") or "ok false")[:200]
    return raw, None


def load_json(ws, rel):
    path = Path(ws) / rel
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_json(ws, rel, payload):
    path = Path(ws) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def summary(payload):
    """One JSON line. The agent reads the last stdout line, so print this last."""
    return json.dumps(payload, separators=(",", ":"), default=str)
