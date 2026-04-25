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
    ParseUrlRequest, GenerateCodeRequest, AddAccountRequest,
    OpenAIResponsesRequest
)
from .config import config_manager, MimoAccount
from .mimo_client import MimoClient
from .utils import parse_curl, parse_url, build_query_from_messages, build_curl_command, build_bash_script, parse_tool_calls
from .usage import tracker

router = APIRouter()

# 日志队列
log_queue: List[str] = []
log_listeners: List[asyncio.Queue] = []


def parse_model(model: str) -> str:
    """解析模型名称"""
    model = model.lower()
    model = model.replace("gpt-", "")
    model = model.replace("4o", "mimo-v2.5-pro").replace("4", "mimo-v2.5-pro").replace("3.5", "mimo-v2-flash")
    if "flash" in model:
        return "mimo-v2-flash"
    elif "pro" in model:
        return "mimo-v2.5-pro"
    elif "v2.5" in model or "v2" in model:
        return "mimo-v2.5"
    return "mimo-v2.5-pro"


def add_log(msg_type: str, msg: str):
    """添加日志"""
    now = datetime.now().strftime("%H:%M:%S")
    entry = json.dumps({"time": now, "type": msg_type, "msg": msg})
    log_queue.append(entry)
    if len(log_queue) > 100:
        log_queue.pop(0)
    print(f"[{msg_type.upper()}] {msg}")
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
@router.post("/chat/completions")
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

    # 添加系统提示词
    system_prompt = config_manager.get_config().get('system_prompt', '')
    if system_prompt:
        query = f"{system_prompt}\n\n{query}"

    # 注入 tools 定义到提示词
    if request.tools:
        tool_descriptions = []
        for t in request.tools:
            func = t.get("function", {})
            name = func.get("name", "unknown")
            desc = func.get("description", "")
            tool_descriptions.append(f"{name}: {desc}")
        if tool_descriptions:
            tool_prompt = f"系统功能: {', '.join(tool_descriptions)}。调用格式: <tool call><function=名称><parameter=参数>值</parameter></function></tool call>"
            query = f"{tool_prompt}\n\n{query}"

    # 判断是否启用深度思考
    thinking = bool(request.reasoning_effort)

    # 创建Mimo客户端
    client = MimoClient(account)

    # 获取模型
    model = parse_model(request.model)

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

        # 解析<tool call>标签
        cleaned_content, tool_calls = parse_tool_calls(content)

        # 如果有思考内容，拼接到回复前面
        full_content = cleaned_content
        if think_content:
            full_content = f"<think>{think_content}</think>\n{cleaned_content}"

        response = OpenAIResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
            object="chat.completion",
            created=int(time.time()),
            model=model,
            choices=[
                OpenAIChoice(
                    index=0,
                    message=OpenAIMessage(role="assistant", content=full_content, tool_calls=tool_calls or None),
                    finish_reason="tool_calls" if tool_calls else "stop"
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


@router.post("/v1/responses")
@router.post("/responses")
async def responses_api(
    request: OpenAIResponsesRequest,
    authorization: Optional[str] = Header(None)
):
    """OpenAI Responses API 兼容接口"""
    
    # 验证API Key
    if not validate_api_key(authorization):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})

    # 获取下一个Mimo账号
    account = config_manager.get_next_account()
    if not account:
        raise HTTPException(status_code=503, detail={"error": {"message": "no mimo account"}})

    # 解析input为messages格式 - 构建对话上下文
    messages = []
    system_prompt = ""
    
    if isinstance(request.input, str):
        # 纯文本输入
        messages = [{"role": "user", "content": request.input}]
    else:
        # 消息数组 - 支持完整对话上下文
        for msg in request.input:
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                # 处理 content 为列表的情况
                if isinstance(content, list):
                    content = " ".join([c.get("text", "") for c in content if isinstance(c, dict)])
                
                # system 消息提取出来
                if role == "system":
                    system_prompt = content
                else:
                    messages.append({"role": role, "content": content})
    
    # 构建最终查询 - 如果有 system prompt，添加到最前面
    if system_prompt:
        query = f"{system_prompt}\n\n" + "\n\n".join([f"{m['role']}: {m['content']}" for m in messages])
    else:
        query = "\n\n".join([f"{m['role']}: {m['content']}" for m in messages])
    
    # 兼容旧版本：只有单个消息时直接用content
    if len(messages) == 1:
        query = messages[0].get("content", query)

    # 添加全局系统提示词
    global_system_prompt = config_manager.get_config().get('system_prompt', '')
    if global_system_prompt:
        query = f"{global_system_prompt}\n\n{query}"

    # 创建Mimo客户端
    client = MimoClient(account)

    # 获取模型
    model = parse_model(request.model)

    # 流式响应
    if request.stream:
        return StreamingResponse(
            stream_responses_response(client, query, model, messages),
            media_type="text/event-stream"
        )

    # 非流式响应
    try:
        start_time = time.time()
        content, think_content, usage = await client.call_api(query, False, model)
        elapsed = time.time() - start_time

        prompt_tokens = usage.get("promptTokens", 0)
        completion_tokens = usage.get("completionTokens", 0)

        # 记录使用情况
        tracker.record(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            seconds=elapsed
        )
        add_log("success", f"[{model}] 输入:{prompt_tokens} 输出:{completion_tokens} 耗时:{elapsed:.1f}s")

        # 如果有思考内容，拼接到回复前面
        full_content = content
        if think_content:
            full_content = f"<think>{think_content}</think>\n{content}"

        # 构建完整的output - 包含所有消息
        output_items = []
        
        # 添加历史消息（非 assistant）
        for msg in messages:
            if msg.get("role") != "assistant":
                msg_content = msg.get("content", "")
                if msg_content:
                    output_items.append({
                        "type": "message",
                        "id": f"msg_{uuid.uuid4().hex[:24]}",
                        "role": msg.get("role", "user"),
                        "content": [{"type": "text", "text": msg_content}]
                    })
        
        # 添加当前 assistant 响应
        output_items.append({
            "type": "message",
            "id": f"msg_{uuid.uuid4().hex[:24]}",
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": full_content
                }
            ]
        })

        # Responses API 格式响应
        response = {
            "id": f"resp_{uuid.uuid4().hex[:24]}",
            "object": "response",
            "created_at": int(time.time()),
            "model": model,
            "output": output_items,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            }
        }

        return response

    except Exception as e:
        add_log("error", f"API错误: {str(e)[:100]}")
        raise HTTPException(status_code=500, detail={"error": {"message": str(e)}})


async def stream_responses_response(client: MimoClient, query: str, model: str, messages: list = None):
    """Responses API 流式响应生成器"""
    if messages is None:
        messages = []
    
    resp_id = f"resp_{uuid.uuid4().hex[:24]}"
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    start_time = time.time()
    completion_tokens = 0
    full_text = ""
    in_think = False
    actual_response = ""
    seq = 0  # 序列号

    try:
        # 发送 response.created 事件
        seq += 1
        yield f"data: {json.dumps({'type': 'response.created', 'sequence_number': seq, 'response': {'id': resp_id, 'object': 'response', 'created_at': int(time.time()), 'model': model, 'status': 'in_progress'}})}\n\n"

        # 发送 response.in_progress 事件
        seq += 1
        yield f"data: {json.dumps({'type': 'response.in_progress', 'sequence_number': seq, 'response': {'id': resp_id, 'object': 'response', 'created_at': int(time.time()), 'model': model, 'status': 'in_progress'}})}\n\n"

        # 添加历史消息（非 assistant）到 output
        for msg in messages:
            if msg.get("role") != "assistant":
                msg_id_hist = f"msg_{uuid.uuid4().hex[:24]}"
                seq += 1
                yield f"data: {json.dumps({'type': 'response.output_item.added', 'sequence_number': seq, 'output_index': len([m for m in messages if m.get('role') != 'assistant']) - 1, 'item': {'id': msg_id_hist, 'type': 'message', 'role': msg.get('role', 'user'), 'status': 'completed', 'content': [{'type': 'text', 'text': msg.get('content', '')}]}})}\n\n"

        # 发送当前 assistant 的 output_item.added 事件
        seq += 1
        yield f"data: {json.dumps({'type': 'response.output_item.added', 'sequence_number': seq, 'output_index': len([m for m in messages if m.get('role') != 'assistant']), 'item': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'status': 'in_progress', 'content': []}})}\n\n"

        # 发送 response.content_part.added 事件
        seq += 1
        yield f"data: {json.dumps({'type': 'response.content_part.added', 'sequence_number': seq, 'item_id': msg_id, 'output_index': 0, 'content_index': 0, 'part': {'type': 'text', 'text': ''}})}\n\n"

        async for sse_data in client.stream_api(query, False, model):
            content = sse_data.get("content", "")
            if not content:
                continue

            content = content.replace("\x00", "")
            full_text += content
            
            buffer = full_text
            output = ""
            
            while buffer:
                if not in_think:
                    think_start = buffer.find("<think>")
                    if think_start != -1:
                        output += buffer[:think_start]
                        buffer = buffer[think_start + 7:]
                        in_think = True
                    else:
                        if len(buffer) > 7:
                            output += buffer[:-7]
                            buffer = buffer[-7:]
                        break
                else:
                    think_end = buffer.find("</think>")
                    if think_end != -1:
                        buffer = buffer[think_end + 8:]
                        in_think = False
                    else:
                        break
            
            full_text = buffer
            
            if output:
                completion_tokens += len(output.split())
                actual_response += output
                seq += 1
                yield f"data: {json.dumps({'type': 'response.output_text.delta', 'sequence_number': seq, 'item_id': msg_id, 'output_index': 0, 'content_index': 0, 'delta': output})}\n\n"

        # 发送剩余内容
        if full_text and not in_think:
            actual_response += full_text
            seq += 1
            yield f"data: {json.dumps({'type': 'response.output_text.delta', 'sequence_number': seq, 'item_id': msg_id, 'output_index': 0, 'content_index': 0, 'delta': full_text})}\n\n"

        # 发送 content_part.done 事件
        seq += 1
        yield f"data: {json.dumps({'type': 'response.content_part.done', 'sequence_number': seq, 'item_id': msg_id, 'output_index': 0, 'content_index': 0, 'part': {'type': 'text', 'text': actual_response}})}\n\n"

        # 发送 output_item.done 事件
        seq += 1
        yield f"data: {json.dumps({'type': 'response.output_item.done', 'sequence_number': seq, 'output_index': 0, 'item': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'status': 'completed', 'content': [{'type': 'text', 'text': actual_response}]}})}\n\n"

        # 构建 output 包含历史消息
        output_items = []
        output_idx = 0
        
        # 添加历史消息
        for msg in messages:
            if msg.get("role") != "assistant" and msg.get("content"):
                output_items.append({
                    "id": f"msg_{uuid.uuid4().hex[:24]}",
                    "type": "message",
                    "role": msg.get("role", "user"),
                    "status": "completed",
                    "content": [{"type": "text", "text": msg.get("content", "")}]
                })
                output_idx += 1
        
        # 添加当前响应
        output_items.append({
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "text", "text": actual_response}]
        })

        # 发送 response.completed 事件
        seq += 1
        prompt_tokens = len(query.split())
        yield f"data: {json.dumps({'type': 'response.completed', 'sequence_number': seq, 'response': {'id': resp_id, 'object': 'response', 'created_at': int(time.time()), 'model': model, 'status': 'completed', 'output': output_items, 'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'total_tokens': prompt_tokens + completion_tokens}}})}\n\n"

        yield "data: [DONE]\n\n"

        elapsed = time.time() - start_time
        tracker.record(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            seconds=elapsed
        )
        add_log("success", f"[{model}] 输入:{prompt_tokens} 输出:{completion_tokens} 耗时:{elapsed:.1f}s")

    except Exception as e:
        error_chunk = {"type": "error", "message": str(e)}
        yield f"data: {json.dumps(error_chunk)}\n\n"
        add_log("error", f"流式错误: {str(e)[:100]}")


@router.get("/v1/models")
@router.get("/models")
async def list_models():
    """列出可用模型"""
    return {
        "object": "list",
        "data": [
            {"id": "mimo-v2.5-pro", "object": "model", "created": 1700000000, "owned_by": "xiaomi"},
            {"id": "mimo-v2.5", "object": "model", "created": 1700000000, "owned_by": "xiaomi"},
            {"id": "mimo-v2-flash", "object": "model", "created": 1700000000, "owned_by": "xiaomi"},
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
                    pass
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
    sent_tool_calls = False

    try:
        async for sse_data in client.stream_api(query, thinking, model):
            content = sse_data.get("content", "")
            if not content:
                continue

            completion_tokens += len(content.split())
            buffer += content
            text = buffer.replace("\x00", "")

            # 检查是否包含完整<tool call>标签
            cleaned, tool_calls = parse_tool_calls(text)
            if tool_calls:
                # 发送tool_calls前积累的文本
                if cleaned:
                    chunk = OpenAIResponse(
                        id=msg_id, object="chat.completion.chunk", created=int(time.time()),
                        model=model,
                        choices=[OpenAIChoice(index=0, delta=OpenAIDelta(content=cleaned), finish_reason=None)]
                    )
                    yield f"data: {json.dumps(chunk.dict())}\n\n"

                # 发送tool_calls
                for tc in tool_calls:
                    tc_chunk = OpenAIResponse(
                        id=msg_id, object="chat.completion.chunk", created=int(time.time()),
                        model=model,
                        choices=[OpenAIChoice(index=0, delta=OpenAIDelta(tool_calls=[tc]))]
                    )
                    yield f"data: {json.dumps(tc_chunk.dict())}\n\n"

                # finish with tool_calls reason
                finish = OpenAIResponse(
                    id=msg_id, object="chat.completion.chunk", created=int(time.time()),
                    model=model,
                    choices=[OpenAIChoice(index=0, delta=OpenAIDelta(), finish_reason="tool_calls")]
                )
                yield f"data: {json.dumps(finish.dict())}\n\n"
                yield "data: [DONE]\n\n"

                elapsed = time.time() - start_time
                prompt_tokens = len(query.split())
                tracker.record(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, seconds=elapsed)
                add_log("success", f"[{model}] tool_calls 输入:{prompt_tokens} 输出:{completion_tokens} 耗时:{elapsed:.1f}s")
                return

            # 没有tool call，正常处理think和文本
            # 处理<think>标签
            while True:
                if not in_think:
                    idx = text.find("<think>")
                    if idx != -1:
                        if idx > 0:
                            chunk = OpenAIResponse(
                                id=msg_id, object="chat.completion.chunk", created=int(time.time()),
                                model=model,
                                choices=[OpenAIChoice(index=0, delta=OpenAIDelta(content=text[:idx]))]
                            )
                            yield f"data: {json.dumps(chunk.dict())}\n\n"
                        in_think = True
                        text = text[idx + 7:]
                        continue

                    safe = len(text) - 7
                    if safe > 0:
                        chunk = OpenAIResponse(
                            id=msg_id, object="chat.completion.chunk", created=int(time.time()),
                            model=model,
                            choices=[OpenAIChoice(index=0, delta=OpenAIDelta(content=text[:safe]))]
                        )
                        yield f"data: {json.dumps(chunk.dict())}\n\n"
                        text = text[safe:]
                    break

                else:
                    idx = text.find("</think>")
                    if idx != -1:
                        if idx > 0:
                            chunk = OpenAIResponse(
                                id=msg_id, object="chat.completion.chunk", created=int(time.time()),
                                model=model,
                                choices=[OpenAIChoice(index=0, delta=OpenAIDelta(reasoning=text[:idx]))]
                            )
                            yield f"data: {json.dumps(chunk.dict())}\n\n"
                        in_think = False
                        text = text[idx + 8:]
                        continue

                    safe = len(text) - 8
                    if safe > 0:
                        chunk = OpenAIResponse(
                            id=msg_id, object="chat.completion.chunk", created=int(time.time()),
                            model=model,
                            choices=[OpenAIChoice(index=0, delta=OpenAIDelta(reasoning=text[:safe]))]
                        )
                        yield f"data: {json.dumps(chunk.dict())}\n\n"
                        text = text[safe:]
                    break

        # 发送剩余的文本
        if text:
            chunk = OpenAIResponse(
                id=msg_id, object="chat.completion.chunk", created=int(time.time()),
                model=model,
                choices=[OpenAIChoice(index=0, delta=OpenAIDelta(content=text))]
            )
            yield f"data: {json.dumps(chunk.dict())}\n\n"

        # 发送结束标记
        final_chunk = OpenAIResponse(
            id=msg_id, object="chat.completion.chunk", created=int(time.time()),
            model=model,
            choices=[OpenAIChoice(index=0, delta=OpenAIDelta(), finish_reason="stop")]
        )
        yield f"data: {json.dumps(final_chunk.dict())}\n\n"
        yield "data: [DONE]\n\n"

        elapsed = time.time() - start_time
        prompt_tokens = len(query.split())
        tracker.record(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, seconds=elapsed)
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


@router.post("/api/test-email")
async def test_email():
    """发送测试邮件"""
    from .email import send_test_email
    success = send_test_email()
    if success:
        return {"status": "ok", "message": "邮件已发送"}
    else:
        return {"status": "error", "message": "发送失败，请检查配置"}


@router.post("/api/check-now")
async def check_now():
    """立即检测账号"""
    from .email import email_checker
    email_checker._check_accounts()
    cfg = config_manager.get_config()
    return {
        "last_time": cfg.get('check_last_time', ''),
        "last_result": cfg.get('check_last_result', '')
    }


@router.post("/api/checker/start")
async def start_checker():
    """启动定时检测"""
    from .email import email_checker
    cfg = config_manager.get_config()
    config_manager.config.email_check_enabled = True
    config_manager.save()
    email_checker.start()
    return {"status": "ok"}


@router.post("/api/checker/stop")
async def stop_checker():
    """停止定时检测"""
    from .email import email_checker
    config_manager.config.email_check_enabled = False
    config_manager.save()
    email_checker.stop()
    return {"status": "ok"}


@router.post("/api/test-account/{user_id}")
async def test_account(user_id: str):
    """测试单个账号"""
    import asyncio
    from .mimo_client import MimoClient
    
    mimo_acc = None
    for acc in config_manager.config.mimo_accounts:
        if acc.user_id == user_id:
            mimo_acc = acc
            break
    
    if not mimo_acc:
        return {"status": "error", "message": "账号不存在"}
    
    client = MimoClient(mimo_acc)
    success, msg = await client.test_connection()
    
    if success:
        return {"status": "ok", "message": msg}
    else:
        return {"status": "error", "message": msg}


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
    import json
    try:
        account = MimoAccount(
            service_token=request.service_token,
            user_id=request.user_id,
            xiaomichatbot_ph=request.xiaomichatbot_ph
        )

        client = MimoClient(account)
        
        print(f"\n{'='*60}")
        print(f"[测试账号] user_id: {request.user_id}")
        print(f"[测试账号] 发送消息: 'hi'")
        
        content, _, _ = await client.call_api("hi", False, tools=True)
        
        print(f"[测试账号] 回复: {content[:500]}")
        print(f"{'='*60}\n")

        return {"success": True, "response": content[:200]}
    except Exception as e:
        print(f"[测试账号] 异常: {e}")
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
