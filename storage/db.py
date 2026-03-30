"""
storage/db.py — SQLite 数据库操作模块
职责：提供 SQLite 数据库的初始化（建表）、处理日志写入/查询、
      黑白名单数据的持久化 CRUD 操作，作为系统唯一的持久化层。
"""

import os
import sqlite3
import logging
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

DDL_EMAIL_LOG = """
CREATE TABLE IF NOT EXISTS email_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT NOT NULL UNIQUE,
    sender      TEXT NOT NULL,
    subject     TEXT,
    category    TEXT NOT NULL,
    action_code TEXT NOT NULL,
    confidence  REAL,
    reason      TEXT,
    processed_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

DDL_ADDRESS_LIST = """
CREATE TABLE IF NOT EXISTS address_list (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    address     TEXT NOT NULL,
    list_type   TEXT NOT NULL,
    reason      TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(address, list_type)
)
"""


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    @contextmanager
    def _get_conn(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        """初始化数据库，创建所有必要的表（幂等）。"""
        with self._get_conn() as conn:
            conn.execute(DDL_EMAIL_LOG)
            conn.execute(DDL_ADDRESS_LIST)
        logger.info("数据库初始化完成：%s", self.db_path)

    # ── 处理日志 ──────────────────────────────────────────

    def insert_email_log(self, uid: str, sender: str, subject: str,
                         category: str, action_code: str,
                         confidence: float, reason: str):
        sql = """
            INSERT OR IGNORE INTO email_log
                (uid, sender, subject, category, action_code, confidence, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        with self._get_conn() as conn:
            conn.execute(sql, (uid, sender, subject, category, action_code, confidence, reason))

    def is_uid_processed(self, uid: str) -> bool:
        sql = "SELECT EXISTS(SELECT 1 FROM email_log WHERE uid = ?)"
        with self._get_conn() as conn:
            row = conn.execute(sql, (uid,)).fetchone()
            return bool(row[0])

    # ── 黑白名单 ──────────────────────────────────────────

    def upsert_address(self, address: str, list_type: str, reason: str = ""):
        """插入或更新地址记录。地址已存在时更新 reason 字段。"""
        sql = """
            INSERT INTO address_list (address, list_type, reason)
            VALUES (?, ?, ?)
            ON CONFLICT(address, list_type) DO UPDATE SET reason = excluded.reason
        """
        with self._get_conn() as conn:
            conn.execute(sql, (address.lower(), list_type, reason))

    def delete_address(self, address: str, list_type: str):
        sql = "DELETE FROM address_list WHERE address = ? AND list_type = ?"
        with self._get_conn() as conn:
            conn.execute(sql, (address.lower(), list_type))

    def find_address(self, address: str) -> Optional[sqlite3.Row]:
        """
        查询发件人是否在名单中。
        匹配顺序：精确地址 → 域名匹配（@domain.com）。
        白名单优先于黑名单返回。
        """
        address = address.lower()
        domain = "@" + address.split("@")[-1] if "@" in address else ""

        sql = """
            SELECT address, list_type FROM address_list
            WHERE address IN (?, ?)
            ORDER BY CASE list_type WHEN 'whitelist' THEN 0 ELSE 1 END
            LIMIT 1
        """
        with self._get_conn() as conn:
            row = conn.execute(sql, (address, domain)).fetchone()
            return row

    def count_sender_spam(self, sender: str) -> int:
        """统计某发件人在 email_log 中被归类为 spam 的历史次数（大小写不敏感）。"""
        sql = "SELECT COUNT(*) FROM email_log WHERE sender = ? AND category = 'spam'"
        with self._get_conn() as conn:
            return conn.execute(sql, (sender.lower(),)).fetchone()[0]

    def list_addresses(self, list_type: str) -> list:
        sql = "SELECT address, list_type, reason, created_at FROM address_list WHERE list_type = ?"
        with self._get_conn() as conn:
            return conn.execute(sql, (list_type,)).fetchall()

    # ── Web 管理层专用查询 ────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """仪表盘聚合统计：总数、今日数、各分类计数、名单数量、最后处理时间。"""
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM email_log").fetchone()[0]
            today = conn.execute(
                "SELECT COUNT(*) FROM email_log WHERE date(processed_at) = date('now')"
            ).fetchone()[0]
            last_at = conn.execute(
                "SELECT processed_at FROM email_log ORDER BY processed_at DESC LIMIT 1"
            ).fetchone()
            cats = conn.execute(
                "SELECT category, COUNT(*) FROM email_log GROUP BY category"
            ).fetchall()
            bl_count = conn.execute(
                "SELECT COUNT(*) FROM address_list WHERE list_type = 'blacklist'"
            ).fetchone()[0]
            wl_count = conn.execute(
                "SELECT COUNT(*) FROM address_list WHERE list_type = 'whitelist'"
            ).fetchone()[0]

        return {
            "total_processed": total,
            "today_count": today,
            "last_processed_at": last_at[0] if last_at else None,
            "category_counts": {row[0]: row[1] for row in cats},
            "blacklist_count": bl_count,
            "whitelist_count": wl_count,
        }

    def get_recent_logs(self, limit: int = 10) -> list:
        """最近 N 条处理记录（最新优先）。"""
        sql = """
            SELECT uid, sender, subject, category, action_code, confidence, reason, processed_at
            FROM email_log ORDER BY processed_at DESC LIMIT ?
        """
        with self._get_conn() as conn:
            return conn.execute(sql, (limit,)).fetchall()

    def get_category_trend(self, days: int = 7) -> list:
        """近 N 天各分类每日数量（用于图表）。"""
        sql = """
            SELECT category, date(processed_at) AS date, COUNT(*) AS count
            FROM email_log
            WHERE processed_at >= date('now', ?)
            GROUP BY category, date(processed_at)
            ORDER BY date
        """
        with self._get_conn() as conn:
            return conn.execute(sql, (f"-{days} days",)).fetchall()

    def query_email_logs(
        self,
        category: str = None,
        sender: str = None,
        date_from: str = None,
        date_to: str = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """分页查询邮件日志，支持分类/发件人/日期范围过滤。"""
        conditions = []
        params = []

        if category:
            conditions.append("category = ?")
            params.append(category)
        if sender:
            conditions.append("sender LIKE ?")
            params.append(f"%{sender.lower()}%")
        if date_from:
            conditions.append("date(processed_at) >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("date(processed_at) <= ?")
            params.append(date_to)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with self._get_conn() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM email_log {where}", params
            ).fetchone()[0]

            offset = (page - 1) * page_size
            items = conn.execute(
                f"""SELECT uid, sender, subject, category, action_code,
                           confidence, reason, processed_at
                    FROM email_log {where}
                    ORDER BY processed_at DESC
                    LIMIT ? OFFSET ?""",
                params + [page_size, offset],
            ).fetchall()

        return {"items": items, "total": total, "page": page, "page_size": page_size}
