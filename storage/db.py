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

DDL_CUSTOM_RULES = """
CREATE TABLE IF NOT EXISTS custom_rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    field      TEXT NOT NULL,
    operator   TEXT NOT NULL,
    value      TEXT NOT NULL,
    action_cat TEXT NOT NULL,
    priority   INTEGER DEFAULT 0,
    enabled    INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now','localtime'))
)
"""

DDL_CORRECTION_LOG = """
CREATE TABLE IF NOT EXISTS correction_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    email_uid    TEXT NOT NULL,
    sender       TEXT,
    subject      TEXT,
    original_cat TEXT NOT NULL,
    correct_cat  TEXT NOT NULL,
    corrected_at TEXT DEFAULT (datetime('now','localtime'))
)
"""

DDL_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
)
"""

DDL_SCAN_TASK = """
CREATE TABLE IF NOT EXISTS scan_task (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    status      TEXT NOT NULL DEFAULT 'pending',
    days_back   INTEGER NOT NULL,
    dry_run     INTEGER NOT NULL DEFAULT 0,
    total       INTEGER DEFAULT 0,
    processed   INTEGER DEFAULT 0,
    error_msg   TEXT,
    started_at  TEXT DEFAULT (datetime('now','localtime')),
    finished_at TEXT
)
"""

DDL_PROCESS_METRICS = """
CREATE TABLE IF NOT EXISTS process_metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_time REAL,
    llm_time      REAL,
    llm_success   INTEGER,
    email_count   INTEGER,
    error_count   INTEGER,
    recorded_at   TEXT DEFAULT (datetime('now','localtime'))
)
"""

# 当前 schema 版本（每次结构性变更递增）
_SCHEMA_VERSION = 1

# 迁移脚本：key 为目标版本号，value 为升级 SQL 列表
_MIGRATIONS: dict = {
    # 版本 1 通过 initialize() 中的 DDL_* 建表完成，无需额外迁移 SQL
}


def _get_schema_version(conn) -> int:
    try:
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0


def _set_schema_version(conn, version: int):
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))


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
        """初始化数据库，创建所有必要的表并执行 schema 迁移（幂等）。"""
        with self._get_conn() as conn:
            # WAL 模式：提升并发读写性能，减少锁争用
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(DDL_EMAIL_LOG)
            conn.execute(DDL_ADDRESS_LIST)
            conn.execute(DDL_CORRECTION_LOG)
            conn.execute(DDL_CUSTOM_RULES)
            conn.execute(DDL_SCHEMA_VERSION)
            conn.execute(DDL_PROCESS_METRICS)
            conn.execute(DDL_SCAN_TASK)

            current = _get_schema_version(conn)
            if current < _SCHEMA_VERSION:
                for ver in range(current + 1, _SCHEMA_VERSION + 1):
                    for sql in _MIGRATIONS.get(ver, []):
                        conn.execute(sql)
                        logger.info("数据库迁移：执行版本 %d SQL", ver)
                _set_schema_version(conn, _SCHEMA_VERSION)
                logger.info("数据库 schema 已更新至版本 %d", _SCHEMA_VERSION)

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

    def get_email_by_uid(self, uid: str) -> Optional[sqlite3.Row]:
        """按 UID 查询单封邮件记录，不存在时返回 None。"""
        sql = """
            SELECT uid, sender, subject, category, action_code, confidence, reason, processed_at
            FROM email_log WHERE uid = ?
        """
        with self._get_conn() as conn:
            return conn.execute(sql, (uid,)).fetchone()

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
            # 合并总数 + 今日数 + 最后时间为一次查询
            row = conn.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN date(processed_at) = date('now') THEN 1 ELSE 0 END) AS today,
                    MAX(processed_at) AS last_at
                FROM email_log
            """).fetchone()
            total   = row[0] or 0
            today   = row[1] or 0
            last_at = row[2]

            cats = conn.execute(
                "SELECT category, COUNT(*) FROM email_log GROUP BY category"
            ).fetchall()

            # 合并黑白名单计数为一次查询
            list_counts = {
                r[0]: r[1]
                for r in conn.execute(
                    "SELECT list_type, COUNT(*) FROM address_list GROUP BY list_type"
                ).fetchall()
            }

        return {
            "total_processed": total,
            "today_count": today,
            "last_processed_at": last_at,
            "category_counts": {row[0]: row[1] for row in cats},
            "blacklist_count": list_counts.get("blacklist", 0),
            "whitelist_count": list_counts.get("whitelist", 0),
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

    # ── 自定义规则 ────────────────────────────────────────────────────────────

    def get_active_rules(self) -> list:
        """获取所有启用的规则，按优先级降序。"""
        sql = """
            SELECT id, name, field, operator, value, action_cat, priority, enabled, created_at
            FROM custom_rules WHERE enabled = 1 ORDER BY priority DESC, id ASC
        """
        with self._get_conn() as conn:
            return [dict(r) for r in conn.execute(sql).fetchall()]

    def get_all_rules(self) -> list:
        """获取所有规则（含禁用），供管理页面展示。"""
        sql = """
            SELECT id, name, field, operator, value, action_cat, priority, enabled, created_at
            FROM custom_rules ORDER BY priority DESC, id ASC
        """
        with self._get_conn() as conn:
            return [dict(r) for r in conn.execute(sql).fetchall()]

    def insert_rule(self, name: str, field: str, operator: str, value: str,
                    action_cat: str, priority: int = 0) -> int:
        sql = """
            INSERT INTO custom_rules (name, field, operator, value, action_cat, priority)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        with self._get_conn() as conn:
            cur = conn.execute(sql, (name, field, operator, value, action_cat, priority))
            return cur.lastrowid

    def update_rule(self, rule_id: int, name: str, field: str, operator: str,
                    value: str, action_cat: str, priority: int, enabled: int):
        sql = """
            UPDATE custom_rules
            SET name=?, field=?, operator=?, value=?, action_cat=?, priority=?, enabled=?
            WHERE id=?
        """
        with self._get_conn() as conn:
            conn.execute(sql, (name, field, operator, value, action_cat, priority, enabled, rule_id))

    def delete_rule(self, rule_id: int):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM custom_rules WHERE id = ?", (rule_id,))

    # ── 纠错记录 ──────────────────────────────────────────────────────────────

    def insert_correction(self, email_uid: str, sender: str, subject: str,
                          original_cat: str, correct_cat: str):
        sql = """
            INSERT INTO correction_log (email_uid, sender, subject, original_cat, correct_cat)
            VALUES (?, ?, ?, ?, ?)
        """
        with self._get_conn() as conn:
            conn.execute(sql, (email_uid, sender, subject, original_cat, correct_cat))

    def get_recent_corrections(self, limit: int = 10) -> list:
        """拉取最近纠错记录，供 classifier Few-shot 注入使用。"""
        sql = """
            SELECT email_uid, sender, subject, original_cat, correct_cat, corrected_at
            FROM correction_log
            ORDER BY corrected_at DESC, id DESC
            LIMIT ?
        """
        with self._get_conn() as conn:
            rows = conn.execute(sql, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def update_email_category(self, uid: str, category: str, action_code: str):
        """更新 email_log 中某封邮件的分类（用户纠错后同步）。"""
        sql = "UPDATE email_log SET category = ?, action_code = ? WHERE uid = ?"
        with self._get_conn() as conn:
            conn.execute(sql, (category, action_code, uid))

    # ── 处理指标 ──────────────────────────────────────────────────────────────

    def insert_metrics(self, pipeline_time: float, llm_time: float,
                       llm_success: int, email_count: int, error_count: int):
        sql = """
            INSERT INTO process_metrics
                (pipeline_time, llm_time, llm_success, email_count, error_count)
            VALUES (?, ?, ?, ?, ?)
        """
        with self._get_conn() as conn:
            conn.execute(sql, (pipeline_time, llm_time, llm_success, email_count, error_count))

    # ── 历史扫描任务 ──────────────────────────────────────────────────────────

    def create_scan_task(self, days_back: int, dry_run: bool) -> int:
        sql = "INSERT INTO scan_task (days_back, dry_run) VALUES (?, ?)"
        with self._get_conn() as conn:
            cur = conn.execute(sql, (days_back, 1 if dry_run else 0))
            return cur.lastrowid

    def update_scan_task(self, task_id: int, status: str, total: int = 0,
                         processed: int = 0, error_msg: str = None, finished: bool = False):
        sql = """
            UPDATE scan_task
            SET status=?, total=?, processed=?, error_msg=?,
                finished_at = CASE WHEN ? THEN datetime('now','localtime') ELSE finished_at END
            WHERE id=?
        """
        with self._get_conn() as conn:
            conn.execute(sql, (status, total, processed, error_msg, 1 if finished else 0, task_id))

    def get_scan_task(self, task_id: int) -> dict:
        sql = "SELECT * FROM scan_task WHERE id = ?"
        with self._get_conn() as conn:
            row = conn.execute(sql, (task_id,)).fetchone()
            return dict(row) if row else {}

    def get_metrics_trend(self, days: int = 7) -> list:
        """近 N 天的指标记录（最新在后）。"""
        sql = """
            SELECT pipeline_time, llm_time, llm_success, email_count, error_count, recorded_at
            FROM process_metrics
            WHERE recorded_at >= datetime('now', ?)
            ORDER BY recorded_at ASC
        """
        with self._get_conn() as conn:
            return [dict(r) for r in conn.execute(sql, (f"-{days} days",)).fetchall()]
