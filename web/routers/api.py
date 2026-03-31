"""
web/routers/api.py — REST API 路由（返回 JSON）
所有接口统一响应格式：{"code": 0, "message": "success", "data": {...}}
"""

import threading

from fastapi import APIRouter, Depends, Query, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from web.deps import get_db, get_blacklist_manager, get_settings
from modules.blacklist import LIST_TYPE_BLACKLIST, LIST_TYPE_WHITELIST
from modules.classifier import _CATEGORY_TO_ACTION

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


# ── 纠错 ──────────────────────────────────────────────────────────────────────

_VALID_CATEGORIES = {"spam", "transactional", "newsletter", "normal", "important"}


class CorrectionBody(BaseModel):
    correct_category: str

    @field_validator("correct_category")
    @classmethod
    def category_valid(cls, v):
        if v not in _VALID_CATEGORIES:
            raise ValueError(f"correct_category 必须为 {_VALID_CATEGORIES} 之一")
        return v


@router.post("/emails/{uid}/correct")
def correct_email(
    uid: str = Path(...),
    body: CorrectionBody = ...,
    db=Depends(get_db),
):
    # 查询原始分类
    row = db.get_email_by_uid(uid)
    if row is None:
        return err(f"邮件 UID={uid} 不存在", 404)

    original_cat = row["category"]
    correct_cat = body.correct_category
    action_code = _CATEGORY_TO_ACTION[correct_cat]

    db.insert_correction(uid, row["sender"], row["subject"], original_cat, correct_cat)
    db.update_email_category(uid, correct_cat, action_code)
    return ok({"uid": uid, "original_category": original_cat, "correct_category": correct_cat})


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


# ── 自定义规则 ────────────────────────────────────────────────────────────────

_VALID_RULE_FIELDS    = {"sender", "subject", "body"}
_VALID_RULE_OPERATORS = {"contains", "equals", "starts_with", "regex"}


class RuleBody(BaseModel):
    name:       str
    field:      str
    operator:   str
    value:      str
    action_cat: str
    priority:   int = 0
    enabled:    int = 1

    @field_validator("field")
    @classmethod
    def field_valid(cls, v):
        if v not in _VALID_RULE_FIELDS:
            raise ValueError(f"field 必须为 {_VALID_RULE_FIELDS} 之一")
        return v

    @field_validator("operator")
    @classmethod
    def operator_valid(cls, v):
        if v not in _VALID_RULE_OPERATORS:
            raise ValueError(f"operator 必须为 {_VALID_RULE_OPERATORS} 之一")
        return v

    @field_validator("action_cat")
    @classmethod
    def action_cat_valid(cls, v):
        if v not in _VALID_CATEGORIES:
            raise ValueError(f"action_cat 必须为 {_VALID_CATEGORIES} 之一")
        return v


@router.get("/rules")
def get_rules(db=Depends(get_db)):
    return ok(db.get_all_rules())


@router.post("/rules")
def create_rule(body: RuleBody, db=Depends(get_db)):
    rule_id = db.insert_rule(body.name, body.field, body.operator,
                             body.value, body.action_cat, body.priority)
    return ok({"id": rule_id})


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int = Path(...), body: RuleBody = ..., db=Depends(get_db)):
    db.update_rule(rule_id, body.name, body.field, body.operator,
                   body.value, body.action_cat, body.priority, body.enabled)
    return ok()


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int = Path(...), db=Depends(get_db)):
    db.delete_rule(rule_id)
    return ok()


# ── 处理指标 ──────────────────────────────────────────────────────────────────

@router.get("/metrics")
def get_metrics(days: int = Query(7, ge=1, le=90), db=Depends(get_db)):
    rows = db.get_metrics_trend(days)
    return ok(rows)


# ── 历史扫描 ──────────────────────────────────────────────────────────────────

class ScanBody(BaseModel):
    days_back: int = 30
    dry_run:   bool = True


def _run_scan(task_id: int, days_back: int, dry_run: bool, settings, db):
    """后台线程：连接 IMAP，扫描历史邮件，逐封处理（dry_run 时只统计不处理）。"""
    import datetime
    from modules.mail_fetcher import MailFetcher
    from modules.mail_parser import MailParser
    from modules.blacklist import BlacklistManager
    from modules.classifier import EmailClassifier
    from modules.mail_handler import MailHandler
    from modules.notifier import Notifier
    from modules.rule_engine import RuleEngine

    fetcher = MailFetcher(settings, db)
    try:
        fetcher.connect()
        fetcher._client.select_folder("INBOX", readonly=True)
        since = (datetime.date.today() - datetime.timedelta(days=days_back)).strftime("%d-%b-%Y")
        all_uids = fetcher._client.search(["SINCE", since])
        # 过滤已处理
        new_uids = [uid for uid in all_uids if not db.is_uid_processed(str(uid))]
        total = len(new_uids)
        db.update_scan_task(task_id, "running", total=total)

        if dry_run:
            db.update_scan_task(task_id, "completed", total=total,
                                processed=0, finished=True)
            return

        parser     = MailParser()
        bl         = BlacklistManager(db)
        classifier = EmailClassifier(settings)
        notifier   = Notifier(settings)
        rule_eng   = RuleEngine(db)
        handler    = MailHandler(settings, fetcher._client, bl)

        processed = 0
        for uid in new_uids:
            try:
                raw  = fetcher.fetch_raw_email(uid)
                parsed = parser.parse(str(uid), raw)
                cat = rule_eng.match(parsed)
                if cat is None:
                    result = classifier.classify(parsed, db)
                    cat = result.category
                    action = result.action_code
                    reason = result.reason
                    conf   = result.confidence
                else:
                    action = _CATEGORY_TO_ACTION.get(cat, "MARK_READ_ARCHIVE")
                    reason = "自定义规则命中（历史扫描）"
                    conf   = 1.0
                db.insert_email_log(str(uid), parsed.sender, parsed.subject,
                                    cat, action, conf, reason)
                processed += 1
                db.update_scan_task(task_id, "running", total=total, processed=processed)
            except Exception:
                pass

        db.update_scan_task(task_id, "completed", total=total,
                            processed=processed, finished=True)
    except Exception as e:
        db.update_scan_task(task_id, "failed", error_msg=str(e)[:200], finished=True)
    finally:
        fetcher.disconnect()


@router.post("/scan/history")
def start_history_scan(body: ScanBody, db=Depends(get_db), settings=Depends(get_settings)):
    task_id = db.create_scan_task(body.days_back, body.dry_run)
    thread = threading.Thread(
        target=_run_scan,
        args=(task_id, body.days_back, body.dry_run, settings, db),
        daemon=True,
        name=f"history-scan-{task_id}",
    )
    thread.start()
    return ok({"task_id": task_id})


@router.get("/scan/history/{task_id}")
def get_scan_status(task_id: int = Path(...), db=Depends(get_db)):
    task = db.get_scan_task(task_id)
    if not task:
        return err(f"任务 {task_id} 不存在", 404)
    return ok(task)
