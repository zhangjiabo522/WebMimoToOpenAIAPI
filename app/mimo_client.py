"""Mimo API客户端"""

import json
import uuid
import httpx
from typing import Optional, Tuple, AsyncIterator
from .config import MimoAccount


class MimoClient:
    """Mimo API客户端"""

    API_URL = "https://aistudio.xiaomimimo.com/open-apis/bot/chat"
    TIMEOUT = 120.0

    # 支持的模型列表
    AVAILABLE_MODELS = [
        "mimo-v2.5-pro",
        "mimo-v2.5",
        "mimo-v2-flash",
    ]

    def __init__(self, account: MimoAccount):
        self.account = account

    def _create_headers(self) -> dict:
        """创建请求头"""
        return {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://aistudio.xiaomimimo.com",
            "Referer": "https://aistudio.xiaomimimo.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "x-timezone": "Asia/Shanghai",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "dnt": "1",
            "sec-ch-ua": '"Microsoft Edge";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }

    def _create_cookies(self) -> dict:
        """创建Cookies"""
        return {
            "serviceToken": self.account.service_token,
            "userId": self.account.user_id,
            "xiaomichatbot_ph": self.account.xiaomichatbot_ph,
        }

    def _create_request_body(self, query: str, thinking: bool = False, model: str = "mimo-v2.5-pro", tools: bool = False) -> dict:
        """创建请求体"""
        return {
            "msgId": uuid.uuid4().hex[:32],
            "conversationId": uuid.uuid4().hex[:32],
            "query": query,
            "isEditedQuery": False,
            "modelConfig": {
                "enableThinking": thinking,
                "webSearchStatus": "enabled" if tools else "disabled",
                "model": model,
                "temperature": 0.8,
                "topP": 0.95,
            },
            "multiMedias": [],
            "attachments": []
        }

    async def test_connection(self) -> Tuple[bool, str]:
        """测试账号连接"""
        try:
            body = self._create_request_body("hi", False)
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.API_URL,
                    params={"xiaomichatbot_ph": self.account.xiaomichatbot_ph},
                    headers=self._create_headers(),
                    cookies=self._create_cookies(),
                    json=body
                )
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if "data" in data or "text" in data or "choices" in data:
                            return True, "连接成功"
                        elif data.get("code") == 401:
                            return False, "token已过期，请重新获取"
                        else:
                            return True, f"响应: {str(data)[:100]}"
                    except:
                        return True, "连接成功"
                elif response.status_code == 401:
                    return False, "认证失败，请重新获取cookie"
                elif response.status_code == 403:
                    return False, "权限不足，可能需要登录"
                else:
                    try:
                        err = response.json().get("message", response.text[:100])
                        return False, f"HTTP {response.status_code}: {err}"
                    except:
                        return False, f"HTTP {response.status_code}"
        except Exception as e:
            return False, str(e)

    async def call_api(self, query: str, thinking: bool = False, model: str = "mimo-v2.5-pro") -> Tuple[str, str, dict]:
        """调用Mimo API（非流式）"""
        body = self._create_request_body(query, thinking, model)

        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            response = await client.post(
                self.API_URL,
                params={"xiaomichatbot_ph": self.account.xiaomichatbot_ph},
                headers=self._create_headers(),
                cookies=self._create_cookies(),
                json=body
            )
            response.raise_for_status()

            result = []
            usage = {"promptTokens": 0, "completionTokens": 0}

            # 解析SSE流
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data = line[5:].strip()
                    try:
                        sse_data = json.loads(data)
                        if sse_data.get("type") == "text":
                            result.append(sse_data.get("content", ""))
                        # 提取usage信息
                        if "promptTokens" in sse_data:
                            usage = {
                                "promptTokens": sse_data.get("promptTokens", 0),
                                "completionTokens": sse_data.get("completionTokens", 0)
                            }
                    except json.JSONDecodeError:
                        continue

            # 合并结果并解析<think>标签
            full_text = "".join(result).replace("\x00", "")
            content, think_content = self._parse_think_tags(full_text)

            return content, think_content, usage

    async def stream_api(self, query: str, thinking: bool = False, model: str = "mimo-v2.5-pro") -> AsyncIterator[dict]:
        """调用Mimo API（流式）"""
        body = self._create_request_body(query, thinking, model)

        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            async with client.stream(
                "POST",
                self.API_URL,
                params={"xiaomichatbot_ph": self.account.xiaomichatbot_ph},
                headers=self._create_headers(),
                cookies=self._create_cookies(),
                json=body
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        try:
                            sse_data = json.loads(data)
                            if sse_data.get("type") == "text" and sse_data.get("content"):
                                yield sse_data
                        except json.JSONDecodeError:
                            continue

    @staticmethod
    def _parse_think_tags(text: str) -> Tuple[str, str]:
        """解析<think>标签"""
        start = text.find("<think>")
        if start == -1:
            return text, ""

        end = text.find("</think>")
        if end == -1:
            return text, ""

        think_content = text[start + 7:end]
        content = text[end + 8:]

        return content, think_content
