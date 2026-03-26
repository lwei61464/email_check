"""
modules/classifier.py — 智能分类模块
职责：调用 LangChain + 通义千问（Qwen）对解析后的邮件进行智能分类，
      通过 Prompt 模板驱动分类逻辑，输出结构化分类结果（含置信度）。
      分类规则完全由 LLM 推理，禁止硬编码关键词匹配。
"""

import json
import logging
import os
from dataclasses import dataclass

from langchain_core.prompts import PromptTemplate
from langchain_community.chat_models import ChatTongyi
from langchain_core.output_parsers import StrOutputParser

from config.prompts import EMAIL_CLASSIFICATION_PROMPT, IMPORTANT_SENDERS_HINT_TEMPLATE

logger = logging.getLogger(__name__)

# 分类结果降级默认值（LLM 调用失败时使用）
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


@dataclass
class ClassificationResult:
    category: str      # "spam" | "normal" | "important"
    action_code: str   # "DELETE_AND_BLOCK" | "MARK_READ_ARCHIVE" | "STAR_AND_NOTIFY"
    reason: str
    confidence: float


class EmailClassifier:
    def __init__(self, settings):
        self.settings = settings
        self._chain = None

    def _build_chain(self):
        """构建 LangChain 调用链：PromptTemplate → ChatTongyi → StrOutputParser"""
        os.environ.setdefault("DASHSCOPE_API_KEY", self.settings.dashscope_api_key)

        llm = ChatTongyi(
            model=self.settings.qwen_model,
            dashscope_api_key=self.settings.dashscope_api_key,
            temperature=0.1,   # 低温度保证分类输出稳定
        )
        prompt = PromptTemplate(
            input_variables=["sender", "subject", "content", "important_senders_hint"],
            template=EMAIL_CLASSIFICATION_PROMPT,
        )
        self._chain = prompt | llm | StrOutputParser()
        logger.info("LangChain 调用链构建完成，模型: %s", self.settings.qwen_model)

    def _build_important_senders_hint(self) -> str:
        """根据配置构建重要发件人提示片段，未配置时返回空字符串。"""
        senders = getattr(self.settings, "important_senders", [])
        if not senders:
            return ""
        senders_list = "\n".join(f"  - {s}" for s in senders)
        return IMPORTANT_SENDERS_HINT_TEMPLATE.format(senders_list=senders_list)

    def classify(self, parsed_email) -> ClassificationResult:
        """
        对单封邮件进行智能分类。
        LLM 调用失败时降级为 normal，不抛出异常，保证流程不中断。
        """
        if self._chain is None:
            self._build_chain()

        try:
            raw_output = self._chain.invoke({
                "sender":                 parsed_email.sender,
                "subject":                parsed_email.subject,
                "content":                parsed_email.body,
                "important_senders_hint": self._build_important_senders_hint(),
            })
            return self._parse_output(raw_output)
        except Exception as e:
            self._log_llm_error(parsed_email.uid, e)
            return ClassificationResult(**_FALLBACK_RESULT)

    # 致命错误关键词：出现这些词说明配置有误，重试无效
    _FATAL_KEYWORDS = ("auth", "unauthorized", "forbidden", "invalid api key",
                       "quota", "rate limit", "access denied", "permission")

    def _log_llm_error(self, uid: str, exc: Exception):
        """区分致命错误与可重试错误，输出不同级别的日志提示。"""
        msg = str(exc).lower()
        if any(kw in msg for kw in self._FATAL_KEYWORDS):
            logger.critical(
                "LLM 认证/配额错误（请检查 DASHSCOPE_API_KEY 或账户余额）"
                "——邮件 UID=%s 已降级为 normal。原始错误: %s", uid, exc
            )
        else:
            logger.error(
                "LLM 分类失败 [%s]（邮件 UID=%s），已降级为 normal。原始错误: %s",
                type(exc).__name__, uid, exc
            )

    def _parse_output(self, raw_output: str) -> ClassificationResult:
        """
        解析 LLM 输出的 JSON 字符串。
        容错处理：提取 JSON 块、校验枚举值、修正 action_code 与 category 不一致。
        """
        # 提取 JSON 块（LLM 有时会在 JSON 前后添加说明文字）
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

        # 强制 action_code 与 category 保持一致，不信任 LLM 的 action_code
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
