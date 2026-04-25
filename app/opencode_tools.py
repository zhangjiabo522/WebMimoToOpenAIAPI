"""OpenCode 工具定义

定义 OpenCode Agent 可用的所有工具，供外部系统通过 function calling 使用。
"""

from typing import Any, Dict, List

# ───────────────────────────────────────────────
# OpenCode 完整工具 Schema
# ───────────────────────────────────────────────

OPENCODE_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "读取文件或目录内容。可读取文本文件、图片、PDF 等。如果是目录，返回目录下的条目列表（带子目录标记）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filePath": {
                        "type": "string",
                        "description": "文件或目录的绝对路径"
                    },
                    "offset": {
                        "type": "integer",
                        "description": "起始行号（1-indexed），默认从第1行开始"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最大读取行数，默认最多2000行"
                    }
                },
                "required": ["filePath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "创建新文件或覆盖已有文件。写入前通常需要先 read 确认文件当前内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filePath": {
                        "type": "string",
                        "description": "文件的绝对路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整文件内容"
                    }
                },
                "required": ["filePath", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "对已有文件做精确字符串替换。oldString 必须在文件中唯一存在（否则会失败）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filePath": {
                        "type": "string",
                        "description": "要修改的文件的绝对路径"
                    },
                    "oldString": {
                        "type": "string",
                        "description": "要被替换的精确文本（包含缩进和空格）"
                    },
                    "newString": {
                        "type": "string",
                        "description": "替换后的新文本"
                    },
                    "replaceAll": {
                        "type": "boolean",
                        "description": "是否替换所有匹配项，默认 false（只替换第一个）"
                    }
                },
                "required": ["filePath", "oldString", "newString"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "按 glob 模式搜索文件路径。支持 **/*.py、src/**/*.ts 等模式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "glob 匹配模式，如 **/*.py、*.md"
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索的根目录，默认当前工作目录"
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "在文件内容中搜索正则表达式。返回匹配的文件路径、行号和内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "正则表达式搜索模式"
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索的目录，默认当前工作目录"
                    },
                    "include": {
                        "type": "string",
                        "description": "文件过滤模式，如 *.py、*.{ts,tsx}"
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "在持久化 shell 会话中执行 bash 命令。适用于 git、npm、python 等终端操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 bash 命令"
                    },
                    "description": {
                        "type": "string",
                        "description": "命令的简短描述（5-10字）"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间（毫秒），默认120000（2分钟）"
                    },
                    "workdir": {
                        "type": "string",
                        "description": "命令执行的工作目录"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "webfetch",
            "description": "获取指定 URL 的内容，自动转为 markdown、text 或 html。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要获取的完整 URL（http:// 或 https://）"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "text", "html"],
                        "description": "返回格式，默认 markdown"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间（秒），默认120"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "todowrite",
            "description": "创建或更新任务列表。用于跟踪多步骤任务的进度。",
            "parameters": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "description": "任务数组，每个任务包含 content、status、priority",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                                "priority": {"type": "string", "enum": ["high", "medium", "low"]}
                            }
                        }
                    }
                },
                "required": ["todos"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "skill",
            "description": "加载指定的 skill，获取该 skill 的详细指令和资源。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "skill 名称"
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "question",
            "description": "向用户提问以收集偏好或澄清需求。支持单选和多选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "description": "问题数组",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "header": {"type": "string"},
                                "options": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "label": {"type": "string"},
                                            "description": {"type": "string"}
                                        }
                                    }
                                },
                                "multiple": {"type": "boolean"}
                            }
                        }
                    }
                },
                "required": ["questions"]
            }
        }
    }
]


# ───────────────────────────────────────────────
# 工具使用指南（注入到 system prompt 中）
# ───────────────────────────────────────────────

TOOL_USAGE_GUIDE = """\
# 工具使用指南

你是一个运行在用户计算机上的 AI 助手。你有以下工具可供使用：

## 核心原则
1. **只在需要时使用工具** —— 普通对话、解释概念、简单计算不需要工具
2. **不要编造工具参数** —— 如果你不确定路径或值，先用 bash/ls 或 glob 确认
3. **文件操作前先看** —— 修改文件前先用 read 查看内容
4. **保持对话自然** —— 工具调用只是辅助，主要输出仍然是自然语言

## 何时使用工具
- 需要读取/修改文件系统时 → read / write / edit / glob / grep
- 需要执行命令（git、npm、python 等）时 → bash
- 需要获取网页信息时 → webfetch
- 需要管理任务列表时 → todowrite
- 需要加载特定 skill 时 → skill
- 需要向用户确认选择时 → question

## 何时不使用工具
- 用户问知识性问题（"Python 是什么"）
- 简单数学计算（"1+1 等于几"）
- 纯文本对话和安慰
- 不需要验证的通用建议

## 调用格式
必须严格使用以下格式：

TOOL_CALL: 工具名(参数1="值1", 参数2="值2")

示例：
- TOOL_CALL: read(filePath="/root/project/main.py")
- TOOL_CALL: bash(command="git status", description="Check git status")
- TOOL_CALL: webfetch(url="https://example.com")

注意：
- 参数值用双引号包裹
- 字符串参数中的双引号需要转义 \\"
- 不要在 TOOL_CALL 前后添加多余说明文字
"""


def get_opencode_tools() -> List[Dict[str, Any]]:
    """返回所有 OpenCode 工具定义。"""
    return OPENCODE_TOOLS.copy()


def get_tool_usage_guide() -> str:
    """返回工具使用指南。"""
    return TOOL_USAGE_GUIDE
