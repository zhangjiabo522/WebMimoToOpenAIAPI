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
        import json
        try:
            body = self._create_request_body("hi", False)
            print(f"\n{'='*60}")
            print(f"[测试] 请求 URL: {self.API_URL}")
            print(f"[测试] 请求参数: xiaomichatbot_ph={self.account.xiaomichatbot_ph}")
            print(f"[测试] 请求体: {json.dumps(body, ensure_ascii=False)}")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.API_URL,
                    params={"xiaomichatbot_ph": self.account.xiaomichatbot_ph},
                    headers=self._create_headers(),
                    cookies=self._create_cookies(),
                    json=body
                )
                print(f"[测试] 响应状态: {response.status_code}")
                try:
                    resp_text = response.text[:500]
                    print(f"[测试] 响应体: {resp_text}")
                except:
                    pass
                print(f"{'='*60}\n")
                if response.status_code == 200:
                    try:
                        resp_text = response.text
                        if "dialogId" in resp_text or "think" in resp_text.lower() or "type" in resp_text:
                            return True, "连接成功"
                        elif resp_text.startswith("{"):
                            data = json.loads(resp_text)
                            if data.get("code") == 401:
                                return False, "token已过期，请重新获取"
                            return True, f"响应: {resp_text[:200]}"
                        else:
                            return True, "连接成功"
                    except:
                        return True, "连接成功"
                elif response.status_code == 401:
                    return False, "认证失败，cookie可能已过期"
                elif response.status_code == 403:
                    return False, "权限不足，可能需要重新登录"
                else:
                    try:
                        err = response.json().get("message", response.text[:200])
                        return False, f"HTTP {response.status_code}: {err}"
                    except:
                        return False, f"HTTP {response.status_code}"
        except Exception as e:
            print(f"[测试] 异常: {e}")
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
            if response.status_code == 401:
                raise Exception("token已过期，请重新获取cookie")
            if response.status_code == 403:
                raise Exception("权限不足，可能需要登录")
            response.raise_for_status()

            result = []
            usage = {"promptTokens": 0, "completionTokens": 0}
            current_event = None

            async for raw_line in response.aiter_lines():
                raw_line = raw_line.rstrip()
                if raw_line.startswith("id:"):
                    continue
                elif raw_line.startswith("event:"):
                    current_event = raw_line[6:].strip()
                elif raw_line.startswith("data:"):
                    data = raw_line[5:].strip()
                    if data == "[DONE]" or current_event == "finish":
                        break
                    if not data:
                        continue
                    try:
                        sse_data = json.loads(data)
                        if sse_data.get("type") == "text":
                            content = sse_data.get("content", "").replace("\x00", "")
                            result.append(content)
                        if "promptTokens" in sse_data:
                            usage = {
                                "promptTokens": sse_data.get("promptTokens", 0),
                                "completionTokens": sse_data.get("completionTokens", 0)
                            }
                    except json.JSONDecodeError:
                        continue
                current_event = None

            full_text = "".join(result)
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
                if response.status_code == 401:
                    raise Exception("token已过期，请重新获取cookie")
                if response.status_code == 403:
                    raise Exception("权限不足，可能需要登录")
                response.raise_for_status()

                current_event = None
                async for raw_line in response.aiter_lines():
                    raw_line = raw_line.rstrip()
                    if raw_line.startswith("id:"):
                        continue
                    elif raw_line.startswith("event:"):
                        current_event = raw_line[6:].strip()
                    elif raw_line.startswith("data:"):
                        data = raw_line[5:].strip()
                        if data == "[DONE]" or current_event == "finish":
                            break
                        if not data:
                            continue
                        try:
                            sse_data = json.loads(data)
                            if sse_data.get("type") == "text" and sse_data.get("content"):
                                yield sse_data
                        except json.JSONDecodeError:
                            continue
                    current_event = None

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
