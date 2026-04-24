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
git clone <repo>
cd MiMo2API
pip install -r requirements.txt
```

### 启动

```bash
# 后台启动
./start.sh

# 或手动启动
PORT=9999 nohup python3 main.py &
```
### 添加账号
![http://img.cd-sw.com/img/1070](http://img.cd-sw.com/img/1070)
![http://img.cd-sw.com/img/1071](http://img.cd-sw.com/img/1071)

### 访问

- 管理界面: http://localhost:9999
- API端点: http://localhost:9999/v1/chat/completions
- 模型列表: http://localhost:9999/v1/models

## API 使用

### 聊天补全

```bash
curl -X POST http://localhost:9999/v1/chat/completions \
  -H "Authorization: Bearer sk-default" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mimo-v2.5-pro",
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

### 流式响应

```bash
curl -X POST http://localhost:9999/v1/chat/completions \
  -H "Authorization: Bearer sk-default" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mimo-v2.5-pro",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

### 深度思考

```bash
curl -X POST http://localhost:9999/v1/chat/completions \
  -H "Authorization: Bearer sk-default" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mimo-v2.5-pro",
    "messages": [{"role": "user", "content": "分析一下这个问题"}],
    "reasoning_effort": "high"
  }'
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | 聊天补全接口 |
| `/v1/models` | GET | 获取模型列表 |
| `/api/config` | GET/POST | 获取/更新配置 |
| `/api/parse-curl` | POST | 解析cURL命令 |
| `/api/test-account` | POST | 测试账号连接 |
| `/api/add-account` | POST | 添加账号 |
| `/api/usage` | GET | 获取使用统计 |
| `/api/usage/reset` | POST | 重置统计 |
| `/api/logs` | GET | SSE实时日志 |

## 支持的模型

- `mimo-v2.5-pro` - 最新专业版
- `mimo-v2-flash-studio` - 快速版
- `mimo-2` - 标准版

## 添加账号

1. 登录 [aistudio.xiaomimimo.com](https://aistudio.xiaomimimo.com)
2. 打开开发者工具 (F12) → Network
3. 发送一条消息
4. 找到 `chat` 请求
5. 右键 → Copy as cURL
6. 粘贴到管理界面

## 配置文件

- `config.json` - 账号配置
- `usage.json` - 用量统计
- `nohup.out` - 运行日志

## 停止服务

```bash
# 使用PID文件
kill $(cat mimo2api.pid)

# 或直接查找
pkill -f "python3 main.py"
```

## License

MIT
