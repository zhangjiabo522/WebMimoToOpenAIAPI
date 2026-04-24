# 声明本项目为二开原项目[出处](https://github.com/Water008/MiMo2API)原项目在此尊重开源喜欢的点点star谢谢啦
# WebMimoToOpenAIAPI
# [国内版教程](https://blog.jx.fyi/post.jb?id=10)

将小米 MiMo AI WEB 模型转换为 OpenAI 兼容 API

## 功能特性

- OpenAI 兼容 API 接口
- 支持流式和非流式响应
- 支持深度思考模式
- 实时日志监控
- 用量统计追踪
- 多账号轮询
- Web 管理界面

## 快速开始

### 安装

```bash
git clone https://github.com/zhangjiabo522/WebMimoToOpenAIAPI.git
cd WebMimoToOpenAIAPI
pip install -r requirements.txt
```

### 启动

```bash
# 默认端口 9999
python3 main.py &

# 或后台启动
nohup python3 main.py > nohup.out 2>&1 &
```

## API 端点

### 基础信息

| 项目 | 默认值 |
|------|-------|
| 端口 | 9999 |
| API密钥 | sk-default (可在config.json修改) |

### API 端点列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `http://localhost:9999` | GET | Web管理界面 |
| `http://localhost:9999/v1/chat/completions` | POST | 聊天补全(Chat格式) |
| `http://localhost:9999/chat/completions` | POST | 聊天补全(简写) |
| `http://localhost:9999/v1/responses` | POST | 聊天补全(Responses格式) |
| `http://localhost:9999/responses` | POST | 聊天补全(简写) |
| `http://localhost:9999/v1/models` | GET | 获取模型列表 |
| `http://localhost:9999/models` | GET | 模型列表(简写) |
| `http://localhost:9999/api/usage` | GET | 用量统计 |
| `http://localhost:9999/api/usage/reset` | POST | 重置统计 |
| `http://localhost:9999/api/logs` | GET | SSE实时日志 |
| `http://localhost:9999/api/config` | GET/POST | 配置管理 |
| `http://localhost:9999/api/parse-curl` | POST | 解析cURL |
| `http://localhost:9999/api/test-account` | POST | 测试账号 |
| `http://localhost:9999/api/add-account` | POST | 添加账号 |

## API 使用

### 1. Chat Completions (OpenAI格式)

```bash
curl -X POST http://localhost:9999/v1/chat/completions \
  -H "Authorization: Bearer sk-default" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mimo-v2.5-pro",
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

### 2. Responses API (新版格式)

```bash
curl -X POST http://localhost:9999/v1/responses \
  -H "Authorization: Bearer sk-default" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mimo-v2.5-pro",
    "input": "你好"
  }'
```

### 3. 带上下文的对话

```bash
curl -X POST http://localhost:9999/v1/responses \
  -H "Authorization: Bearer sk-default" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mimo-v2.5-pro",
    "input": [
      {"role": "user", "content": "你好"},
      {"role": "assistant", "content": "你好，有什么可以帮你的？"},
      {"role": "user", "content": "今天天气怎么样？"}
    ]
  }'
```

### 4. 流式响应

```bash
curl -X POST http://localhost:9999/v1/responses \
  -H "Authorization: Bearer sk-default" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mimo-v2.5-pro",
    "input": "你好",
    "stream": true
  }'
```

### 5. 深度思考

```bash
curl -X POST http://localhost:9999/v1/chat/completions \
  -H "Authorization: Bearer sk-default" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mimo-v2.5-pro",
    "messages": [{"role": "user", "content": "分析这个问题"}],
    "reasoning_effort": "high"
  }'
```

## 支持的模型

- `mimo-v2.5-pro` - 专业版
- `mimo-v2.5` - 标准版
- `mimo-v2-flash` - 快速版

## 添加账号

1. 登录 [aistudio.xiaomimimo.com](https://aistudio.xiaomimimo.com)
2. 打开开发者工具 (F12) → Network
3. 发送一条消息
4. 找到 `chat` 请求
5. 右键 → Copy as cURL
6. 粘贴到管理界面解析

## 配置文件

- `config.json` - 账号配置
- `token.json` - 用量统计
- `nohup.out` - 运行日志

## 停止服务

```bash
# 查找进程
ps aux | grep python3

# 或直接杀死
pkill -f "python3 main.py"
```

## License

MIT