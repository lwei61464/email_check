"""
modules/rule_engine.py — 自定义规则匹配引擎
职责：在 LLM 分类之前，对邮件按用户配置的规则进行匹配。
      规则命中即返回强制分类，优先级高于 LLM。
"""

import re
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_VALID_FIELDS    = {"sender", "subject", "body"}
_VALID_OPERATORS = {"contains", "equals", "starts_with", "regex"}


class RuleEngine:
    _CACHE_TTL = 300  # 规则缓存有效期（秒），避免每封邮件都查库

    def __init__(self, db):
        self._db = db
        self._cache: list = []
        self._cache_ts: float = 0.0

    def match(self, parsed_email) -> Optional[str]:
        """
        按优先级顺序检测所有启用规则，命中第一条即返回对应 action_cat。
        未命中任何规则时返回 None（交由 LLM 处理）。
        规则列表缓存 5 分钟，减少重复数据库查询。
        """
        try:
            now = time.monotonic()
            if now - self._cache_ts > self._CACHE_TTL:
                self._cache = self._db.get_active_rules()
                self._cache_ts = now
            rules = self._cache
        except Exception as e:
            logger.warning("规则引擎加载失败，跳过规则匹配: %s", e)
            return None

        for rule in rules:
            if self._matches(rule, parsed_email):
                logger.info(
                    "规则命中: [%s] → %s（邮件 UID=%s）",
                    rule["name"], rule["action_cat"], parsed_email.uid,
                )
                return rule["action_cat"]
        return None

    def _matches(self, rule: dict, parsed_email) -> bool:
        field    = rule.get("field", "")
        operator = rule.get("operator", "")
        value    = rule.get("value", "")

        if field not in _VALID_FIELDS or operator not in _VALID_OPERATORS:
            return False

        text = self._get_field(parsed_email, field)
        if text is None:
            return False
        text_lower  = text.lower()
        value_lower = value.lower()

        try:
            if operator == "contains":
                return value_lower in text_lower
            elif operator == "equals":
                return text_lower == value_lower
            elif operator == "starts_with":
                return text_lower.startswith(value_lower)
            elif operator == "regex":
                return bool(re.search(value, text, re.IGNORECASE))
        except re.error as e:
            logger.warning("规则正则表达式无效 '%s': %s", value, e)
        return False

    @staticmethod
    def _get_field(parsed_email, field: str) -> Optional[str]:
        mapping = {
            "sender":  parsed_email.sender,
            "subject": parsed_email.subject,
            "body":    parsed_email.body,
        }
        return mapping.get(field)
