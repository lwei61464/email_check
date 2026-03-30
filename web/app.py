"""
web/app.py — FastAPI 应用实例
"""

import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from web.routers import pages, api

logger = logging.getLogger(__name__)

app = FastAPI(title="邮件分拣系统管理后台", docs_url=None, redoc_url=None)

# 静态文件
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# 路由注册
app.include_router(pages.router)
app.include_router(api.router)


# Pydantic 校验失败：统一返回 400（FastAPI 默认 422）
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    first_error = exc.errors()[0]
    message = first_error.get("msg", "请求参数错误")
    # 去掉 Pydantic 自动添加的 "Value error, " 前缀，保持消息简洁
    if message.startswith("Value error, "):
        message = message[len("Value error, "):]
    return JSONResponse({"code": 400, "message": message, "data": {}}, status_code=400)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("未处理异常 %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        {"code": 500, "message": "服务器内部错误，请查看日志", "data": {}},
        status_code=500,
    )
