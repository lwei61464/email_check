"""
web/routers/api.py — REST API 路由（返回 JSON）
所有接口统一响应格式：{"code": 0, "message": "success", "data": {...}}
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from web.deps import get_db, get_blacklist_manager
from modules.blacklist import LIST_TYPE_BLACKLIST, LIST_TYPE_WHITELIST

router = APIRouter(prefix="/api")

_VALID_LIST_TYPES = {LIST_TYPE_BLACKLIST, LIST_TYPE_WHITELIST}


# ── 响应工具 ──────────────────────────────────────────────────────────────────

def ok(data=None):
    return {"code": 0, "message": "success", "data": data if data is not None else {}}


def err(message: str, status_code: int = 400):
    return JSONResponse({"code": status_code, "message": message, "data": {}}, status_code=status_code)


# ── 仪表盘 ────────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(db=Depends(get_db)):
    return ok(db.get_stats())


@router.get("/emails/recent")
def get_recent_emails(limit: int = Query(10, ge=1, le=50), db=Depends(get_db)):
    rows = db.get_recent_logs(limit)
    return ok([dict(r) for r in rows])


@router.get("/emails/trend")
def get_email_trend(days: int = Query(7, ge=1, le=90), db=Depends(get_db)):
    rows = db.get_category_trend(days)
    return ok([dict(r) for r in rows])


# ── 邮件日志 ──────────────────────────────────────────────────────────────────

@router.get("/emails")
def get_emails(
    category: str = Query(None),
    sender: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    result = db.query_email_logs(
        category=category or None,
        sender=sender or None,
        date_from=date_from or None,
        date_to=date_to or None,
        page=page,
        page_size=page_size,
    )
    result["items"] = [dict(r) for r in result["items"]]
    return ok(result)


# ── 黑白名单 ──────────────────────────────────────────────────────────────────

@router.get("/blacklist")
def get_blacklist(list_type: str = Query("blacklist"), db=Depends(get_db)):
    if list_type not in _VALID_LIST_TYPES:
        return err(f"list_type 必须为 blacklist 或 whitelist")
    rows = db.list_addresses(list_type)
    return ok([dict(r) for r in rows])


class AddressBody(BaseModel):
    address: str
    list_type: str
    reason: str = ""

    @field_validator("address")
    @classmethod
    def address_not_empty(cls, v):
        if not v.strip():
            raise ValueError("address 不能为空")
        return v.strip()

    @field_validator("list_type")
    @classmethod
    def list_type_valid(cls, v):
        if v not in _VALID_LIST_TYPES:
            raise ValueError("list_type 必须为 blacklist 或 whitelist")
        return v


class DeleteBody(BaseModel):
    address: str
    list_type: str

    @field_validator("list_type")
    @classmethod
    def list_type_valid(cls, v):
        if v not in _VALID_LIST_TYPES:
            raise ValueError("list_type 必须为 blacklist 或 whitelist")
        return v


@router.post("/blacklist")
def add_to_list(body: AddressBody, bl=Depends(get_blacklist_manager)):
    if body.list_type == LIST_TYPE_BLACKLIST:
        bl.add_to_blacklist(body.address, body.reason)
    else:
        bl.add_to_whitelist(body.address, body.reason)
    return ok()


@router.delete("/blacklist")
def remove_from_list(body: DeleteBody, bl=Depends(get_blacklist_manager)):
    bl.remove(body.address, body.list_type)
    return ok()
