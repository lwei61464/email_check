"""
web_server.py — Web 管理页面启动入口
使用方式：python web_server.py
访问地址：http://localhost:8080
"""

import os
import sys
import uvicorn

# 确保从项目根目录运行，保证模块路径正确
os.chdir(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    port = int(os.getenv("WEB_PORT", "8080"))
    uvicorn.run("web.app:app", host="127.0.0.1", port=port, reload=False)
