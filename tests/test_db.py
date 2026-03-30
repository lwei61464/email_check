"""
tests/test_db.py — storage.db.Database 单元测试

覆盖：
  - initialize() 建表 & 幂等性
  - insert_email_log() 插入与幂等（重复 uid 忽略）
  - is_uid_processed()
  - upsert_address() 幂等性与小写归一化
  - delete_address()
  - find_address() 精确匹配、域名匹配、白名单优先、未命中返回 None
  - list_addresses()
"""

import sqlite3
import pytest
from storage.db import Database


# ── initialize ────────────────────────────────────────────────────────────────

class TestInitialize:

    def test_creates_email_log_table(self, db):
        """initialize() 后 email_log 表存在。"""
        with sqlite3.connect(db.db_path) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        assert "email_log" in tables

    def test_creates_address_list_table(self, db):
        """initialize() 后 address_list 表存在。"""
        with sqlite3.connect(db.db_path) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        assert "address_list" in tables

    def test_initialize_is_idempotent(self, tmp_path):
        """多次调用 initialize() 不抛出异常（CREATE TABLE IF NOT EXISTS）。"""
        database = Database(str(tmp_path / "idempotent.db"))
        database.initialize()
        database.initialize()


# ── insert_email_log / is_uid_processed ──────────────────────────────────────

class TestEmailLog:

    def test_insert_stores_record(self, db):
        """插入一条记录后 is_uid_processed 返回 True。"""
        db.insert_email_log("uid-001", "a@b.com", "Subject", "normal",
                            "MARK_READ_ARCHIVE", 0.9, "reason")
        assert db.is_uid_processed("uid-001") is True

    def test_unknown_uid_returns_false(self, db):
        """未插入的 uid 返回 False。"""
        assert db.is_uid_processed("nonexistent-uid") is False

    def test_duplicate_uid_is_silently_ignored(self, db):
        """重复 uid 的第二次插入被静默忽略，数据库中只有一条记录。"""
        db.insert_email_log("uid-dup", "a@b.com", "S1", "normal",
                            "MARK_READ_ARCHIVE", 0.9, "first")
        db.insert_email_log("uid-dup", "x@y.com", "S2", "spam",
                            "DELETE_AND_BLOCK", 0.5, "second")
        with sqlite3.connect(db.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM email_log WHERE uid='uid-dup'"
            ).fetchone()[0]
        assert count == 1

    def test_multiple_different_uids_all_inserted(self, db):
        """不同 uid 的邮件均可正常插入并被检测到。"""
        db.insert_email_log("uid-A", "a@b.com", "SA", "spam",
                            "DELETE_AND_BLOCK", 0.99, "r")
        db.insert_email_log("uid-B", "b@c.com", "SB", "important",
                            "STAR_AND_NOTIFY", 0.95, "r")
        assert db.is_uid_processed("uid-A") is True
        assert db.is_uid_processed("uid-B") is True


# ── upsert_address ────────────────────────────────────────────────────────────

class TestUpsertAddress:

    def test_new_address_is_inserted(self, db):
        """upsert 新地址后 find_address 可查到。"""
        db.upsert_address("spam@bad.com", "blacklist", "known spammer")
        row = db.find_address("spam@bad.com")
        assert row is not None
        assert row["list_type"] == "blacklist"

    def test_address_is_normalized_to_lowercase(self, db):
        """大写地址存储后小写可查。"""
        db.upsert_address("UPPER@EXAMPLE.COM", "whitelist")
        row = db.find_address("upper@example.com")
        assert row is not None

    def test_upsert_is_idempotent(self, db):
        """同一地址重复 upsert 不抛出异常，只保留一条记录。"""
        db.upsert_address("once@example.com", "blacklist", "r1")
        db.upsert_address("once@example.com", "blacklist", "r2")
        with sqlite3.connect(db.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM address_list WHERE address='once@example.com'"
            ).fetchone()[0]
        assert count == 1


# ── delete_address ────────────────────────────────────────────────────────────

class TestDeleteAddress:

    def test_delete_removes_existing_entry(self, db):
        """插入后删除，find_address 返回 None。"""
        db.upsert_address("gone@example.com", "blacklist")
        db.delete_address("gone@example.com", "blacklist")
        assert db.find_address("gone@example.com") is None

    def test_delete_nonexistent_does_not_raise(self, db):
        """删除不存在的地址不抛出异常。"""
        db.delete_address("nobody@nowhere.com", "blacklist")

    def test_delete_only_removes_specified_list_type(self, db):
        """删除黑名单条目不影响同一地址的白名单条目。"""
        db.upsert_address("both@example.com", "blacklist")
        db.upsert_address("both@example.com", "whitelist")
        db.delete_address("both@example.com", "blacklist")
        row = db.find_address("both@example.com")
        assert row is not None
        assert row["list_type"] == "whitelist"


# ── find_address ──────────────────────────────────────────────────────────────

class TestFindAddress:

    def test_exact_match(self, db):
        """精确地址命中返回对应行。"""
        db.upsert_address("exact@domain.com", "blacklist")
        row = db.find_address("exact@domain.com")
        assert row is not None
        assert row["address"] == "exact@domain.com"

    def test_domain_level_match(self, db):
        """精确地址不存在时，匹配 @domain.com 域名条目。"""
        db.upsert_address("@domain.com", "blacklist", "whole domain blocked")
        row = db.find_address("anyone@domain.com")
        assert row is not None
        assert row["list_type"] == "blacklist"

    def test_whitelist_priority_over_blacklist_same_address(self, db):
        """同一精确地址同时在黑白名单时，白名单优先。"""
        db.upsert_address("vip@example.com", "blacklist")
        db.upsert_address("vip@example.com", "whitelist")
        row = db.find_address("vip@example.com")
        assert row["list_type"] == "whitelist"

    def test_returns_none_when_no_match(self, db):
        """既无精确匹配也无域名匹配时返回 None。"""
        row = db.find_address("stranger@unknown.com")
        assert row is None

    def test_query_is_case_insensitive(self, db):
        """查询时地址大小写不影响匹配结果。"""
        db.upsert_address("lower@example.com", "whitelist")
        row = db.find_address("LOWER@EXAMPLE.COM")
        assert row is not None

    def test_no_false_domain_match_across_different_domains(self, db):
        """不同域名的域名规则不会互相干扰。"""
        db.upsert_address("@evil.com", "blacklist")
        row = db.find_address("user@good.com")
        assert row is None


# ── list_addresses ────────────────────────────────────────────────────────────

class TestListAddresses:

    def test_returns_only_requested_list_type(self, db):
        """list_addresses('blacklist') 只返回黑名单条目。"""
        db.upsert_address("bl@example.com", "blacklist")
        db.upsert_address("wl@example.com", "whitelist")
        rows = db.list_addresses("blacklist")
        assert len(rows) == 1
        assert rows[0]["address"] == "bl@example.com"

    def test_returns_empty_list_when_no_entries(self, db):
        """空数据库返回空列表，不抛出异常。"""
        assert db.list_addresses("blacklist") == []

    def test_returns_all_entries_of_requested_type(self, db):
        """list_addresses 返回该类型下的所有条目。"""
        db.upsert_address("a@x.com", "blacklist")
        db.upsert_address("b@x.com", "blacklist")
        db.upsert_address("c@x.com", "blacklist")
        rows = db.list_addresses("blacklist")
        addresses = [r["address"] for r in rows]
        assert len(rows) == 3
        assert "a@x.com" in addresses
        assert "b@x.com" in addresses
        assert "c@x.com" in addresses


# ── count_sender_spam ─────────────────────────────────────────────────────────

class TestCountSenderSpam:

    def test_returns_zero_when_no_records(self, db):
        """没有任何日志时，spam 计数返回 0。"""
        assert db.count_sender_spam("new@example.com") == 0

    def test_counts_only_spam_category(self, db):
        """只统计 category='spam' 的记录，其他分类不计入。"""
        db.insert_email_log("uid-n1", "sender@x.com", "S", "normal",    "MARK_READ_ARCHIVE", 0.9, "")
        db.insert_email_log("uid-i1", "sender@x.com", "S", "important", "STAR_AND_NOTIFY",   0.9, "")
        db.insert_email_log("uid-s1", "sender@x.com", "S", "spam",      "DELETE_AND_BLOCK",  0.95, "")
        assert db.count_sender_spam("sender@x.com") == 1

    def test_counts_multiple_spam_records(self, db):
        """同一发件人的多条 spam 记录正确累加。"""
        db.insert_email_log("uid-s1", "repeat@evil.com", "S1", "spam", "DELETE_AND_BLOCK", 0.95, "")
        db.insert_email_log("uid-s2", "repeat@evil.com", "S2", "spam", "DELETE_AND_BLOCK", 0.97, "")
        db.insert_email_log("uid-s3", "repeat@evil.com", "S3", "spam", "DELETE_AND_BLOCK", 0.98, "")
        assert db.count_sender_spam("repeat@evil.com") == 3

    def test_is_case_insensitive(self, db):
        """sender 查询大小写不敏感。"""
        db.insert_email_log("uid-s1", "spammer@evil.com", "S", "spam", "DELETE_AND_BLOCK", 0.95, "")
        assert db.count_sender_spam("SPAMMER@EVIL.COM") == 1

    def test_does_not_count_other_senders(self, db):
        """不统计其他发件人的 spam 记录。"""
        db.insert_email_log("uid-s1", "a@evil.com", "S", "spam", "DELETE_AND_BLOCK", 0.95, "")
        db.insert_email_log("uid-s2", "b@evil.com", "S", "spam", "DELETE_AND_BLOCK", 0.95, "")
        assert db.count_sender_spam("a@evil.com") == 1


# ── get_stats ─────────────────────────────────────────────────────────────────

class TestGetStats:

    def test_returns_zero_when_empty(self, db):
        """空数据库时所有计数均为 0。"""
        stats = db.get_stats()
        assert stats["total_processed"] == 0
        assert stats["today_count"] == 0
        assert stats["last_processed_at"] is None
        assert stats["category_counts"] == {}
        assert stats["blacklist_count"] == 0
        assert stats["whitelist_count"] == 0

    def test_counts_total_correctly(self, db):
        """total_processed 等于 email_log 中的记录数。"""
        db.insert_email_log("u1", "a@x.com", "S", "spam", "DELETE_AND_BLOCK", 0.9, "")
        db.insert_email_log("u2", "b@x.com", "S", "normal", "MARK_READ_ARCHIVE", 0.8, "")
        assert db.get_stats()["total_processed"] == 2

    def test_category_counts_aggregated(self, db):
        """category_counts 正确统计各分类数量。"""
        db.insert_email_log("u1", "a@x.com", "S", "spam", "DELETE_AND_BLOCK", 0.9, "")
        db.insert_email_log("u2", "b@x.com", "S", "spam", "DELETE_AND_BLOCK", 0.9, "")
        db.insert_email_log("u3", "c@x.com", "S", "normal", "MARK_READ_ARCHIVE", 0.8, "")
        stats = db.get_stats()
        assert stats["category_counts"]["spam"] == 2
        assert stats["category_counts"]["normal"] == 1

    def test_blacklist_whitelist_count(self, db):
        """blacklist_count 和 whitelist_count 正确反映名单数量。"""
        db.upsert_address("a@spam.com", "blacklist")
        db.upsert_address("b@spam.com", "blacklist")
        db.upsert_address("c@good.com", "whitelist")
        stats = db.get_stats()
        assert stats["blacklist_count"] == 2
        assert stats["whitelist_count"] == 1


# ── get_recent_logs ───────────────────────────────────────────────────────────

class TestGetRecentLogs:

    def test_returns_empty_when_no_records(self, db):
        """无记录时返回空列表。"""
        assert db.get_recent_logs() == []

    def test_returns_latest_first(self, db):
        """结果按 processed_at 倒序排列（最新在前）。"""
        import sqlite3
        # 直接写入不同时间戳以确保排序稳定
        with sqlite3.connect(db.db_path) as conn:
            conn.execute(
                "INSERT INTO email_log (uid, sender, subject, category, action_code, confidence, reason, processed_at)"
                " VALUES ('u1', 'a@x.com', 'S1', 'normal', 'MARK_READ_ARCHIVE', 0.8, '', '2025-01-01 10:00:00')"
            )
            conn.execute(
                "INSERT INTO email_log (uid, sender, subject, category, action_code, confidence, reason, processed_at)"
                " VALUES ('u2', 'b@x.com', 'S2', 'spam', 'DELETE_AND_BLOCK', 0.9, '', '2025-01-01 11:00:00')"
            )
            conn.commit()
        rows = db.get_recent_logs(2)
        # u2 时间更晚，应排在前面
        assert dict(rows[0])["uid"] == "u2"

    def test_limit_respected(self, db):
        """limit 参数控制返回数量。"""
        for i in range(5):
            db.insert_email_log(f"u{i}", f"a{i}@x.com", "S", "normal", "MARK_READ_ARCHIVE", 0.8, "")
        assert len(db.get_recent_logs(3)) == 3


# ── query_email_logs ──────────────────────────────────────────────────────────

class TestQueryEmailLogs:

    def test_returns_all_when_no_filters(self, db):
        """无筛选条件时返回全部记录。"""
        db.insert_email_log("u1", "a@x.com", "S", "spam", "DELETE_AND_BLOCK", 0.9, "")
        db.insert_email_log("u2", "b@x.com", "S", "normal", "MARK_READ_ARCHIVE", 0.8, "")
        result = db.query_email_logs(page=1, page_size=20)
        assert result["total"] == 2
        assert len(result["items"]) == 2

    def test_filter_by_category(self, db):
        """category 筛选只返回对应分类记录。"""
        db.insert_email_log("u1", "a@x.com", "S", "spam", "DELETE_AND_BLOCK", 0.9, "")
        db.insert_email_log("u2", "b@x.com", "S", "normal", "MARK_READ_ARCHIVE", 0.8, "")
        result = db.query_email_logs(category="spam", page=1, page_size=20)
        assert result["total"] == 1
        assert dict(result["items"][0])["category"] == "spam"

    def test_filter_by_sender(self, db):
        """sender 筛选支持模糊匹配。"""
        db.insert_email_log("u1", "target@evil.com", "S", "spam", "DELETE_AND_BLOCK", 0.9, "")
        db.insert_email_log("u2", "other@good.com", "S", "normal", "MARK_READ_ARCHIVE", 0.8, "")
        result = db.query_email_logs(sender="evil", page=1, page_size=20)
        assert result["total"] == 1

    def test_pagination(self, db):
        """分页正确：page_size=2 时第1页返回最新2条，第2页返回剩余。"""
        for i in range(5):
            db.insert_email_log(f"u{i}", f"a{i}@x.com", "S", "normal", "MARK_READ_ARCHIVE", 0.8, "")
        r1 = db.query_email_logs(page=1, page_size=2)
        r2 = db.query_email_logs(page=2, page_size=2)
        assert r1["total"] == 5
        assert len(r1["items"]) == 2
        assert len(r2["items"]) == 2

    def test_returns_empty_when_no_match(self, db):
        """筛选无匹配时返回空列表，total=0。"""
        result = db.query_email_logs(category="spam", page=1, page_size=20)
        assert result["total"] == 0
        assert result["items"] == []
