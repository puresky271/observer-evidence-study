"""AST-selected experiment code; see extraction_provenance.json."""
from __future__ import annotations
import copy
import hashlib
import inspect
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SYSTEM_PROMPT = """你是一个进行事实边界回答的实验模型。只根据用户问题和提供的三栏上下文回答。
current 是当前仍有支持的观察，history 是过去观察，unknown 是当前没有足够证据的命题。
不要使用上下文之外的常识补全地点、人物、营业状态或事件；不要把 history 说成现在；unknown 时明确说不知道或无法确认。
用简洁中文回答，不要输出分析过程、标签、JSON、条件名称或实验术语。"""

def redact_claim(claim: dict[str, Any]) -> dict[str, Any]:
    # Observer v2 stores semantic fields under `claim`; legacy E1 rows are flat.
    source = dict(claim.get("claim", {})) if isinstance(claim.get("claim"), dict) else claim
    allowed = (
        "subject", "predicate", "object", "modality", "channel",
        "observed_at_jst", "event_time_jst", "scope", "validity",
        "first_observed_at_jst", "last_observed_at_jst",
    )
    result = {key: source[key] for key in allowed if key in source}
    if "subject_ref" in source and "subject" not in result:
        result["subject"] = source["subject_ref"]
    if "predicate" in source and "predicate" not in result:
        result["predicate"] = source["predicate"]
    for key in ("observed_at_jst", "event_time_jst", "validity"):
        if key in claim:
            result[key] = claim[key]
    if "scope" in claim and isinstance(claim["scope"], dict):
        result["scope"] = claim["scope"]
    return result

def model_context(projection: dict[str, Any], *, as_of_jst: str) -> dict[str, Any]:
    return {
        "as_of_jst": as_of_jst,
        "current": [redact_claim(row) for row in projection.get("current", [])],
        "history": [redact_claim(row) for row in projection.get("history", [])],
        "unknown": list(projection.get("unknown", [])),
    }

def request_payload(question: str, context: dict[str, Any], *, max_tokens: int, model: str) -> dict[str, Any]:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be an explicit nonempty string")
    user_prompt = "用户问题：\n" + question + "\n\n上下文：\n" + json.dumps(context, ensure_ascii=False, indent=2)
    return {
        "model": str(model),
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
