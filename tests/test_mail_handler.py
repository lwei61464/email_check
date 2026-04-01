"""
tests/test_mail_handler.py — modules.mail_handler.MailHandler 单元测试

覆盖：
  - handle() 路由：5 个分类分发到正确方法
  - handle_normal()        : copy 到 Archive，不设 SEEN
  - handle_important()     : INBOX 打星标 + copy 到 Important，不设 SEEN
  - handle_newsletter()    : copy 到 Newsletter，不设 SEEN
  - handle_transactional() : copy 到 Transactional，不设 SEEN
  - handle_spam()高置信    : copy 到 Quarantine + $Junk + try_auto_blacklist（达阈值）
  - handle_spam()低置信    : copy 到 Review，不写黑名单
  - _try_set_junk_flag()   : 服务器不支持时静默跳过
  - cleanup_quarantine()   : 调用 _cleanup_folder(QUARANTINE, ...)
  - cleanup_review()       : 调用 _cleanup_folder(REVIEW, ...)
  - _cleanup_folder()      : 文件夹不存在时直接返回；过期邮件被删除
"""

import pytest
from unittest.mock import MagicMock, call, patch
import imapclient

from modules.mail_handler import (
    MailHandler,
    FOLDER_ARCHIVE,
    FOLDER_IMPORTANT,
    FOLDER_NEWSLETTER,
    FOLDER_TRANSACTIONAL,
    FOLDER_QUARANTINE,
    FOLDER_REVIEW,
)
from modules.classifier import ClassificationResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def imap():
    client = MagicMock(spec=imapclient.IMAPClient)
    client.folder_exists.return_value = True
    return client


@pytest.fixture
def settings():
    s = MagicMock()
    s.spam_confidence_threshold = 0.90
    s.quarantine_retention_days = 7
    s.review_retention_days = 14
    s.folder_archive       = FOLDER_ARCHIVE
    s.folder_important     = FOLDER_IMPORTANT
    s.folder_newsletter    = FOLDER_NEWSLETTER
    s.folder_transactional = FOLDER_TRANSACTIONAL
    s.folder_quarantine    = FOLDER_QUARANTINE
    s.folder_review        = FOLDER_REVIEW
    return s


@pytest.fixture
def blacklist():
    return MagicMock()


@pytest.fixture
def handler(settings, imap, blacklist):
    return MailHandler(settings, imap, blacklist)


def _result(category: str, confidence: float = 0.95) -> ClassificationResult:
    from modules.classifier import _CATEGORY_TO_ACTION
    return ClassificationResult(
        category=category,
        action_code=_CATEGORY_TO_ACTION[category],
        reason="test",
        confidence=confidence,
    )


def _parsed(sender="sender@example.com"):
    p = MagicMock()
    p.sender = sender
    return p


# ── handle() 路由 ─────────────────────────────────────────────────────────────

class TestHandleRouting:

    def test_spam_routes_to_handle_spam(self, handler):
        with patch.object(handler, "handle_spam") as mock:
            handler.handle(1, _parsed(), _result("spam", 0.95))
            mock.assert_called_once_with(1, "sender@example.com", 0.95)

    def test_important_routes_to_handle_important(self, handler):
        with patch.object(handler, "handle_important") as mock:
            handler.handle(1, _parsed(), _result("important"))
            mock.assert_called_once_with(1)

    def test_newsletter_routes_to_handle_newsletter(self, handler):
        with patch.object(handler, "handle_newsletter") as mock:
            handler.handle(1, _parsed(), _result("newsletter"))
            mock.assert_called_once_with(1)

    def test_transactional_routes_to_handle_transactional(self, handler):
        with patch.object(handler, "handle_transactional") as mock:
            handler.handle(1, _parsed(), _result("transactional"))
            mock.assert_called_once_with(1)

    def test_normal_routes_to_handle_normal(self, handler):
        with patch.object(handler, "handle_normal") as mock:
            handler.handle(1, _parsed(), _result("normal"))
            mock.assert_called_once_with(1)


# ── 非破坏性策略：绝不设 SEEN ─────────────────────────────────────────────────

class TestNeverMarkSeen:
    """所有 handle_* 方法均不得调用 add_flags 设置 \\Seen。"""

    def _seen_calls(self, imap_mock) -> list:
        return [
            c for c in imap_mock.add_flags.call_args_list
            if imapclient.SEEN in (c.args[1] if c.args else c[1])
        ]

    def test_handle_normal_never_marks_seen(self, handler, imap):
        handler.handle_normal(1)
        assert self._seen_calls(imap) == []

    def test_handle_newsletter_never_marks_seen(self, handler, imap):
        handler.handle_newsletter(1)
        assert self._seen_calls(imap) == []

    def test_handle_transactional_never_marks_seen(self, handler, imap):
        handler.handle_transactional(1)
        assert self._seen_calls(imap) == []

    def test_handle_important_never_marks_seen(self, handler, imap):
        handler.handle_important(1)
        assert self._seen_calls(imap) == []

    def test_handle_spam_high_never_marks_seen(self, handler, imap):
        handler.handle_spam(1, "x@evil.com", confidence=0.95)
        assert self._seen_calls(imap) == []

    def test_handle_spam_low_never_marks_seen(self, handler, imap):
        handler.handle_spam(1, "x@evil.com", confidence=0.50)
        assert self._seen_calls(imap) == []


# ── 非破坏性策略：使用 COPY 而非 MOVE ────────────────────────────────────────

class TestCopyNotMove:
    """所有 handle_* 方法均使用 copy()，不调用 move()。"""

    def test_handle_normal_uses_copy(self, handler, imap):
        handler.handle_normal(1)
        imap.copy.assert_called_once_with([1], FOLDER_ARCHIVE)
        imap.move.assert_not_called()

    def test_handle_important_uses_copy(self, handler, imap):
        handler.handle_important(1)
        imap.copy.assert_called_once_with([1], FOLDER_IMPORTANT)
        imap.move.assert_not_called()

    def test_handle_newsletter_uses_copy(self, handler, imap):
        handler.handle_newsletter(1)
        imap.copy.assert_called_once_with([1], FOLDER_NEWSLETTER)
        imap.move.assert_not_called()

    def test_handle_transactional_uses_copy(self, handler, imap):
        handler.handle_transactional(1)
        imap.copy.assert_called_once_with([1], FOLDER_TRANSACTIONAL)
        imap.move.assert_not_called()

    def test_handle_spam_high_uses_copy_to_quarantine(self, handler, imap):
        handler.handle_spam(1, "x@evil.com", confidence=0.95)
        imap.copy.assert_called_once_with([1], FOLDER_QUARANTINE)
        imap.move.assert_not_called()

    def test_handle_spam_low_uses_copy_to_review(self, handler, imap):
        handler.handle_spam(1, "x@evil.com", confidence=0.50)
        imap.copy.assert_called_once_with([1], FOLDER_REVIEW)
        imap.move.assert_not_called()


# ── handle_important：INBOX 星标 ──────────────────────────────────────────────

class TestHandleImportant:

    def test_adds_flagged_to_inbox_copy(self, handler, imap):
        handler.handle_important(1)
        imap.add_flags.assert_called_once_with([1], [imapclient.FLAGGED])

    def test_copies_to_important_folder(self, handler, imap):
        handler.handle_important(1)
        imap.copy.assert_called_once_with([1], FOLDER_IMPORTANT)


# ── handle_spam：黑名单与 $Junk 逻辑 ─────────────────────────────────────────

class TestHandleSpam:

    def test_high_confidence_calls_try_auto_blacklist(self, handler, blacklist, settings):
        """高置信时调用 try_auto_blacklist，传入正确的 sender 和 threshold。"""
        settings.blacklist_threshold = 3
        blacklist.try_auto_blacklist.return_value = True
        handler.handle_spam(1, "spammer@evil.com", confidence=0.95)
        blacklist.try_auto_blacklist.assert_called_once()
        call_args = blacklist.try_auto_blacklist.call_args
        assert call_args[0][0] == "spammer@evil.com"   # sender
        assert call_args[0][1] == 3                     # threshold

    def test_high_confidence_below_threshold_no_blacklist(self, handler, blacklist, settings):
        """高置信但未达阈值时，try_auto_blacklist 返回 False，add_to_blacklist 不被直接调用。"""
        settings.blacklist_threshold = 3
        blacklist.try_auto_blacklist.return_value = False
        handler.handle_spam(1, "newspammer@evil.com", confidence=0.95)
        blacklist.try_auto_blacklist.assert_called_once()
        blacklist.add_to_blacklist.assert_not_called()

    def test_low_confidence_does_not_write_blacklist(self, handler, blacklist):
        handler.handle_spam(1, "maybe@spam.com", confidence=0.50)
        blacklist.try_auto_blacklist.assert_not_called()
        blacklist.add_to_blacklist.assert_not_called()

    def test_high_confidence_tries_junk_flag(self, handler, imap):
        handler.handle_spam(1, "x@evil.com", confidence=0.95)
        junk_calls = [c for c in imap.add_flags.call_args_list if b"$Junk" in c[0][1]]
        assert len(junk_calls) == 1

    def test_junk_flag_exception_does_not_propagate(self, handler, imap):
        imap.add_flags.side_effect = Exception("keyword not supported")
        # 不应抛出异常
        handler.handle_spam(1, "x@evil.com", confidence=0.95)

    def test_low_confidence_does_not_try_junk_flag(self, handler, imap):
        handler.handle_spam(1, "x@maybe.com", confidence=0.50)
        imap.add_flags.assert_not_called()


# ── cleanup ───────────────────────────────────────────────────────────────────

class TestCleanup:

    def test_cleanup_quarantine_skips_when_folder_missing(self, handler, imap):
        imap.folder_exists.return_value = False
        handler.cleanup_quarantine()
        imap.select_folder.assert_not_called()

    def test_cleanup_review_skips_when_folder_missing(self, handler, imap):
        imap.folder_exists.return_value = False
        handler.cleanup_review()
        imap.select_folder.assert_not_called()

    def test_cleanup_quarantine_deletes_old_messages(self, handler, imap):
        imap.folder_exists.return_value = True
        imap.search.return_value = [101, 102]
        handler.cleanup_quarantine()
        imap.delete_messages.assert_called_once_with([101, 102])
        imap.expunge.assert_called_once()

    def test_cleanup_review_deletes_old_messages(self, handler, imap):
        imap.folder_exists.return_value = True
        imap.search.return_value = [201]
        handler.cleanup_review()
        imap.delete_messages.assert_called_once_with([201])
        imap.expunge.assert_called_once()

    def test_cleanup_skips_delete_when_no_old_messages(self, handler, imap):
        imap.folder_exists.return_value = True
        imap.search.return_value = []
        handler.cleanup_quarantine()
        imap.delete_messages.assert_not_called()

    def test_cleanup_quarantine_uses_correct_retention(self, handler, imap, settings):
        """cleanup_quarantine 使用 quarantine_retention_days，不与 review 混用。"""
        imap.search.return_value = []
        settings.quarantine_retention_days = 3
        handler.cleanup_quarantine()
        search_args = imap.search.call_args[0][0]
        import datetime
        expected_cutoff = datetime.date.today() - datetime.timedelta(days=3)
        assert expected_cutoff in search_args

    def test_cleanup_review_uses_correct_retention(self, handler, imap, settings):
        """cleanup_review 使用 review_retention_days，不与 quarantine 混用。"""
        imap.search.return_value = []
        settings.review_retention_days = 14
        handler.cleanup_review()
        search_args = imap.search.call_args[0][0]
        import datetime
        expected_cutoff = datetime.date.today() - datetime.timedelta(days=14)
        assert expected_cutoff in search_args
