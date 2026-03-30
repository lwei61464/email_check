"""
modules/blacklist.py — 黑白名单管理模块
职责：维护发件人黑名单与白名单，在 LLM 分类之前提供快速拦截/放行判断，
      支持精确邮箱地址匹配和域名级别匹配（如 @spam.com）。
      白名单优先级高于黑名单（白名单覆盖黑名单）。
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

LIST_TYPE_BLACKLIST = "blacklist"
LIST_TYPE_WHITELIST = "whitelist"


class BlacklistManager:
    def __init__(self, db):
        self.db = db

    def check(self, sender_address: str) -> Optional[str]:
        """
        检查发件人是否命中黑名单或白名单。

        :return: "blacklist" | "whitelist" | None
        """
        row = self.db.find_address(sender_address)
        if row is None:
            return None
        return row["list_type"]

    def add_to_blacklist(self, address: str, reason: str = ""):
        self.db.upsert_address(address, LIST_TYPE_BLACKLIST, reason)
        logger.info("加入黑名单: %s（原因: %s）", address, reason or "无")

    def add_to_whitelist(self, address: str, reason: str = ""):
        self.db.upsert_address(address, LIST_TYPE_WHITELIST, reason)
        logger.info("加入白名单: %s（原因: %s）", address, reason or "无")

    def remove(self, address: str, list_type: str):
        self.db.delete_address(address, list_type)
        logger.info("从 %s 移除: %s", list_type, address)

    def list_all(self, list_type: str) -> list:
        return self.db.list_addresses(list_type)

    def try_auto_blacklist(self, sender: str, threshold: int, reason: str = "") -> bool:
        """
        检查发件人历史 spam 次数，累计达到阈值时才自动加入黑名单。

        计数基于 email_log 中已有记录（不含当前正在处理的邮件）：
          - 历史次数 >= threshold - 1 → 本次触发，加入黑名单，返回 True
          - 历史次数 <  threshold - 1 → 未达阈值，仅记录日志，返回 False

        :param sender:    发件人地址
        :param threshold: 加入黑名单所需的累计 spam 次数（含本次）
        :param reason:    加入原因
        :return: 是否已加入黑名单
        """
        existing_count = self.db.count_sender_spam(sender)
        if existing_count >= threshold - 1:
            self.add_to_blacklist(sender, reason)
            logger.info("发件人 %s 累计 %d 次 spam，达到阈值 %d，已加入黑名单",
                        sender, existing_count + 1, threshold)
            return True
        logger.info("发件人 %s 已记录 %d 次 spam，阈值 %d，暂不加入黑名单",
                    sender, existing_count + 1, threshold)
        return False
