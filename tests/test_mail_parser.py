"""
tests/test_mail_parser.py — modules.mail_parser.MailParser 单元测试

覆盖：
  - sender 地址提取（小写、纯地址）
  - sender_name 提取（有无显示名称）
  - subject 提取（ASCII / Base64 / QP 编码 / 缺失）
  - body 提取（纯文本 / HTML 转文本 / multipart 优先纯文本 / 截断 / 空正文）
  - uid 原样保留
  - raw_date 提取（有 / 无 Date 头）
"""

import base64
import pytest

from modules.mail_parser import MailParser, ParsedEmail
from tests.conftest import (
    build_plain_email,
    build_html_email,
    build_multipart_email,
)


class TestParseSender:

    def test_extracts_sender_address_as_lowercase(self, parser):
        """From 头含大写邮箱时，sender 转小写。"""
        raw = build_plain_email(sender="Alice <ALICE@EXAMPLE.COM>")
        result = parser.parse("uid-1", raw)
        assert result.sender == "alice@example.com"

    def test_extracts_display_name_as_sender_name(self, parser):
        """From 头含显示名称时，sender_name 正确提取。"""
        raw = build_plain_email(sender="Alice Smith <alice@example.com>")
        result = parser.parse("uid-2", raw)
        assert result.sender_name == "Alice Smith"

    def test_uses_local_part_as_name_when_no_display_name(self, parser):
        """From 头无显示名称时，sender_name 取邮箱本地部分。"""
        raw = build_plain_email(sender="plain@example.com")
        result = parser.parse("uid-3", raw)
        assert result.sender_name == "plain"

    def test_preserves_uid(self, parser):
        """ParsedEmail.uid 与传入的 uid 参数完全一致。"""
        raw = build_plain_email()
        result = parser.parse("my-unique-id-42", raw)
        assert result.uid == "my-unique-id-42"


class TestParseSubject:

    def test_ascii_subject_extracted_as_is(self, parser):
        """普通 ASCII 主题原样提取。"""
        raw = build_plain_email(subject="Meeting Tomorrow")
        result = parser.parse("uid-4", raw)
        assert result.subject == "Meeting Tomorrow"

    def test_base64_encoded_subject_decoded(self, parser):
        """=?utf-8?B?...?= 编码的中文主题正确解码。"""
        chinese = "重要通知"
        b64 = base64.b64encode(chinese.encode("utf-8")).decode()
        encoded_subject = f"=?utf-8?B?{b64}?="
        raw = build_plain_email(subject=encoded_subject)
        result = parser.parse("uid-5", raw)
        assert result.subject == chinese

    def test_qp_encoded_subject_decoded(self, parser):
        """=?utf-8?Q?...?= 编码的主题正确解码。"""
        text = "Reunion"
        encoded_subject = f"=?utf-8?Q?{text}?="
        raw = build_plain_email(subject=encoded_subject)
        result = parser.parse("uid-6", raw)
        assert result.subject == text

    def test_missing_subject_returns_placeholder(self, parser):
        """无 Subject 头时返回占位符。"""
        raw = (
            b"From: a@b.com\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"body"
        )
        result = parser.parse("uid-7", raw)
        assert result.subject == "\uff08\u65e0\u4e3b\u9898\uff09" or "无主题" in result.subject or result.subject == "（无主题）"


class TestParseBody:

    def test_plain_text_body_extracted(self, parser):
        """纯文本邮件正文正确提取。"""
        raw = build_plain_email(body="Hello, World!")
        result = parser.parse("uid-8", raw)
        assert result.body == "Hello, World!"

    def test_html_body_converted_to_plain_text(self, parser):
        """HTML 邮件正文通过 BeautifulSoup 转为纯文本，HTML 标签被去除。"""
        raw = build_html_email(html_body="<p>Hello <b>World</b></p>")
        result = parser.parse("uid-9", raw)
        assert "Hello" in result.body
        assert "World" in result.body
        assert "<p>" not in result.body
        assert "<b>" not in result.body

    def test_multipart_prefers_plain_text_over_html(self, parser):
        """multipart 邮件存在 text/plain part 时优先使用。"""
        raw = build_multipart_email(
            plain_body="I am the plain text.",
            html_body="<p>I am the HTML.</p>",
        )
        result = parser.parse("uid-10", raw)
        assert "I am the plain text." in result.body

    def test_body_truncated_to_3000_chars(self, parser):
        """超过 3000 字符的正文被截断至恰好 3000 字符。"""
        long_body = "A" * 5000
        raw = build_plain_email(body=long_body)
        result = parser.parse("uid-11", raw)
        assert len(result.body) == 3000

    def test_body_not_truncated_when_under_3000_chars(self, parser):
        """不超过 3000 字符的正文长度不变。"""
        short_body = "B" * 100
        raw = build_plain_email(body=short_body)
        result = parser.parse("uid-12", raw)
        assert len(result.body) == 100

    def test_empty_body_returns_placeholder(self, parser):
        """无正文内容时返回占位符。"""
        raw = (
            b"From: a@b.com\r\n"
            b"Subject: test\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
        )
        result = parser.parse("uid-13", raw)
        assert "正文为空" in result.body or result.body == "（正文为空）"


class TestParseDate:

    def test_extracts_raw_date_header(self, parser):
        """raw_date 字段保留 Date 头的原始字符串。"""
        raw = build_plain_email()
        result = parser.parse("uid-14", raw)
        assert result.raw_date == "Wed, 01 Jan 2025 00:00:00 +0000"

    def test_missing_date_returns_empty_string(self, parser):
        """无 Date 头时 raw_date 为空字符串。"""
        raw = (
            b"From: a@b.com\r\n"
            b"Subject: test\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"body"
        )
        result = parser.parse("uid-15", raw)
        assert result.raw_date == ""
