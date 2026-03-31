"""
tests/test_scheduler.py — scheduler.EmailScheduler 单元测试

覆盖：
  - _process_one() 正常流程（parse → blacklist_check → classify → handle → log）
  - 黑名单快速拦截路径（跳过 LLM，confidence=1.0）
  - 白名单放行路径（跳过 LLM，category=normal）
  - LLM 分类后的 handle + notifier 联动
  - 单封邮件异常不影响流水线（异常被隔离）
  - _log() 写入的字段正确
"""

import pytest
from unittest.mock import MagicMock, patch, call

from scheduler import EmailScheduler
from modules.classifier import ClassificationResult
from modules.mail_parser import ParsedEmail


# ── Fixtures ──────────────────────────────────────────────────────────────────

class _FakeSettings:
    imap_host = "imap.example.com"
    imap_port = 993
    imap_username = "user@example.com"
    imap_password = "secret"
    dashscope_api_key = "fake-key"
    qwen_model = "qwen-plus"
    poll_interval_seconds = 300
    imap_timeout = 30
    spam_confidence_threshold = 0.90
    blacklist_threshold = 3
    quarantine_retention_days = 7
    review_retention_days = 14
    notify_channel = "log"
    notify_webhook_url = ""
    important_senders = []
    llm_circuit_breaker_threshold = 5
    llm_circuit_breaker_reset = 300
    llm_max_retries = 3


@pytest.fixture
def scheduler(db):
    """每个测试拥有独立 DB 实例的 EmailScheduler（不启动真实调度器）。"""
    return EmailScheduler(_FakeSettings(), db)


def _make_parsed(uid="100", sender="from@test.com", subject="Test Subject"):
    return ParsedEmail(
        uid=uid,
        sender=sender,
        sender_name="Test User",
        subject=subject,
        body="Test body content.",
        raw_date="Wed, 01 Jan 2025 00:00:00 +0000",
    )


def _make_fetcher(raw: bytes = b"From: from@test.com\r\nSubject: Test\r\n\r\nBody"):
    fetcher = MagicMock()
    fetcher.fetch_raw_email.return_value = raw
    return fetcher


def _make_handler():
    handler = MagicMock()
    return handler


# ── _process_one 正常流程 ──────────────────────────────────────────────────────

class TestProcessOneNormalFlow:

    def test_calls_fetch_raw_email_with_uid(self, scheduler, db):
        """_process_one 使用传入的 uid 调用 fetcher.fetch_raw_email。"""
        raw = b"From: test@example.com\r\nSubject: Hi\r\nContent-Type: text/plain\r\n\r\nHello"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        clf_result = ClassificationResult("normal", "MARK_READ_ARCHIVE", "test", 0.85)

        with patch.object(scheduler._classifier, "classify", return_value=clf_result):
            scheduler._process_one(42, fetcher, handler)

        fetcher.fetch_raw_email.assert_called_once_with(42)

    def test_writes_log_to_db_after_processing(self, scheduler, db):
        """处理完成后 email_log 中存在对应 uid 记录。"""
        raw = b"From: writer@example.com\r\nSubject: Log Test\r\nContent-Type: text/plain\r\n\r\nBody"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        clf_result = ClassificationResult("normal", "MARK_READ_ARCHIVE", "ok", 0.80)

        with patch.object(scheduler._classifier, "classify", return_value=clf_result):
            scheduler._process_one(55, fetcher, handler)

        assert db.is_uid_processed("55")

    def test_log_fields_match_classification_result(self, scheduler, db):
        """写入 DB 的 category、action_code、confidence、reason 与分类结果一致。"""
        raw = b"From: fields@example.com\r\nSubject: Fields\r\nContent-Type: text/plain\r\n\r\nBody"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        clf_result = ClassificationResult("spam", "DELETE_AND_BLOCK", "suspicious content", 0.95)

        with patch.object(scheduler._classifier, "classify", return_value=clf_result):
            scheduler._process_one(66, fetcher, handler)

        rows = db.query_email_logs(sender="fields@example.com")
        assert rows["total"] == 1
        item = rows["items"][0]
        assert item["category"] == "spam"
        assert item["action_code"] == "DELETE_AND_BLOCK"
        assert abs(item["confidence"] - 0.95) < 0.001
        assert item["reason"] == "suspicious content"

    def test_handler_handle_called_with_correct_args(self, scheduler, db):
        """handler.handle 被调用，传入 uid 和分类结果。"""
        raw = b"From: dispatch@example.com\r\nSubject: Dispatch\r\nContent-Type: text/plain\r\n\r\nBody"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        clf_result = ClassificationResult("newsletter", "MARK_READ_ARCHIVE", "newsletter", 0.90)

        with patch.object(scheduler._classifier, "classify", return_value=clf_result):
            scheduler._process_one(77, fetcher, handler)

        handler.handle.assert_called_once()
        args = handler.handle.call_args[0]
        assert args[0] == 77
        assert args[2].category == "newsletter"

    def test_important_email_triggers_notifier(self, scheduler, db):
        """分类为 important 时调用 notifier.notify_important。"""
        raw = b"From: boss@company.com\r\nSubject: Urgent\r\nContent-Type: text/plain\r\n\r\nUrgent"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        clf_result = ClassificationResult("important", "STAR_AND_NOTIFY", "VIP sender", 0.92)

        with patch.object(scheduler._classifier, "classify", return_value=clf_result):
            with patch.object(scheduler._notifier, "notify_important") as mock_notify:
                scheduler._process_one(88, fetcher, handler)

        mock_notify.assert_called_once()

    def test_classify_called_with_db(self, scheduler, db):
        """_process_one 调用 classify 时传入 db 实例，确保 Few-shot 纠错生效。"""
        raw = b"From: check@example.com\r\nSubject: DB arg\r\nContent-Type: text/plain\r\n\r\nCheck"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        clf_result = ClassificationResult("normal", "MARK_READ_ARCHIVE", "ok", 0.8)

        with patch.object(scheduler._classifier, "classify", return_value=clf_result) as mock_clf:
            scheduler._process_one(45, fetcher, handler)

        mock_clf.assert_called_once()
        _, kwargs = mock_clf.call_args
        assert kwargs.get("db") is db or mock_clf.call_args[0][1] is db

    def test_non_important_email_does_not_trigger_notifier(self, scheduler, db):
        """非 important 分类不调用 notifier。"""
        raw = b"From: normal@example.com\r\nSubject: Ads\r\nContent-Type: text/plain\r\n\r\nAds"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        clf_result = ClassificationResult("spam", "DELETE_AND_BLOCK", "spam", 0.95)

        with patch.object(scheduler._classifier, "classify", return_value=clf_result):
            with patch.object(scheduler._notifier, "notify_important") as mock_notify:
                scheduler._process_one(99, fetcher, handler)

        mock_notify.assert_not_called()


# ── 黑名单快速拦截路径 ────────────────────────────────────────────────────────

class TestProcessOneBlacklistPath:

    def test_blacklisted_sender_skips_llm(self, scheduler, db):
        """黑名单命中时不调用 LLM 分类器。"""
        raw = b"From: spammer@evil.com\r\nSubject: Spam\r\nContent-Type: text/plain\r\n\r\nSpam"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        scheduler._blacklist.add_to_blacklist("spammer@evil.com")

        with patch.object(scheduler._classifier, "classify") as mock_clf:
            scheduler._process_one(111, fetcher, handler)

        mock_clf.assert_not_called()

    def test_blacklisted_sender_logs_spam_with_full_confidence(self, scheduler, db):
        """黑名单命中时日志 confidence=1.0，category=spam，reason 含'黑名单'。"""
        raw = b"From: spammer@evil.com\r\nSubject: Spam\r\nContent-Type: text/plain\r\n\r\nSpam"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        scheduler._blacklist.add_to_blacklist("spammer@evil.com")

        scheduler._process_one(112, fetcher, handler)

        rows = db.query_email_logs(sender="spammer@evil.com")
        assert rows["total"] >= 1
        item = rows["items"][0]
        assert item["category"] == "spam"
        assert item["confidence"] == 1.0
        assert "黑名单" in item["reason"]

    def test_blacklisted_sender_calls_handle_spam(self, scheduler, db):
        """黑名单命中时调用 handler.handle_spam 而非 handler.handle。"""
        raw = b"From: spammer@evil.com\r\nSubject: Spam\r\nContent-Type: text/plain\r\n\r\nSpam"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        scheduler._blacklist.add_to_blacklist("spammer@evil.com")

        scheduler._process_one(113, fetcher, handler)

        handler.handle_spam.assert_called_once_with(113, "spammer@evil.com", confidence=1.0)
        handler.handle.assert_not_called()


# ── 白名单放行路径 ─────────────────────────────────────────────────────────────

class TestProcessOneWhitelistPath:

    def test_whitelisted_sender_skips_llm(self, scheduler, db):
        """白名单命中时不调用 LLM 分类器。"""
        raw = b"From: vip@corp.com\r\nSubject: VIP\r\nContent-Type: text/plain\r\n\r\nVIP"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        scheduler._blacklist.add_to_whitelist("vip@corp.com")

        with patch.object(scheduler._classifier, "classify") as mock_clf:
            scheduler._process_one(121, fetcher, handler)

        mock_clf.assert_not_called()

    def test_whitelisted_sender_logs_normal(self, scheduler, db):
        """白名单命中时日志 category=normal，reason 含'白名单'。"""
        raw = b"From: vip@corp.com\r\nSubject: VIP\r\nContent-Type: text/plain\r\n\r\nVIP"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        scheduler._blacklist.add_to_whitelist("vip@corp.com")

        scheduler._process_one(122, fetcher, handler)

        rows = db.query_email_logs(sender="vip@corp.com")
        assert rows["total"] >= 1
        item = rows["items"][0]
        assert item["category"] == "normal"
        assert "白名单" in item["reason"]

    def test_whitelisted_sender_calls_handle_normal(self, scheduler, db):
        """白名单命中时调用 handler.handle_normal 而非 handler.handle。"""
        raw = b"From: vip@corp.com\r\nSubject: VIP\r\nContent-Type: text/plain\r\n\r\nVIP"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        scheduler._blacklist.add_to_whitelist("vip@corp.com")

        scheduler._process_one(123, fetcher, handler)

        handler.handle_normal.assert_called_once_with(123)
        handler.handle.assert_not_called()


# ── 异常隔离 ──────────────────────────────────────────────────────────────────

class TestProcessOneExceptionIsolation:

    def test_fetch_exception_does_not_raise(self, scheduler, db):
        """fetch_raw_email 抛异常时 _process_one 不向上传播。"""
        fetcher = MagicMock()
        fetcher.fetch_raw_email.side_effect = ConnectionError("IMAP disconnected")
        handler = _make_handler()

        scheduler._process_one(200, fetcher, handler)  # 不应抛出

    def test_fetch_exception_does_not_write_db(self, scheduler, db):
        """fetch_raw_email 失败时不写入 email_log。"""
        fetcher = MagicMock()
        fetcher.fetch_raw_email.side_effect = ConnectionError("IMAP disconnected")
        handler = _make_handler()

        scheduler._process_one(201, fetcher, handler)

        assert not db.is_uid_processed("201")

    def test_classifier_exception_does_not_raise(self, scheduler, db):
        """分类器抛异常时 _process_one 不向上传播。"""
        raw = b"From: test@example.com\r\nSubject: X\r\nContent-Type: text/plain\r\n\r\nX"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()

        with patch.object(scheduler._classifier, "classify", side_effect=Exception("LLM timeout")):
            scheduler._process_one(202, fetcher, handler)  # 不应抛出

    def test_handler_exception_does_not_raise(self, scheduler, db):
        """handler.handle 抛异常时 _process_one 不向上传播。"""
        raw = b"From: test@example.com\r\nSubject: X\r\nContent-Type: text/plain\r\n\r\nX"
        fetcher = _make_fetcher(raw)
        handler = _make_handler()
        handler.handle.side_effect = Exception("IMAP copy failed")
        clf_result = ClassificationResult("normal", "MARK_READ_ARCHIVE", "ok", 0.8)

        with patch.object(scheduler._classifier, "classify", return_value=clf_result):
            scheduler._process_one(203, fetcher, handler)  # 不应抛出
