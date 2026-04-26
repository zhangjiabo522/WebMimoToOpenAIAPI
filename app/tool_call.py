"""工具调用模块

将 OpenAI function calling 格式转译为 MiMo 可理解的纯文本提示词，
并从 MiMo 的纯文本响应中解析回结构化 tool_call。

设计原则：
  1. 防御性编程 — 任何字段缺失/None 都不能崩溃
  2. 多策略提取 — 正则 + JSON + 关键词匹配，尽力而为
  3. 单一职责 — 每个函数做一件事
"""

from __future__ import annotations

import re
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "build_tool_prompt",
    "get_tool_names",
    "extract_tool_call",
    "normalize_tool_call",
    "clean_tool_text",
]


OPENCODE_TOOL_NAMES = frozenset({
    "read", "write", "edit", "patch", "glob", "grep", "list",
    "bash", "webfetch", "websearch", "lsp", "todowrite", "todoread",
    "skill", "question", "codesearch",
})


def _is_opencode_tools(tools):
    if not tools:
        return False
    names = set()
    for tool in tools:
        func = _safe_get(tool, "function", default={})
        name = _safe_get(func, "name", default=None)
        if name:
            names.add(name)
    return len(names & OPENCODE_TOOL_NAMES) >= 3


def build_tool_prompt(tools):
    if not tools:
        return ""

    is_opencode = _is_opencode_tools(tools)

    if is_opencode:
        lines = [
            "# 可用工具",
            "",
            "你是一个运行在用户计算机上的 AI 助手，拥有以下工具。",
            "",
            "## 核心原则",
            "1. 只在明确需要时使用工具",
            "2. 不要编造工具参数",
            "3. 文件操作前先看",
            "",
            "## 调用格式",
            "请使用以下 XML 格式:",
            "<tool_call>",
            "<function=工具名>",
            "<parameter=参数名>参数值",
            "</function>",
            "</tool_call>",
            "",
        ]
    else:
        lines = ["# Tools"]

    for i, tool in enumerate(tools, 1):
        func = _safe_get(tool, "function", default={})
        name = _safe_get(func, "name", default=f"unknown_{i}")
        desc = _safe_get(func, "description", default="")
        params = _safe_get(func, "parameters", default=None)

        param_str = ""
        if params and isinstance(params, dict):
            props = params.get("properties") or {}
            if props:
                param_str = "(" + ", ".join(props.keys()) + ")"

        d = " - " + desc if desc else ""
        lines.append(f"{i}. {name}{param_str}{d}")

    return "\n".join(lines)


def get_tool_names(tools):
    names = []
    for tool in tools or []:
        func = _safe_get(tool, "function", default={})
        name = _safe_get(func, "name", default=None)
        if name:
            names.append(str(name))
    return names


def extract_tool_call(text, tool_names):
    if not text or not tool_names:
        return None, text

    text = text.replace("\x00", "")

    tc = _extract_tool_call_pattern(text, tool_names)
    if tc:
        return tc, _remove_tool_call_text(text)

    tc = _extract_json_tool_call(text, tool_names)
    if tc:
        return tc, _remove_json_tool_call(text)

    tc = _extract_freeform_tool_call(text, tool_names)
    if tc:
        return tc, _remove_tool_call_text(text)

    tc = _extract_xml_tool_call(text, tool_names)
    if tc:
        return tc, _remove_tool_call_text(text)

    fc_pat = r"<function_calls?>(.*?)</function_calls?>"
    fc_m = re.search(fc_pat, text, re.DOTALL)
    if fc_m:
        inner = fc_m.group(1)
        for block in re.split(r"</function_call>", inner):
            if not block.strip():
                continue
            block = re.sub(r"^.*?<function_call>", "", block, flags=re.DOTALL).strip()
            if not block:
                continue
            js_start = block.find("{")
            if js_start == -1:
                continue
            js = _find_balanced_json(block, js_start)
            if js:
                try:
                    data = json.loads(js)
                    name = data.get("name", "")
                    if name and name in tool_names:
                        args = data.get("arguments", {})
                        tc2 = normalize_tool_call({"name": name, "arguments": args})
                        if tc2:
                            return tc2, _remove_tool_call_text(text)
                except (json.JSONDecodeError, AttributeError):
                    pass

    tc = _extract_opencode_invoke(text, tool_names)
    if tc:
        return tc, _remove_tool_call_text(text)

    tc = _extract_antml_tool_call(text, tool_names)
    if tc:
        return tc, _remove_tool_call_text(text)

    return None, text


def normalize_tool_call(raw):
    if not raw:
        return raw

    if "function" in raw and isinstance(raw["function"], dict):
        func = raw["function"]
        if "name" in func and "arguments" in func:
            if "id" not in raw:
                raw["id"] = f"call_{uuid.uuid4().hex[:24]}"
            if "type" not in raw:
                raw["type"] = "function"
            if not isinstance(func["arguments"], str):
                func["arguments"] = json.dumps(func["arguments"], ensure_ascii=False)
            return raw

    if "name" in raw:
        args = raw.get("arguments") or raw.get("parameters") or raw.get("args") or {}
        if not isinstance(args, str):
            args = json.dumps(args, ensure_ascii=False)
        return {
            "id": f"call_{uuid.uuid4().hex[:24]}",
            "type": "function",
            "function": {
                "name": raw["name"],
                "arguments": args,
            },
        }

    return raw


def clean_tool_text(text):
    if not text:
        return text

    text = re.sub(r"TOOL_CALL:\s*\S+.*", "", text, flags=re.MULTILINE)
    text = re.sub(r"</?function_calls?>", "", text)
    text = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<function=\w+>.*?</function>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<parameter=\w+>.*?</parameter>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<invoke\s+name=\"\w+\"[^>]*>.*?</invoke>", "", text, flags=re.DOTALL)
    text = re.sub(r"<antml:[^>]+>.*?</antml:[^>]+>", "", text, flags=re.DOTALL)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _safe_get(d, key, default=None):
    if d is None:
        return default
    if isinstance(d, dict):
        return d.get(key, default)
    return getattr(d, key, default)


def _find_balanced_json(text, start):
    if start >= len(text) or text[start] != "{":
        return ""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if esc:
            esc = False
            continue
        if c == "\\" and in_str:
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return ""


def _extract_xml_tool_call(text, tool_names):
    tc_pattern = r"<tool_call>(.*?)</tool_call>"
    m = re.search(tc_pattern, text, re.DOTALL | re.IGNORECASE)
    if not m:
        return None

    inner = m.group(1)
    func_pattern = r"<function=(\w+)>(.*?)</function>"
    fm = re.search(func_pattern, inner, re.DOTALL | re.IGNORECASE)
    if not fm:
        return None

    name = fm.group(1).strip()
    if name not in tool_names:
        return None

    func_body = fm.group(2)
    args = {}
    param_pattern = r"<parameter=(\w+)>(.*?)</parameter>"
    for pm in re.finditer(param_pattern, func_body, re.DOTALL | re.IGNORECASE):
        key = pm.group(1).strip()
        val = pm.group(2).strip()
        args[key] = _auto_type(val)

    return normalize_tool_call({"name": name, "arguments": args})


def _extract_opencode_invoke(text, tool_names):
    pattern = r"<invoke\s+name=\"(\w+)\">\s*((?:\s*<parameter\s+name=\"(\w+)\">(.*?)</parameter>\s*)+)\s*</invoke>"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return None

    name = match.group(1).strip()
    if name not in tool_names:
        return None

    args = {}
    param_pattern = r"<parameter\s+name=\"(\w+)\">(.*?)</parameter>"
    for pm in re.finditer(param_pattern, match.group(0), re.DOTALL):
        key = pm.group(1)
        val = pm.group(2).strip()
        args[key] = _auto_type(val)

    return normalize_tool_call({"name": name, "arguments": args})


def _extract_antml_tool_call(text, tool_names):
    pattern = r"<antml:invoke\s+name=\"(\w+)\">\s*((?:\s*<antml:parameter\s+name=\"(\w+)\">(.*?)</antml:parameter>\s*)+)\s*</antml:invoke>"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return None

    name = match.group(1).strip()
    if name not in tool_names:
        return None

    args = {}
    param_pattern = r"<antml:parameter\s+name=\"(\w+)\">(.*?)</antml:parameter>"
    for pm in re.finditer(param_pattern, match.group(0), re.DOTALL):
        key = pm.group(1)
        val = pm.group(2).strip()
        args[key] = _auto_type(val)

    return normalize_tool_call({"name": name, "arguments": args})


def _extract_tool_call_pattern(text, tool_names):
    pattern = r"TOOL_CALL:\s*(\w+)\s*\((.*?)\)"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        pattern2 = r"TOOL_CALL:\s*(\w+)\s*\{(.+?)\}\s*$"
        match = re.search(pattern2, text, re.DOTALL | re.MULTILINE)

    if not match:
        return None

    name = match.group(1).strip()
    if name not in tool_names:
        return None

    args_raw = match.group(2).strip()
    args = _parse_args_text(args_raw)
    return normalize_tool_call({"name": name, "arguments": args})


def _extract_json_tool_call(text, tool_names):
    json_patterns = [
        r"\{[^{}]*\"(?:name|function)\"[^{}]*\}",
        r"\{[^{}]*\"(?:name|function)\"[^{}]*\"arguments\"[^{}]*\}",
    ]
    for pat in json_patterns:
        for m in re.finditer(pat, text, re.DOTALL):
            try:
                obj = json.loads(m.group())
                name = obj.get("name") or _safe_get(obj.get("function", {}), "name")
                if name and name in tool_names:
                    args = obj.get("arguments") or obj.get("parameters") or {}
                    if not isinstance(args, str):
                        args = json.dumps(args, ensure_ascii=False)
                    return normalize_tool_call({"name": name, "arguments": args})
            except (json.JSONDecodeError, AttributeError):
                continue

    try:
        start = text.find("{")
        while start != -1:
            depth = 0
            for i in range(start, min(start + 2000, len(text))):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        try:
                            obj = json.loads(candidate)
                            name = obj.get("name") or _safe_get(obj.get("function", {}), "name")
                            if name and name in tool_names:
                                args = obj.get("arguments") or obj.get("parameters") or {}
                                if not isinstance(args, str):
                                    args = json.dumps(args, ensure_ascii=False)
                                return normalize_tool_call({"name": name, "arguments": args})
                        except (json.JSONDecodeError, AttributeError):
                            pass
                        break
            start = text.find("{", start + 1)
    except Exception:
        pass

    return None


def _extract_freeform_tool_call(text, tool_names):
    for name in tool_names:
        pat = rf"(?:^|\s){re.escape(name)}\s*\((.+?)\)"
        m = re.search(pat, text, re.DOTALL)
        if m:
            args_raw = m.group(1).strip()
            args = _parse_args_text(args_raw)
            return normalize_tool_call({"name": name, "arguments": args})

    return None


def _parse_args_text(raw):
    raw = raw.strip()
    if not raw:
        return "{}"

    if raw.startswith("{") and raw.endswith("}"):
        try:
            obj = json.loads(raw)
            return json.dumps(obj, ensure_ascii=False)
        except json.JSONDecodeError:
            pass

    args = {}
    pattern = r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^,\s]+))'
    for m in re.finditer(pattern, raw):
        key = m.group(1)
        val = m.group(2) or m.group(3) or m.group(4)
        args[key] = _auto_type(val)

    if args:
        return json.dumps(args, ensure_ascii=False)

    return json.dumps(raw, ensure_ascii=False)


def _auto_type(val):
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    if val.lower() == "null" or val.lower() == "none":
        return None
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def _remove_tool_call_text(text):
    cleaned = re.sub(r"TOOL_CALL:.*$", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"</?function_calls?>", "", cleaned)
    cleaned = re.sub(r"<tool_call>.*?</tool_call>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"</?function=\w+>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<parameter=\w+>.*?</parameter>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<invoke\s+name=\"\w+\"[^>]*>.*?</invoke>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<antml:[^>]+>.*?</antml:[^>]+>", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


def _remove_json_tool_call(text):
    cleaned = text
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        for i in range(start, min(start + 2000, len(cleaned))):
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start : i + 1]
                    try:
                        obj = json.loads(candidate)
                        name = obj.get("name") or _safe_get(obj.get("function", {}), "name")
                        if name:
                            cleaned = cleaned[:start] + cleaned[i + 1 :]
                            break
                    except (json.JSONDecodeError, AttributeError):
                        pass
                    break
        start = cleaned.find("{", start + 1)

    cleaned = re.sub(r"<tool_call>\s*</tool_call>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
