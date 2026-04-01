"""
modules/mail_parser.py — 邮件解析模块
职责：将 IMAP 获取的原始邮件字节流解析为结构化数据，
      提取发件人、主题、正文（纯文本），处理编码与 HTML 转换。
"""

import email
import email.header
import email.utils
import logging
from dataclasses import dataclass
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ParsedEmail:
    uid: str
    sender: str              # 发件人邮箱地址（纯地址）
    sender_name: str         # 发件人显示名称
    subject: str             # 邮件主题
    body: str                # 正文纯文本
    raw_date: str            # 原始日期字符串
    attachments: list = None  # 附件文件名列表（解析后填充）

    def __post_init__(self):
        if self.attachments is None:
            self.attachments = []


class MailParser:
    def parse(self, uid: str, raw_bytes: bytes) -> ParsedEmail:
        msg = email.message_from_bytes(raw_bytes)
        sender_name, sender_addr = self._extract_sender_address(msg.get("From", ""))
        subject = self._decode_header(msg.get("Subject", "（无主题）"))
        body = self._extract_body(msg)
        raw_date = msg.get("Date", "")
        attachments = self._extract_attachments(msg)
        return ParsedEmail(
            uid=uid,
            sender=sender_addr,
            sender_name=sender_name,
            subject=subject,
            body=body[:3000],   # 截断过长正文，降低 Token 消耗
            raw_date=raw_date,
            attachments=attachments,
        )

    def _decode_header(self, header_value: str) -> str:
        if not header_value:
            return ""
        parts = email.header.decode_header(header_value)
        decoded_parts = []
        for fragment, charset in parts:
            if isinstance(fragment, bytes):
                try:
                    decoded_parts.append(fragment.decode(charset or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    decoded_parts.append(fragment.decode("utf-8", errors="replace"))
            else:
                decoded_parts.append(fragment)
        return "".join(decoded_parts)

    def _extract_body(self, msg) -> str:
        plain_text = ""
        html_text = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in disposition:
                    continue
                if ctype == "text/plain" and not plain_text:
                    plain_text = self._decode_payload(part)
                elif ctype == "text/html" and not html_text:
                    html_text = self._decode_payload(part)
        else:
            ctype = msg.get_content_type()
            if ctype == "text/plain":
                plain_text = self._decode_payload(msg)
            elif ctype == "text/html":
                html_text = self._decode_payload(msg)

        if plain_text:
            return plain_text.strip()
        if html_text:
            soup = BeautifulSoup(html_text, "html.parser")
            return soup.get_text(separator="\n").strip()
        return "（正文为空）"

    def _decode_payload(self, part) -> str:
        payload = part.get_payload(decode=True)
        if not payload:
            return ""
        charset = part.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            return payload.decode("utf-8", errors="replace")

    def _extract_attachments(self, msg) -> list:
        """提取附件文件名列表（跳过内嵌图片等非真正附件）。"""
        names = []
        if msg.is_multipart():
            for part in msg.walk():
                disposition = str(part.get("Content-Disposition", ""))
                if "attachment" not in disposition:
                    continue
                filename = part.get_filename()
                if filename:
                    names.append(self._decode_header(filename))
        return names

    def _extract_sender_address(self, from_field: str) -> tuple:
        name_raw, addr = email.utils.parseaddr(from_field)
        name = self._decode_header(name_raw) if name_raw else addr.split("@")[0]
        return name, addr.lower()
