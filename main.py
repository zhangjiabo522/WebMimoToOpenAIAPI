"""Mimo2API Python版本 - 主程序入口"""
# -*- coding: utf-8 -*-

import logging
import re
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from app.routes import router, add_log
from app.config import config_manager


class UvicornAccessFilter(logging.Filter):
    def filter(self, record):
        return not (hasattr(record, 'pathname') and 'uvicorn' in record.pathname and 'access' in record.getMessage().lower())

# 创建FastAPI应用
app = FastAPI(
    title="Mimo2API",
    description="将小米 Mimo AI 转换为 OpenAI 兼容 API",
    version="1.2.5"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router)

# 静态文件目录
web_dir = Path(__file__).parent / "web"

# 提供管理界面
@app.get("/")
async def serve_admin():
    """提供管理界面"""
    index_file = web_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Admin interface not found"}


def main():
    """主函数"""
    port = 9999

    print(f"""
╔══════════════════════════════════════════════════════════╗
║                    Mimo2API Python                       ║
║          将小米 Mimo AI 转换为 OpenAI 兼容 API           ║
╚══════════════════════════════════════════════════════════╝

🚀 服务器启动中...
📍 地址: http://localhost:{port}
📊 管理界面: http://localhost:{port}
📡 API端点: http://localhost:{port}/v1/chat/completions

配置信息:
  - API Keys: {len(config_manager.config.api_keys.split(','))} 个
  - Mimo账号: {len(config_manager.config.mimo_accounts)} 个
""")

    # 启动服务器
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False
    )


if __name__ == "__main__":
    main()
