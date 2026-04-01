"""
modules/classifier.py — 智能分类模块
职责：调用 LangChain + 通义千问（Qwen）对解析后的邮件进行智能分类，
      通过 Prompt 模板驱动分类逻辑，输出结构化分类结果（含置信度）。

故障容错策略：
  1. 指数退避重试（最多 llm_max_retries 次）
  2. 熔断器：连续失败达到阈值后开启，reset 秒后自动恢复
  3. 最终降级：关键词规则兜底，保证系统持续运行
"""

import json
import logging
import os
import time
import threading
from dataclasses import dataclass
from typing import Optional

from langchain_core.prompts import PromptTemplate
from langchain_community.chat_models import ChatTongyi
from langchain_core.output_parsers import StrOutputParser

from config.prompts import EMAIL_CLASSIFICATION_PROMPT, IMPORTANT_SENDERS_HINT_TEMPLATE

logger = logging.getLogger(__name__)

# 分类结果降级默认值（LLM 完全不可用时使用）
_FALLBACK_RESULT = {
    "category": "normal",
    "action_code": "MARK_READ_ARCHIVE",
    "reason": "LLM 调用失败，默认归为普通邮件",
    "confidence": 0.0,
}

# 合法枚举值校验集合
_VALID_CATEGORIES = {"spam", "transactional", "newsletter", "normal", "important"}
_CATEGORY_TO_ACTION = {
    "spam":          "DELETE_AND_BLOCK",
    "transactional": "MARK_READ_ARCHIVE",
    "newsletter":    "MARK_READ_ARCHIVE",
    "normal":        "MARK_READ_ARCHIVE",
    "important":     "STAR_AND_NOTIFY",
}

# 关键词降级规则（仅在 LLM 熔断期间使用）
_KEYWORD_RULES = [
    ("spam",      ["unsubscribe", "opt-out", "opt out", "promotion", "广告", "优惠券",
                   "限时", "特价", "free gift", "click here", "verify your account"]),
    ("important", ["紧急", "urgent", "action required", "deadline", "asap",
                   "需要确认", "请尽快", "立即处理", "overdue", "critical"]),
]


@dataclass
class ClassificationResult:
    category: str      # "spam" | "normal" | "important" | ...
    action_code: str   # "DELETE_AND_BLOCK" | "MARK_READ_ARCHIVE" | "STAR_AND_NOTIFY"
    reason: str
    confidence: float


class _CircuitBreaker:
    """简单熔断器：连续失败达阈值时开启，reset 秒后自动恢复。"""

    def __init__(self, threshold: int, reset_seconds: int):
        self._threshold = threshold
        self._reset_seconds = reset_seconds
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            if time.time() - self._opened_at >= self._reset_seconds:
                # 自动恢复，进入半开状态（下次调用重新尝试）
                self._failures = 0
                self._opened_at = None
                logger.info("熔断器已自动恢复，重新尝试 LLM 调用")
                return False
            return True

    def record_success(self):
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self):
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold and self._opened_at is None:
                self._opened_at = time.time()
                logger.warning(
                    "LLM 熔断器已开启（连续失败 %d 次），%d 秒后自动恢复，期间使用关键词降级",
                    self._failures, self._reset_seconds,
                )


class EmailClassifier:
    def __init__(self, settings):
        self.settings = settings
        self._chain = None
        self._circuit_breaker = _CircuitBreaker(
            threshold=settings.llm_circuit_breaker_threshold,
            reset_seconds=settings.llm_circuit_breaker_reset,
        )

    def _build_chain(self):
        """构建 LangChain 调用链：PromptTemplate → ChatTongyi → StrOutputParser"""
        os.environ.setdefault("DASHSCOPE_API_KEY", self.settings.dashscope_api_key)
        llm = ChatTongyi(
            model=self.settings.qwen_model,
            dashscope_api_key=self.settings.dashscope_api_key,
            temperature=0.1,
        )
        prompt = PromptTemplate(
            input_variables=["sender", "subject", "content", "attachments",
                             "important_senders_hint", "corrections_hint"],
            template=EMAIL_CLASSIFICATION_PROMPT,
        )
        self._chain = prompt | llm | StrOutputParser()
        logger.info("LangChain 调用链构建完成，模型: %s", self.settings.qwen_model)

    def _build_important_senders_hint(self) -> str:
        senders = getattr(self.settings, "important_senders", [])
        if not senders:
            return ""
        senders_list = "\n".join(f"  - {s}" for s in senders)
        return IMPORTANT_SENDERS_HINT_TEMPLATE.format(senders_list=senders_list)

    def _build_corrections_hint(self, db=None) -> str:
        """拉取最近纠错记录，构建 Few-shot 提示片段。db 为 None 时返回空字符串。"""
        if db is None:
            return ""
        try:
            corrections = db.get_recent_corrections(limit=8)
            if not corrections:
                return ""
            lines = "\n".join(
                f"  - 发件人: {c['sender'] or '?'} / 原判: {c['original_cat']} → 正确: {c['correct_cat']}"
                for c in corrections
            )
            return f"\n\n## 用户近期纠错记录（优先参考）\n{lines}"
        except Exception:
            return ""

    def classify(self, parsed_email, db=None) -> ClassificationResult:
        """
        对单封邮件进行智能分类。
        熔断器开启时跳过 LLM 直接使用关键词降级；
        LLM 失败时指数退避重试，彻底失败后关键词降级，保证流程不中断。
        """
        # 熔断器开启：直接关键词降级
        if self._circuit_breaker.is_open:
            return self._keyword_fallback(parsed_email, reason="LLM 熔断中，使用关键词降级")

        if self._chain is None:
            self._build_chain()

        max_retries = self.settings.llm_max_retries
        last_exc = None

        for attempt in range(max_retries):
            try:
                attachments = getattr(parsed_email, "attachments", None) or []
                attachments_str = ", ".join(attachments) if attachments else "无"
                raw_output = self._chain.invoke({
                    "sender":                 parsed_email.sender,
                    "subject":                parsed_email.subject,
                    "content":                parsed_email.body,
                    "attachments":            attachments_str,
                    "important_senders_hint": self._build_important_senders_hint(),
                    "corrections_hint":       self._build_corrections_hint(db),
                })
                result = self._parse_output(raw_output)
                self._circuit_breaker.record_success()
                return result

            except Exception as e:
                last_exc = e
                wait = 2 ** attempt          # 1s → 2s → 4s
                if attempt < max_retries - 1:
                    if self._is_fatal_error(e):
                        # 致命错误（认证/配额）不重试
                        break
                    logger.warning(
                        "LLM 调用失败（第 %d/%d 次），%ds 后重试。错误: %s",
                        attempt + 1, max_retries, wait, e,
                    )
                    time.sleep(wait)

        # 所有重试耗尽
        self._circuit_breaker.record_failure()
        self._log_llm_error(parsed_email.uid, last_exc)
        return self._keyword_fallback(parsed_email, reason="LLM 多次失败，使用关键词降级")

    def _keyword_fallback(self, parsed_email, reason: str) -> ClassificationResult:
        """关键词规则兜底分类，仅在 LLM 不可用时启用。"""
        text = f"{parsed_email.subject or ''} {parsed_email.body or ''}".lower()
        for category, keywords in _KEYWORD_RULES:
            if any(kw in text for kw in keywords):
                logger.info("关键词降级命中分类: %s（邮件 UID=%s）", category, parsed_email.uid)
                return ClassificationResult(
                    category=category,
                    action_code=_CATEGORY_TO_ACTION[category],
                    reason=reason,
                    confidence=0.5,
                )
        return ClassificationResult(**{**_FALLBACK_RESULT, "reason": reason})

    _FATAL_KEYWORDS = ("auth", "unauthorized", "forbidden", "invalid api key",
                       "quota", "rate limit", "access denied", "permission")

    def _is_fatal_error(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(kw in msg for kw in self._FATAL_KEYWORDS)

    def _log_llm_error(self, uid: str, exc: Exception):
        if exc and self._is_fatal_error(exc):
            logger.critical(
                "LLM 认证/配额错误（请检查 DASHSCOPE_API_KEY 或账户余额）"
                "——邮件 UID=%s 已降级。原始错误: %s", uid, exc
            )
        else:
            logger.error(
                "LLM 分类失败 [%s]（邮件 UID=%s），已降级。原始错误: %s",
                type(exc).__name__ if exc else "Unknown", uid, exc
            )

    def _parse_output(self, raw_output: str) -> ClassificationResult:
        """解析 LLM 输出的 JSON 字符串，容错处理枚举校验和 action_code 修正。"""
        text = raw_output.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            logger.warning("LLM 输出中未找到 JSON，原始输出: %s", text[:200])
            return ClassificationResult(**_FALLBACK_RESULT)

        try:
            data = json.loads(text[start:end])
        except json.JSONDecodeError as e:
            logger.warning("JSON 解析失败: %s，原始输出: %s", e, text[:200])
            return ClassificationResult(**_FALLBACK_RESULT)

        category = str(data.get("category", "normal")).lower()
        if category not in _VALID_CATEGORIES:
            logger.warning("LLM 返回未知分类 '%s'，降级为 normal", category)
            category = "normal"

        action_code = _CATEGORY_TO_ACTION[category]

        try:
            confidence = float(data.get("confidence", 0.8))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.8

        return ClassificationResult(
            category=category,
            action_code=action_code,
            reason=str(data.get("reason", ""))[:200],
            confidence=confidence,
        )
