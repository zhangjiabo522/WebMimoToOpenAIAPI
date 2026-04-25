"""OpenAI API 数据模型"""

from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field


class OpenAIMessage(BaseModel):
    """OpenAI消息"""
    role: str
    content: Optional[Union[str, List]] = None
    tool_calls: Optional[List] = None


class OpenAIRequest(BaseModel):
    """OpenAI请求"""
    model: str
    messages: List[OpenAIMessage]
    stream: bool = False
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    reasoning_effort: Optional[str] = Field(None, description="深度思考等级: low/medium/high")
    tools: Optional[List] = None


class OpenAIDelta(BaseModel):
    """OpenAI流式响应增量"""
    role: Optional[str] = None
    content: Optional[str] = None
    reasoning: Optional[str] = Field(None, description="深度思考内容")
    tool_calls: Optional[List] = None


class OpenAIChoice(BaseModel):
    """OpenAI选择项"""
    index: int
    message: Optional[OpenAIMessage] = None
    delta: Optional[OpenAIDelta] = None
    finish_reason: Optional[str] = None


class OpenAIUsage(BaseModel):
    """OpenAI使用统计"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class OpenAIResponse(BaseModel):
    """OpenAI响应"""
    id: str
    object: str
    created: int
    model: str
    choices: List[OpenAIChoice]
    usage: Optional[OpenAIUsage] = None


class ParseCurlRequest(BaseModel):
    """解析cURL请求"""
    curl: str


class TestAccountRequest(BaseModel):
    """测试账号请求"""
    service_token: str
    user_id: str
    xiaomichatbot_ph: str


class ParseUrlRequest(BaseModel):
    """解析URL请求"""
    url: str


class GenerateCodeRequest(BaseModel):
    """生成代码请求"""
    service_token: str
    user_id: str
    xiaomichatbot_ph: str
    format: Optional[Literal["curl", "bash"]] = "curl"


class AddAccountRequest(BaseModel):
    """手动添加账号请求"""
    service_token: str
    user_id: str
    xiaomichatbot_ph: str
    nickname: Optional[str] = ""


class OpenAIMessageInput(BaseModel):
    """消息输入"""
    role: str
    content: str


class OpenAIResponsesRequest(BaseModel):
    """OpenAI Responses API 请求"""
    model: str
    input: str | List[dict]  # 支持字符串或消息数组
    stream: bool = False
    max_output_tokens: Optional[int] = None
    temperature: Optional[float] = None
    previous_response_id: Optional[str] = None  # 支持上下文
