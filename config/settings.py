"""
config/settings.py — 配置加载模块
职责：从 .env 文件读取所有系统配置，提供统一的配置访问接口，
      确保密钥等敏感信息不硬编码在代码中。
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # IMAP 配置
    imap_host: str = field(default_factory=lambda: os.getenv("IMAP_HOST", ""))
    imap_port: int = field(default_factory=lambda: int(os.getenv("IMAP_PORT", "993")))
    imap_username: str = field(default_factory=lambda: os.getenv("IMAP_USERNAME", ""))
    imap_password: str = field(default_factory=lambda: os.getenv("IMAP_PASSWORD", ""))

    # Qwen / DashScope 配置
    dashscope_api_key: str = field(default_factory=lambda: os.getenv("DASHSCOPE_API_KEY", ""))
    qwen_model: str = field(default_factory=lambda: os.getenv("QWEN_MODEL", "qwen-plus"))

    # 系统行为配置
    poll_interval_seconds: int = field(
        default_factory=lambda: int(os.getenv("POLL_INTERVAL_SECONDS", "300"))
    )
    imap_timeout: int = field(
        default_factory=lambda: int(os.getenv("IMAP_TIMEOUT", "30"))
    )
    spam_confidence_threshold: float = field(
        default_factory=lambda: float(os.getenv("SPAM_CONFIDENCE_THRESHOLD", "0.90"))
    )
    # 同一发件人被判定为 spam 累计达到此次数后，才自动加入黑名单
    blacklist_threshold: int = field(
        default_factory=lambda: int(os.getenv("BLACKLIST_THRESHOLD", "3"))
    )
    quarantine_retention_days: int = field(
        default_factory=lambda: int(os.getenv("QUARANTINE_RETENTION_DAYS", "7"))
    )

    # 数据存储
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "storage/email_sorter.db"))

    # 通知配置
    notify_channel: str = field(default_factory=lambda: os.getenv("NOTIFY_CHANNEL", "log"))
    notify_webhook_url: str = field(default_factory=lambda: os.getenv("NOTIFY_WEBHOOK_URL", ""))

    # 重要发件人白名单（逗号分隔，支持完整地址或 @domain.com 格式）
    important_senders: list = field(
        default_factory=lambda: [
            s.strip().lower()
            for s in os.getenv("IMPORTANT_SENDERS", "").split(",")
            if s.strip()
        ]
    )

    # Review 文件夹保留天数（低置信 spam 待审核区）
    review_retention_days: int = field(
        default_factory=lambda: int(os.getenv("REVIEW_RETENTION_DAYS", "14"))
    )

    def validate(self):
        """校验必填配置项，缺失时抛出异常。"""
        required = {
            "IMAP_HOST": self.imap_host,
            "IMAP_USERNAME": self.imap_username,
            "IMAP_PASSWORD": self.imap_password,
            "DASHSCOPE_API_KEY": self.dashscope_api_key,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"缺少必要配置项: {', '.join(missing)}")
