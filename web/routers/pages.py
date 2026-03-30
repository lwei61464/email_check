"""
web/routers/pages.py — 页面路由（返回 HTML）
"""

from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/")
def dashboard(request: Request):
    # Starlette 1.x 新 API：request 作为第一参数，name 第二，context 第三
    return templates.TemplateResponse(request, "dashboard.html", {"active_page": "dashboard"})


@router.get("/emails")
def emails(request: Request):
    return templates.TemplateResponse(request, "emails.html", {"active_page": "emails"})


@router.get("/blacklist")
def blacklist(request: Request):
    return templates.TemplateResponse(request, "blacklist.html", {"active_page": "blacklist"})
