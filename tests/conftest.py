"""
tests/conftest.py — 共享 fixture 与测试工具函数

所有 fixture 通过 tmp_path 隔离：每个测试函数获得独立的临时目录，
测试结束后自动清理，互不干扰。
"""

import pytest

from storage.db import Database
from modules.blacklist import BlacklistManager
from modules.mail_parser import MailParser
from modules.classifier import EmailClassifier


# ── 数据库 ────────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    """每个测试独立的已初始化 Database 实例。"""
    db_file = tmp_path / "test.db"
    database = Database(str(db_file))
    database.initialize()
    return database


# ── 黑白名单管理器 ────────────────────────────────────────────────────────────

@pytest.fixture
def blacklist_manager(db):
    """依赖 db fixture，确保每个测试使用空的黑白名单。"""
    return BlacklistManager(db)


# ── 邮件解析器 ────────────────────────────────────────────────────────────────

@pytest.fixture
def parser():
    """MailParser 无状态，无外部依赖，直接实例化。"""
    return MailParser()


# ── 分类器（使用虚假 settings，不调用真实 LLM）────────────────────────────────

class _FakeSettings:
    """仅提供 EmailClassifier.__init__ 所需的最小属性，不触及真实 API。"""
    dashscope_api_key = "fake-key-for-tests"
    qwen_model = "qwen-plus"


@pytest.fixture
def classifier():
    """
    返回 EmailClassifier 实例，_chain 保持 None。
    各测试通过直接赋值或 mock.patch 注入伪造的 chain，避免真实 LLM 调用。
    """
    return EmailClassifier(_FakeSettings())


# ── 邮件原始字节构造工具函数 ──────────────────────────────────────────────────

def build_plain_email(
    sender: str = "Test User <test@example.com>",
    subject: str = "Hello",
    body: str = "Plain text body.",
    charset: str = "utf-8",
) -> bytes:
    """构造最简单的纯文本邮件原始字节（RFC 2822 格式）。"""
    raw = (
        f"From: {sender}\r\n"
        f"Subject: {subject}\r\n"
        f"MIME-Version: 1.0\r\n"
        f"Content-Type: text/plain; charset={charset}\r\n"
        f"Content-Transfer-Encoding: 7bit\r\n"
        f"Date: Wed, 01 Jan 2025 00:00:00 +0000\r\n"
        f"\r\n"
        f"{body}"
    )
    return raw.encode(charset)


def build_html_email(
    sender: str = "html@example.com",
    subject: str = "HTML Mail",
    html_body: str = "<p>Hello <b>World</b></p>",
) -> bytes:
    """构造纯 HTML 邮件原始字节。"""
    raw = (
        f"From: {sender}\r\n"
        f"Subject: {subject}\r\n"
        f"MIME-Version: 1.0\r\n"
        f"Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Transfer-Encoding: 7bit\r\n"
        f"Date: Wed, 01 Jan 2025 00:00:00 +0000\r\n"
        f"\r\n"
        f"{html_body}"
    )
    return raw.encode("utf-8")


def build_multipart_email(
    sender: str = "multi@example.com",
    subject: str = "Multipart",
    plain_body: str = "plain part",
    html_body: str = "<p>html part</p>",
) -> bytes:
    """构造 multipart/alternative 邮件（同时含纯文本和 HTML part）。"""
    boundary = "==BOUNDARY_TEST=="
    raw = (
        f"From: {sender}\r\n"
        f"Subject: {subject}\r\n"
        f"MIME-Version: 1.0\r\n"
        f'Content-Type: multipart/alternative; boundary="{boundary}"\r\n'
        f"Date: Wed, 01 Jan 2025 00:00:00 +0000\r\n"
        f"\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"{plain_body}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: text/html; charset=utf-8\r\n"
        f"\r\n"
        f"{html_body}\r\n"
        f"--{boundary}--\r\n"
    )
    return raw.encode("utf-8")
