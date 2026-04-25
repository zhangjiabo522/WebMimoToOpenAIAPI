"""工具函数"""

import re
from typing import Optional
from .config import MimoAccount


def parse_curl(curl_command: str) -> Optional[MimoAccount]:
    """解析cURL命令提取Mimo账号凭证"""
    account = {
        'service_token': '',
        'user_id': '',
        'xiaomichatbot_ph': ''
    }

    clean = curl_command

    # PowerShell格式处理 (^ 续行符)
    clean = re.sub(r'\^\s*\n', '', clean)
    clean = re.sub(r'\^"', '"', clean)
    clean = re.sub(r'\^%', '%', clean)
    clean = re.sub(r'\^', '', clean)

    # URL编码解码
    import urllib.parse
    try:
        clean = urllib.parse.unquote(clean)
    except:
        pass

    # 提取cookie字符串（支持多种格式）
    cookie_match = re.search(r"(?:-b|--cookie)\s+'(.+?)'(?:\s|$)", clean, re.DOTALL)
    if not cookie_match:
        cookie_match = re.search(r'(?:-b|--cookie)\s+"(.*?)"(?:\s|$)', clean, re.DOTALL)
    if not cookie_match:
        cookie_match = re.search(r"(?:-H|--header)\s+'[Cc]ookie:\s*(.+?)'", clean, re.DOTALL)
    if not cookie_match:
        cookie_match = re.search(r'(?:-H|--header)\s+"[Cc]ookie:\s*(.+?)"', clean, re.DOTALL)

    cookies = cookie_match.group(1) if cookie_match else clean

    # 提取serviceToken
    st_match = re.search(r'serviceToken="([^"]+)"', cookies)
    if not st_match:
        st_match = re.search(r'serviceToken=([^\s;]+)', cookies)
    if st_match:
        account['service_token'] = st_match.group(1).strip().strip('"')

    # 提取userId
    uid_match = re.search(r'userId=(\d+)', cookies)
    if uid_match:
        account['user_id'] = uid_match.group(1)

    # 提取xiaomichatbot_ph
    ph_match = re.search(r'xiaomichatbot_ph="([^"]+)"', cookies)
    if not ph_match:
        ph_match = re.search(r'xiaomichatbot_ph=([^\s;]+)', cookies)
    if ph_match:
        account['xiaomichatbot_ph'] = ph_match.group(1).strip().strip('"')

    if not account['service_token']:
        return None

    return MimoAccount(**account)

    # 提取cookie字符串（支持多种格式）
    cookie_match = re.search(r"(?:-b|--cookie)\s+'(.+)$", clean)
    if not cookie_match:
        cookie_match = re.search(r'(?:-b|--cookie)\s+"(.+)$', clean)
    if not cookie_match:
        cookie_match = re.search(r"-H\s+'[Cc]ookie:\s*(.+)$", clean)
    if not cookie_match:
        cookie_match = re.search(r'-H\s+"[Cc]ookie:\s*(.+)$', clean)
    if not cookie_match:
        return None

    cookies = cookie_match.group(1)

    # 提取serviceToken (支持带引号和不带引号)
    service_token_match = re.search(r'serviceToken="([^"]+)"', cookies)
    if not service_token_match:
        service_token_match = re.search(r'serviceToken=([^;]+)', cookies)
    if service_token_match:
        account['service_token'] = service_token_match.group(1).strip()

    # 提取userId
    user_id_match = re.search(r'userId=(\d+)', cookies)
    if user_id_match:
        account['user_id'] = user_id_match.group(1)

    # 提取xiaomichatbot_ph (支持带引号和不带引号)
    ph_match = re.search(r'xiaomichatbot_ph="([^"]+)"', cookies)
    if not ph_match:
        ph_match = re.search(r'xiaomichatbot_ph=([^;]+)', cookies)
    if ph_match:
        account['xiaomichatbot_ph'] = ph_match.group(1).strip()

    # 验证必需字段
    if not account['service_token']:
        return None

    return MimoAccount(**account)


def parse_url(url: str) -> Optional[MimoAccount]:
    """
    解析从浏览器复制的URL或原始URL提取Mimo账号凭证

    支持格式:
    - 浏览器开发者工具复制的原始请求
    - 包含cookie的URL（如 mi.com/superweb/chat?cookie=...）
    - cURL命令格式的URL

    Args:
        url: URL字符串或原始请求文本

    Returns:
        MimoAccount对象或None
    """
    account = {
        'service_token': '',
        'user_id': '',
        'xiaomichatbot_ph': ''
    }

    # 尝试从URL查询参数中提取
    if '?' in url:
        query_part = url.split('?')[1] if '://' in url else url.split('?')[1]
        # 提取serviceToken
        match = re.search(r'serviceToken=([^&\s"]+)', query_part)
        if match:
            account['service_token'] = match.group(1)
        # 提取userId
        match = re.search(r'userId=([^&\s"]+)', query_part)
        if match:
            account['user_id'] = match.group(1)
        # 提取xiaomichatbot_ph
        match = re.search(r'xiaomichatbot_ph=([^&\s"]+)', query_part)
        if match:
            account['xiaomichatbot_ph'] = match.group(1)

    # 尝试直接从文本中提取（支持多种格式的cookie字符串）
    if not account['service_token']:
        # 格式: serviceToken=xxx; userId=xxx; xiaomichatbot_ph=xxx
        match = re.search(r'serviceToken=([^;]+)', url)
        if match:
            account['service_token'] = match.group(1).strip()
        match = re.search(r'userId=(\d+)', url)
        if match:
            account['user_id'] = match.group(1)
        match = re.search(r'xiaomichatbot_ph=([^;]+)', url)
        if match:
            account['xiaomichatbot_ph'] = match.group(1).strip()

    # 尝试从cookie头格式提取: Cookie: serviceToken="xxx"; userId=xxx; xiaomichatbot_ph="xxx"
    if not account['service_token']:
        match = re.search(r'serviceToken["\s:]=["\s]?([^";\s]+)', url)
        if match:
            account['service_token'] = match.group(1)
        match = re.search(r'userId["\s:]=["\s]?(\d+)', url)
        if match:
            account['user_id'] = match.group(1)
        match = re.search(r'xiaomichatbot_ph["\s:]=["\s]?([^";\s]+)', url)
        if match:
            account['xiaomichatbot_ph'] = match.group(1)

    # 验证必需字段
    if not account['service_token']:
        return None

    return MimoAccount(**account)


def safe_utf8_len(text: str, max_len: int) -> int:
    """
    安全的UTF-8字符串长度计算，避免在多字节字符中间截断

    Args:
        text: 文本字符串
        max_len: 最大长度

    Returns:
        安全的截断长度
    """
    if max_len <= 0 or max_len >= len(text):
        return len(text)

    # Python 3的字符串是Unicode，不需要特殊处理UTF-8边界
    # 但为了与Go版本保持一致的逻辑，我们保留这个函数
    return max_len


def build_query_from_messages(messages: list, max_messages: int = 10, max_content_len: int = 4000) -> str:
    """
    从消息列表构建查询字符串

    Args:
        messages: 消息列表
        max_messages: 最大消息数量
        max_content_len: 单条消息最大长度

    Returns:
        查询字符串
    """
    # 只保留最后N条消息
    if len(messages) > max_messages:
        messages = messages[-max_messages:]

    query_parts = []
    for msg in messages:
        # 支持dict和Pydantic模型
        if hasattr(msg, 'model_dump'):
            msg = msg.model_dump()
        elif hasattr(msg, 'get'):
            msg = msg
        else:
            msg = {"role": "user", "content": str(msg)}
        
        content = msg.get("content", "")
        role = msg.get("role", "user")
        
        # 处理list类型的content (多模态)
        if isinstance(content, list):
            text_parts = []
            for c in content:
                if isinstance(c, dict):
                    if c.get("type") == "text":
                        text_parts.append(c.get("text", ""))
                    elif c.get("type") == "image_url":
                        text_parts.append("[图片]")
                else:
                    text_parts.append(str(c))
            content = " ".join(text_parts)
        # 截断过长的内容
        if isinstance(content, str) and len(content) > max_content_len:
            content = content[:max_content_len] + "..."
        query_parts.append(f"{role}: {content}")

    return "\n".join(query_parts)


def build_curl_command(account: MimoAccount, api_url: str = "http://localhost:9999") -> str:
    """
    从账号构建cURL命令示例

    Args:
        account: MimoAccount对象
        api_url: API地址

    Returns:
        cURL命令字符串
    """
    cookie = f'serviceToken="{account.service_token}"; userId={account.user_id}; xiaomichatbot_ph="{account.xiaomichatbot_ph}"'
    return f"""curl -X POST "{api_url}/v1/chat/completions" \\
  -H "Authorization: Bearer sk-default" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "model": "mimo-v2.5-pro",
    "messages": [{{"role": "user", "content": "你好"}}
  ]
}}'"""


def build_bash_script(account: MimoAccount, api_url: str = "http://localhost:9999") -> str:
    """
    从账号构建bash脚本示例

    Args:
        account: MimoAccount对象
        api_url: API地址

    Returns:
        bash脚本字符串
    """
    cookie = f'serviceToken="{account.service_token}"; userId={account.user_id}; xiaomichatbot_ph="{account.xiaomichatbot_ph}"'
    return f"""#!/bin/bash

API_URL="{api_url}"
API_KEY="sk-default"

curl -X POST "$API_URL/v1/chat/completions" \\
  -H "Authorization: Bearer $API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "model": "mimo-v2.5-pro",
    "messages": [{{"role": "user", "content": "你好"}}
  ]
}}'"""
