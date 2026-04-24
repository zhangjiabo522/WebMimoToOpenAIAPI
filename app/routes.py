"""API路由"""

import time
import uuid
import json
import asyncio
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import StreamingResponse, JSONResponse
from .models import (
    OpenAIRequest, OpenAIResponse, OpenAIChoice, OpenAIMessage,
    OpenAIDelta, OpenAIUsage, ParseCurlRequest, TestAccountRequest,
    ParseUrlRequest, GenerateCodeRequest, AddAccountRequest
)
from .config import config_manager, MimoAccount
from .mimo_client import MimoClient
from .utils import parse_curl, parse_url, build_query_from_messages, build_curl_command, build_bash_script
from .usage import tracker

router = APIRouter()

# 日志队列
log_queue: List[str] = []
log_listeners: List[asyncio.Queue] = []


def add_log(msg_type: str, msg: str):
    """添加日志"""
    now = datetime.now().strftime("%H:%M:%S")
    entry = json.dumps({"time": now, "type": msg_type, "msg": msg})
    log_queue.append(entry)
    if len(log_queue) > 100:
        log_queue.pop(0)
    for listener in log_listeners:
        try:
            listener.put_nowait(entry)
        except:
            pass


def validate_api_key(authorization: Optional[str]) -> bool:
    """验证API Key"""
    if not authorization:
        return False

    # 移除"Bearer "前缀
    key = authorization.replace("Bearer ", "").strip()
    return config_manager.validate_api_key(key)


@router.post("/v1/chat/completions")
async def chat_completions(
    request: OpenAIRequest,
    authorization: Optional[str] = Header(None)
):
    """OpenAI兼容的聊天接口"""

    # 验证API Key
    if not validate_api_key(authorization):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})

    # 获取下一个Mimo账号
    account = config_manager.get_next_account()
    if not account:
        raise HTTPException(status_code=503, detail={"error": {"message": "no mimo account"}})

    # 构建查询字符串
    query = build_query_from_messages(request.messages)

    # 判断是否启用深度思考
    thinking = bool(request.reasoning_effort)

    # 创建Mimo客户端
    client = MimoClient(account)

    # 获取模型
    model = request.model.replace("gpt-", "").replace("4o", "mimo-v2.5-pro").replace("4", "mimo-v2.5-pro").replace("3.5", "mimo-v2-flash-studio")
    if model not in MimoClient.AVAILABLE_MODELS:
        model = "mimo-v2.5-pro"

    # 流式响应
    if request.stream:
        return StreamingResponse(
            stream_response(client, query, thinking, model),
            media_type="text/event-stream"
        )

    # 非流式响应
    try:
        start_time = time.time()
        content, think_content, usage = await client.call_api(query, thinking, model)
        elapsed = time.time() - start_time

        prompt_tokens = usage.get("promptTokens", 0)
        completion_tokens = usage.get("completionTokens", 0)

        # 记录使用情况
        tracker.record(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            seconds=elapsed
        )

        # 添加日志
        add_log("success", f"[{model}] 输入:{prompt_tokens} 输出:{completion_tokens} 耗时:{elapsed:.1f}s")

        # 如果有思考内容，拼接到回复前面
        full_content = content
        if think_content:
            full_content = f"<think>{think_content}</think>\n{content}"

        response = OpenAIResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
            object="chat.completion",
            created=int(time.time()),
            model=model,
            choices=[
                OpenAIChoice(
                    index=0,
                    message=OpenAIMessage(role="assistant", content=full_content),
                    finish_reason="stop"
                )
            ],
            usage=OpenAIUsage(
                prompt_tokens=usage.get("promptTokens", 0),
                completion_tokens=usage.get("completionTokens", 0),
                total_tokens=usage.get("promptTokens", 0) + usage.get("completionTokens", 0)
            )
        )

        return response

    except Exception as e:
        add_log("error", f"API错误: {str(e)[:100]}")
        raise HTTPException(status_code=500, detail={"error": {"message": str(e)}})


@router.get("/v1/models")
async def list_models():
    """列出可用模型"""
    return {
        "object": "list",
        "data": [
            {"id": "mimo-v2.5-pro", "object": "model", "created": 1700000000, "owned_by": "xiaomi"},
            {"id": "mimo-v2-flash-studio", "object": "model", "created": 1700000000, "owned_by": "xiaomi"},
            {"id": "mimo-2", "object": "model", "created": 1700000000, "owned_by": "xiaomi"},
        ]
    }


@router.get("/api/usage")
async def get_usage():
    """获取API使用统计"""
    return tracker.get_stats()


@router.post("/api/usage/reset")
async def reset_usage():
    """重置使用统计"""
    tracker.reset()
    return {"status": "ok"}


@router.get("/api/logs")
async def stream_logs():
    """SSE实时日志"""
    async def event_stream():
        queue = asyncio.Queue()
        log_listeners.append(queue)
        try:
            # 发送历史日志
            for entry in log_queue[-20:]:
                yield f"data: {entry}\n\n"
            # 实时推送
            while True:
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {entry}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'time': '', 'type': 'info', 'msg': 'ping'})}\n\n"
        finally:
            log_listeners.remove(queue)
    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def stream_response(client: MimoClient, query: str, thinking: bool, model: str):
    """流式响应生成器"""

    msg_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    start_time = time.time()
    completion_tokens = 0

    # 发送初始role delta
    yield f"data: {json.dumps(OpenAIResponse(id=msg_id, object='chat.completion.chunk', created=int(time.time()), model=model, choices=[OpenAIChoice(index=0, delta=OpenAIDelta(role='assistant'))]).dict())}\n\n"

    buffer = ""
    in_think = False

    try:
        async for sse_data in client.stream_api(query, thinking, model):
            content = sse_data.get("content", "")
            if not content:
                continue

            completion_tokens += len(content.split())
            buffer += content
            text = buffer.replace("\x00", "")

            # 处理<think>标签
            while True:
                if not in_think:
                    # 查找<think>标签
                    idx = text.find("<think>")
                    if idx != -1:
                        # 发送<think>之前的内容
                        if idx > 0:
                            chunk = OpenAIResponse(
                                id=msg_id,
                                object="chat.completion.chunk",
                                created=int(time.time()),
                                model=model,
                                choices=[OpenAIChoice(index=0, delta=OpenAIDelta(content=text[:idx]))]
                            )
                            yield f"data: {json.dumps(chunk.dict())}\n\n"

                        in_think = True
                        text = text[idx + 7:]
                        continue

                    # 保留最后7个字符以防<think>被截断
                    safe = len(text) - 7
                    if safe > 0:
                        chunk = OpenAIResponse(
                            id=msg_id,
                            object="chat.completion.chunk",
                            created=int(time.time()),
                            model=model,
                            choices=[OpenAIChoice(index=0, delta=OpenAIDelta(content=text[:safe]))]
                        )
                        yield f"data: {json.dumps(chunk.dict())}\n\n"
                        text = text[safe:]
                    break

                else:
                    # 查找</think>标签
                    idx = text.find("</think>")
                    if idx != -1:
                        # 发送</think>之前的思考内容
                        if idx > 0:
                            chunk = OpenAIResponse(
                                id=msg_id,
                                object="chat.completion.chunk",
                                created=int(time.time()),
                                model=model,
                                choices=[OpenAIChoice(index=0, delta=OpenAIDelta(reasoning=text[:idx]))]
                            )
                            yield f"data: {json.dumps(chunk.dict())}\n\n"

                        in_think = False
                        text = text[idx + 8:]
                        continue

                    # 保留最后8个字符以防</think>被截断
                    safe = len(text) - 8
                    if safe > 0:
                        chunk = OpenAIResponse(
                            id=msg_id,
                            object="chat.completion.chunk",
                            created=int(time.time()),
                            model=model,
                            choices=[OpenAIChoice(index=0, delta=OpenAIDelta(reasoning=text[:safe]))]
                        )
                        yield f"data: {json.dumps(chunk.dict())}\n\n"
                        text = text[safe:]
                    break

            buffer = text

        # 发送剩余内容
        if buffer:
            if in_think:
                chunk = OpenAIResponse(
                    id=msg_id,
                    object="chat.completion.chunk",
                    created=int(time.time()),
                    model=model,
                    choices=[OpenAIChoice(index=0, delta=OpenAIDelta(reasoning=buffer))]
                )
            else:
                chunk = OpenAIResponse(
                    id=msg_id,
                    object="chat.completion.chunk",
                    created=int(time.time()),
                    model=model,
                    choices=[OpenAIChoice(index=0, delta=OpenAIDelta(content=buffer))]
                )
            yield f"data: {json.dumps(chunk.dict())}\n\n"

        # 发送结束标记
        final_chunk = OpenAIResponse(
            id=msg_id,
            object="chat.completion.chunk",
            created=int(time.time()),
            model=model,
            choices=[OpenAIChoice(index=0, delta=OpenAIDelta(), finish_reason="stop")]
        )
        yield f"data: {json.dumps(final_chunk.dict())}\n\n"
        yield "data: [DONE]\n\n"

        # 记录使用情况
        elapsed = time.time() - start_time
        prompt_tokens = len(query.split())
        tracker.record(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            seconds=elapsed
        )
        add_log("success", f"[{model}] 输入:{prompt_tokens} 输出:{completion_tokens} 耗时:{elapsed:.1f}s")

    except Exception as e:
        error_chunk = {"error": {"message": str(e)}}
        yield f"data: {json.dumps(error_chunk)}\n\n"
        add_log("error", f"流式错误: {str(e)[:100]}")


@router.get("/api/config")
async def get_config():
    """获取配置"""
    return config_manager.get_config()


@router.post("/api/config")
async def update_config(request: Request):
    """更新配置"""
    try:
        new_config = await request.json()
        config_manager.update_config(new_config)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "invalid"})


@router.post("/api/parse-curl")
async def parse_curl_command(request: ParseCurlRequest):
    """解析cURL命令"""
    account = parse_curl(request.curl)
    if not account:
        raise HTTPException(status_code=400, detail={"error": "parse failed"})
    return account.to_dict()


@router.post("/api/parse-url")
async def parse_url_command(request: ParseUrlRequest):
    """解析URL或复制的请求"""
    account = parse_url(request.url)
    if not account:
        raise HTTPException(status_code=400, detail={"error": "parse failed"})
    return account.to_dict()


@router.post("/api/generate-code")
async def generate_code(request: GenerateCodeRequest):
    """生成调用代码"""
    account = MimoAccount(
        service_token=request.service_token,
        user_id=request.user_id,
        xiaomichatbot_ph=request.xiaomichatbot_ph
    )

    if request.format == "bash":
        code = build_bash_script(account)
    else:
        code = build_curl_command(account)

    return {"code": code}


@router.post("/api/test-account")
async def test_account(request: TestAccountRequest):
    """测试账号有效性"""
    try:
        account = MimoAccount(
            service_token=request.service_token,
            user_id=request.user_id,
            xiaomichatbot_ph=request.xiaomichatbot_ph
        )

        client = MimoClient(account)
        content, _, _ = await client.call_api("hi", False)

        return {"success": True, "response": content}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/add-account")
async def add_account(request: AddAccountRequest):
    """手动添加账号"""
    try:
        account = MimoAccount(
            service_token=request.service_token,
            user_id=request.user_id,
            xiaomichatbot_ph=request.xiaomichatbot_ph
        )
        
        # 直接添加账号（可选测试）
        config_manager.add_account(account, request.nickname or f"account_{len(config_manager.get_accounts())+1}")
        
        # 保存到config.json
        cfg = config_manager.get_config()
        cfg['mimo_accounts'].append(account.to_dict())
        config_manager.update_config(cfg)
        
        return {"success": True, "account": account.to_dict()}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@router.get("/api/accounts")
async def get_accounts():
    """获取账号列表"""
    return config_manager.get_accounts()
