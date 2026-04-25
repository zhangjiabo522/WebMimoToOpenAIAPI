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


# ─── 已知的 OpenCode 工具名 ────────────────────────────────────

OPENCODE_TOOL_NAMES = frozenset({
    "read", "write", "edit", "patch", "glob", "grep", "list",
    "bash", "webfetch", "websearch", "lsp", "todowrite", "todoread",
    "skill", "question",
})


def _is_opencode_tools(tools: List[Dict[str, Any]]) -> bool:
    """检测传入的 tools 是否为 OpenCode 工具集。"""
    if not tools:
        return False
    names = set()
    for tool in tools:
        func = _safe_get(tool, "function", default={})
        name = _safe_get(func, "name", default=None)
        if name:
            names.add(name)
    # 如果包含至少 3 个 OpenCode 工具名，认为是 OpenCode 工具集
    return len(names & OPENCODE_TOOL_NAMES) >= 3


# ─── 构建工具提示词 ────────────────────────────────────────────

def build_tool_prompt(tools: List[Dict[str, Any]]) -> str:
    """将 OpenAI tools 列表转为 MiMo 可理解的纯文本工具说明。

    当检测到 OpenCode 工具集时，会自动追加使用指南，
    防止模型在不需要时调用工具（避免"降智"）。
    """
    if not tools:
        return ""

    is_opencode = _is_opencode_tools(tools)

    if is_opencode:
        lines = [
            "# 可用工具",
            "",
            "你是一个运行在用户计算机上的 AI 助手。你拥有以下工具，可在需要时调用。",
            "",
            "## 核心原则",
            "1. 只在**明确需要**时使用工具 —— 普通对话、解释概念、简单计算不需要工具",
            "2. 不要编造工具参数 —— 如果你不确定路径，先用 glob / bash 确认",
            "3. 文件操作前先看 —— 修改文件前先用 read 查看内容",
            "4. 保持对话自然 —— 工具调用只是辅助，主要输出仍然是自然语言",
            "",
            "## 何时使用工具",
            "- 读取/修改文件系统 → read / write / edit / glob / grep",
            "- 执行命令（git、npm、python 等）→ bash",
            "- 获取网页信息 → webfetch",
            "- 管理任务列表 → todowrite",
            "",
            "## 何时不使用工具",
            "- 知识性问题（\"Python 是什么\"）",
            "- 简单数学计算",
            "- 纯文本对话和安慰",
            "- 不需要验证的通用建议",
            "",
            "## 工具列表",
        ]
    else:
        lines = ["你有以下工具可以调用："]

    for i, tool in enumerate(tools, 1):
        # 容错提取 —— tool 可能是 dict 或 pydantic model
        func = _safe_get(tool, "function", default={})
        name = _safe_get(func, "name", default=f"unknown_{i}")
        desc = _safe_get(func, "description", default="无描述")
        params = _safe_get(func, "parameters", default=None)

        lines.append(f"{i}. {name} - {desc}")

        if params and isinstance(params, dict):
            required = set(params.get("required") or [])
            properties = params.get("properties") or {}
            if properties:
                lines.append("   参数:")
                for pname, pdef in properties.items():
                    if not isinstance(pdef, dict):
                        pdef = {}
                    ptype = pdef.get("type", "string")
                    pdesc = pdef.get("description", "")
                    req_tag = "必需" if pname in required else "可选"
                    suffix = f" ({pdesc})" if pdesc else ""
                    lines.append(f"     - {pname} ({ptype}, {req_tag}){suffix}")

    lines.append("")
    if is_opencode:
        lines.append("## 调用格式")
        lines.append("必须严格使用以下格式（独占一行）：")
        lines.append("")
        lines.append('TOOL_CALL: 工具名(参数1="值1", 参数2="值2")')
        lines.append("")
        lines.append("示例：")
        lines.append('  TOOL_CALL: read(filePath="/root/project/main.py")')
        lines.append('  TOOL_CALL: bash(command="git status", description="Check status")')
        lines.append("")
        lines.append("注意：")
        lines.append("- 参数值用双引号包裹")
        lines.append('- 字符串中的双引号需要转义 \\"')
        lines.append("- 不要在 TOOL_CALL 前后添加多余说明文字")
    else:
        lines.append('调用方式：TOOL_CALL: 工具名(参数1="值1", 参数2="值2")')
        lines.append("注意：只调用上面列出的工具，不要编造工具名。参数值用 JSON 格式。")

    return "\n".join(lines)


# ─── 提取工具名列表 ───────────────────────────────────────────

def get_tool_names(tools: List[Dict[str, Any]]) -> List[str]:
    """从 tools 列表提取所有 function name。"""
    names = []
    for tool in tools or []:
        func = _safe_get(tool, "function", default={})
        name = _safe_get(func, "name", default=None)
        if name:
            names.append(str(name))
    return names


# ─── 从文本中提取工具调用 ──────────────────────────────────────

def extract_tool_call(
    text: str, tool_names: List[str]
) -> Tuple[Optional[Dict[str, Any]], str]:
    """从 MiMo 输出文本中提取工具调用。

    策略（按优先级）：
      1. 正则匹配 TOOL_CALL: name(...)
      2. JSON 解析 {"name": ..., "arguments": ...}
      3. 关键词匹配 (name) 或 name(...)

    Returns:
        (tool_call_dict_or_None, cleaned_text_without_tool_call)
    """
    if not text or not tool_names:
        return None, text

    # 清理 null 字节
    text = text.replace("\x00", "")

    # ── 策略1: TOOL_CALL: name(args) ──
    tc = _extract_tool_call_pattern(text, tool_names)
    if tc:
        return tc, _remove_tool_call_text(text)

    # ── 策略2: JSON 格式 ──
    tc = _extract_json_tool_call(text, tool_names)
    if tc:
        return tc, _remove_json_tool_call(text)

    # ── 策略3: 自由文本匹配 ──
    tc = _extract_freeform_tool_call(text, tool_names)
    if tc:
        return tc, _remove_tool_call_text(text)

    return None, text


# ─── 标准化工具调用 ────────────────────────────────────────────

def normalize_tool_call(raw: Dict[str, Any]) -> Dict[str, Any]:
    """将各种格式的 tool_call dict 标准化为 OpenAI 格式。

    OpenAI 格式:
        {
            "id": "call_xxx",
            "type": "function",
            "function": {
                "name": "...",
                "arguments": "{...}"   # JSON 字符串
            }
        }
    """
    if not raw:
        return raw

    # 已经是标准格式
    if "function" in raw and isinstance(raw["function"], dict):
        func = raw["function"]
        if "name" in func and "arguments" in func:
            if "id" not in raw:
                raw["id"] = f"call_{uuid.uuid4().hex[:24]}"
            if "type" not in raw:
                raw["type"] = "function"
            # 确保 arguments 是字符串
            if not isinstance(func["arguments"], str):
                func["arguments"] = json.dumps(func["arguments"], ensure_ascii=False)
            return raw

    # 扁平格式: {"name": "xxx", "arguments": {...}}
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


# ─── 清理工具文本 ──────────────────────────────────────────────

def clean_tool_text(text: str) -> str:
    """清理文本中的工具调用残留痕迹。"""
    if not text:
        return text

    # 移除 TOOL_CALL: xxx 行
    text = re.sub(r"TOOL_CALL:\s*\S+.*", "", text, flags=re.MULTILINE)
    # 移除多余的空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════
# 内部辅助函数
# ═══════════════════════════════════════════════════════════════

def _safe_get(d: Any, key: str, default: Any = None) -> Any:
    """安全取值 —— 对 dict、pydantic model、任意对象都能用。"""
    if d is None:
        return default
    if isinstance(d, dict):
        return d.get(key, default)
    # pydantic model / dataclass / 带 __dict__ 的对象
    return getattr(d, key, default)


def _extract_tool_call_pattern(
    text: str, tool_names: List[str]
) -> Optional[Dict[str, Any]]:
    """策略1: 匹配 TOOL_CALL: name(...) 或 TOOL_CALL: name{...}"""
    # 匹配 TOOL_CALL: xxx(...)
    pattern = r"TOOL_CALL:\s*(\w+)\s*\((.*?)\)"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        # 尝试 TOOL_CALL: name{...}  (JSON args)
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


def _extract_json_tool_call(
    text: str, tool_names: List[str]
) -> Optional[Dict[str, Any]]:
    """策略2: 文本中包含 JSON 工具调用。"""
    # 尝试找 JSON 块
    json_patterns = [
        r"\{[^{}]*\"(?:name|function)\"[^{}]*\}",       # 简单 JSON
        r"\{[^{}]*\"(?:name|function)\"[^{}]*\"arguments\"[^{}]*\}",
    ]
    for pat in json_patterns:
        for m in re.finditer(pat, text, re.DOTALL):
            try:
                obj = json.loads(m.group())
                name = obj.get("name") or _safe_get(
                    obj.get("function", {}), "name"
                )
                if name and name in tool_names:
                    args = obj.get("arguments") or obj.get("parameters") or {}
                    if not isinstance(args, str):
                        args = json.dumps(args, ensure_ascii=False)
                    return normalize_tool_call({"name": name, "arguments": args})
            except (json.JSONDecodeError, AttributeError):
                continue

    # 尝试匹配更大的 JSON 块 (带嵌套)
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
                            name = (
                                obj.get("name")
                                or _safe_get(obj.get("function", {}), "name")
                            )
                            if name and name in tool_names:
                                args = (
                                    obj.get("arguments")
                                    or obj.get("parameters")
                                    or {}
                                )
                                if not isinstance(args, str):
                                    args = json.dumps(args, ensure_ascii=False)
                                return normalize_tool_call(
                                    {"name": name, "arguments": args}
                                )
                        except (json.JSONDecodeError, AttributeError):
                            pass
                        break
            start = text.find("{", start + 1)
    except Exception:
        pass

    return None


def _extract_freeform_tool_call(
    text: str, tool_names: List[str]
) -> Optional[Dict[str, Any]]:
    """策略3: 自由文本匹配 —— 模型可能输出类似 call_xxx(yyy) 的内容。"""
    for name in tool_names:
        # 匹配 name(args) 模式
        pat = rf"(?:^|\s){re.escape(name)}\s*\((.+?)\)"
        m = re.search(pat, text, re.DOTALL)
        if m:
            args_raw = m.group(1).strip()
            args = _parse_args_text(args_raw)
            return normalize_tool_call({"name": name, "arguments": args})

    return None


def _parse_args_text(raw: str) -> str:
    """将函数参数文本转为 JSON 字符串。

    支持格式:
      key="value", key2=123
      key=value, key2=value2
      "json string"
    """
    raw = raw.strip()
    if not raw:
        return "{}"

    # 如果已经是 JSON 对象
    if raw.startswith("{") and raw.endswith("}"):
        try:
            obj = json.loads(raw)
            return json.dumps(obj, ensure_ascii=False)
        except json.JSONDecodeError:
            pass

    # key=value 解析
    args = {}
    # 匹配 key="value" 或 key=value 或 key=123
    pattern = r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^,\s]+))'
    for m in re.finditer(pattern, raw):
        key = m.group(1)
        val = m.group(2) or m.group(3) or m.group(4)
        # 尝试解析数字和布尔
        args[key] = _auto_type(val)

    if args:
        return json.dumps(args, ensure_ascii=False)

    # 无法解析，原样返回
    return json.dumps(raw, ensure_ascii=False)


def _auto_type(val: str) -> Any:
    """自动推断值类型。"""
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


def _remove_tool_call_text(text: str) -> str:
    """移除文本中的 TOOL_CALL 行。"""
    # 移除 TOOL_CALL: xxx 行
    cleaned = re.sub(r"TOOL_CALL:.*$", "", text, flags=re.MULTILINE)
    return cleaned.strip()


def _remove_json_tool_call(text: str) -> str:
    """移除文本中的 JSON 工具调用块。"""
    # 尝试找到并移除 JSON 块
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
                        name = obj.get("name") or _safe_get(
                            obj.get("function", {}), "name"
                        )
                        if name:
                            cleaned = cleaned[:start] + cleaned[i + 1 :]
                            break
                    except (json.JSONDecodeError, AttributeError):
                        pass
                    break
        start = cleaned.find("{", start + 1)

    return cleaned.strip()
