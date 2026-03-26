"""
tests/test_classifier.py — modules.classifier.EmailClassifier 单元测试

覆盖（_parse_output）：
  - 三种合法分类的正确解析
  - action_code 强制由 category 决定，不信任 LLM 返回值
  - 带前缀/后缀文字的 JSON（LLM 常见输出格式）
  - 未知 category → 降级为 normal
  - 无效 JSON → 降级为 fallback
  - confidence 越界夹紧 / 非数字使用默认值
  - reason 超 200 字符截断 / 缺失时为空字符串

覆盖（classify）：
  - chain.invoke 抛出异常时降级返回 normal（不传播异常）
  - chain.invoke 正常时返回正确分类
  - _chain 为 None 时懒加载 _build_chain
  - invoke 被调用时传入正确参数键
"""

import pytest
from unittest.mock import MagicMock, patch

from modules.classifier import (
    EmailClassifier,
    ClassificationResult,
    _FALLBACK_RESULT,
    _CATEGORY_TO_ACTION,
)
from modules.mail_parser import ParsedEmail


def _make_parsed_email(uid="uid-test"):
    return ParsedEmail(
        uid=uid,
        sender="test@example.com",
        sender_name="Test",
        subject="Test Subject",
        body="Test body content.",
        raw_date="",
    )


# ── _parse_output：正常 JSON ──────────────────────────────────────────────────

class TestParseOutputNormalJson:

    def test_spam_returns_correct_fields(self, classifier):
        raw = '{"category": "spam", "action_code": "DELETE_AND_BLOCK", "reason": "广告", "confidence": 0.95}'
        result = classifier._parse_output(raw)
        assert result.category == "spam"
        assert result.action_code == "DELETE_AND_BLOCK"
        assert result.confidence == pytest.approx(0.95)

    def test_normal_returns_correct_fields(self, classifier):
        raw = '{"category": "normal", "action_code": "MARK_READ_ARCHIVE", "reason": "日常", "confidence": 0.8}'
        result = classifier._parse_output(raw)
        assert result.category == "normal"
        assert result.action_code == "MARK_READ_ARCHIVE"

    def test_important_returns_correct_fields(self, classifier):
        raw = '{"category": "important", "action_code": "STAR_AND_NOTIFY", "reason": "会议", "confidence": 0.9}'
        result = classifier._parse_output(raw)
        assert result.category == "important"
        assert result.action_code == "STAR_AND_NOTIFY"

    def test_reason_is_preserved(self, classifier):
        raw = '{"category": "normal", "action_code": "MARK_READ_ARCHIVE", "reason": "普通邮件", "confidence": 0.7}'
        result = classifier._parse_output(raw)
        assert result.reason == "普通邮件"

    def test_confidence_preserved_when_in_range(self, classifier):
        raw = '{"category": "spam", "action_code": "DELETE_AND_BLOCK", "reason": "r", "confidence": 0.75}'
        result = classifier._parse_output(raw)
        assert result.confidence == pytest.approx(0.75)


# ── _parse_output：action_code 强制覆盖 ──────────────────────────────────────

class TestParseOutputActionCodeOverride:

    def test_wrong_action_code_corrected_by_category(self, classifier):
        """LLM 返回错误的 action_code 时，由 category 强制修正。"""
        raw = '{"category": "important", "action_code": "DELETE_AND_BLOCK", "reason": "r", "confidence": 0.9}'
        result = classifier._parse_output(raw)
        assert result.action_code == "STAR_AND_NOTIFY"

    def test_action_code_always_matches_category_for_all_types(self, classifier):
        """对所有合法 category，action_code 始终与 _CATEGORY_TO_ACTION 一致。"""
        for category, expected_action in _CATEGORY_TO_ACTION.items():
            raw = f'{{"category": "{category}", "action_code": "WRONG", "reason": "r", "confidence": 0.5}}'
            result = classifier._parse_output(raw)
            assert result.action_code == expected_action


# ── _parse_output：带前后缀文字的 JSON ───────────────────────────────────────

class TestParseOutputWithSurroundingText:

    def test_json_with_leading_text(self, classifier):
        raw = '好的，分类结果：\n{"category": "spam", "action_code": "x", "reason": "广告", "confidence": 0.92}'
        result = classifier._parse_output(raw)
        assert result.category == "spam"

    def test_json_with_trailing_text(self, classifier):
        raw = '{"category": "normal", "action_code": "x", "reason": "日常", "confidence": 0.8}\n以上结果供参考。'
        result = classifier._parse_output(raw)
        assert result.category == "normal"

    def test_json_surrounded_by_text(self, classifier):
        raw = (
            "分析如下：\n"
            '{"category": "important", "action_code": "x", "reason": "会议通知", "confidence": 0.95}\n'
            "请据此处理。"
        )
        result = classifier._parse_output(raw)
        assert result.category == "important"


# ── _parse_output：未知分类降级 ───────────────────────────────────────────────

class TestParseOutputUnknownCategory:

    def test_unknown_category_falls_back_to_normal(self, classifier):
        raw = '{"category": "unknown_type", "action_code": "SOME_CODE", "reason": "r", "confidence": 0.5}'
        result = classifier._parse_output(raw)
        assert result.category == "normal"
        assert result.action_code == "MARK_READ_ARCHIVE"

    def test_empty_category_falls_back_to_normal(self, classifier):
        raw = '{"category": "", "action_code": "", "reason": "r", "confidence": 0.5}'
        result = classifier._parse_output(raw)
        assert result.category == "normal"

    def test_missing_category_key_falls_back_to_normal(self, classifier):
        raw = '{"action_code": "SOME_CODE", "reason": "r", "confidence": 0.5}'
        result = classifier._parse_output(raw)
        assert result.category == "normal"


# ── _parse_output：无效 JSON ──────────────────────────────────────────────────

class TestParseOutputInvalidJson:

    def test_no_json_block_returns_fallback(self, classifier):
        """输出中完全没有 {} 时，返回 fallback。"""
        result = classifier._parse_output("无法理解邮件内容，请人工处理")
        assert result.category == _FALLBACK_RESULT["category"]
        assert result.confidence == _FALLBACK_RESULT["confidence"]

    def test_malformed_json_returns_fallback(self, classifier):
        """格式错误的 JSON 返回 fallback。"""
        result = classifier._parse_output("{category: spam, confidence: 0.9}")
        assert result.category == "normal"

    def test_empty_string_returns_fallback(self, classifier):
        result = classifier._parse_output("")
        assert result.category == _FALLBACK_RESULT["category"]

    def test_only_braces_with_garbage_returns_fallback(self, classifier):
        result = classifier._parse_output("{not valid json !!!}")
        assert result.category == "normal"


# ── _parse_output：confidence 边界处理 ───────────────────────────────────────

class TestParseOutputConfidence:

    def test_confidence_above_1_clamped_to_1(self, classifier):
        raw = '{"category": "spam", "action_code": "x", "reason": "r", "confidence": 1.5}'
        result = classifier._parse_output(raw)
        assert result.confidence == pytest.approx(1.0)

    def test_confidence_below_0_clamped_to_0(self, classifier):
        raw = '{"category": "spam", "action_code": "x", "reason": "r", "confidence": -0.3}'
        result = classifier._parse_output(raw)
        assert result.confidence == pytest.approx(0.0)

    def test_confidence_exactly_0_preserved(self, classifier):
        raw = '{"category": "normal", "action_code": "x", "reason": "r", "confidence": 0.0}'
        result = classifier._parse_output(raw)
        assert result.confidence == pytest.approx(0.0)

    def test_confidence_exactly_1_preserved(self, classifier):
        raw = '{"category": "important", "action_code": "x", "reason": "r", "confidence": 1.0}'
        result = classifier._parse_output(raw)
        assert result.confidence == pytest.approx(1.0)

    def test_non_numeric_confidence_uses_default(self, classifier):
        raw = '{"category": "spam", "action_code": "x", "reason": "r", "confidence": "high"}'
        result = classifier._parse_output(raw)
        assert result.confidence == pytest.approx(0.8)

    def test_null_confidence_uses_default(self, classifier):
        raw = '{"category": "normal", "action_code": "x", "reason": "r", "confidence": null}'
        result = classifier._parse_output(raw)
        assert result.confidence == pytest.approx(0.8)


# ── _parse_output：reason 字段 ────────────────────────────────────────────────

class TestParseOutputReason:

    def test_reason_truncated_to_200_chars(self, classifier):
        long_reason = "X" * 300
        raw = f'{{"category": "normal", "action_code": "x", "reason": "{long_reason}", "confidence": 0.5}}'
        result = classifier._parse_output(raw)
        assert len(result.reason) == 200

    def test_missing_reason_defaults_to_empty_string(self, classifier):
        raw = '{"category": "normal", "action_code": "x", "confidence": 0.5}'
        result = classifier._parse_output(raw)
        assert result.reason == ""


# ── classify()：mock chain 测试 ───────────────────────────────────────────────

class TestClassifyWithMockedChain:

    def test_successful_invoke_returns_correct_result(self, classifier):
        """chain.invoke 返回合法 JSON 时，classify 返回正确 ClassificationResult。"""
        valid_output = '{"category": "spam", "action_code": "x", "reason": "广告邮件", "confidence": 0.97}'
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = valid_output
        classifier._chain = mock_chain

        result = classifier.classify(_make_parsed_email())
        assert result.category == "spam"
        assert result.action_code == "DELETE_AND_BLOCK"

    def test_invoke_exception_falls_back_to_normal(self, classifier):
        """chain.invoke 抛出异常时，classify 不传播异常，降级返回 normal。"""
        mock_chain = MagicMock()
        mock_chain.invoke.side_effect = RuntimeError("network timeout")
        classifier._chain = mock_chain

        result = classifier.classify(_make_parsed_email())
        assert result.category == "normal"
        assert result.action_code == "MARK_READ_ARCHIVE"
        assert result.confidence == 0.0

    def test_invoke_exception_fallback_matches_fallback_result(self, classifier):
        """降级结果各字段与 _FALLBACK_RESULT 完全一致。"""
        mock_chain = MagicMock()
        mock_chain.invoke.side_effect = ConnectionError("API unreachable")
        classifier._chain = mock_chain

        result = classifier.classify(_make_parsed_email())
        assert result.category == _FALLBACK_RESULT["category"]
        assert result.action_code == _FALLBACK_RESULT["action_code"]
        assert result.reason == _FALLBACK_RESULT["reason"]
        assert result.confidence == _FALLBACK_RESULT["confidence"]

    def test_invoke_called_with_correct_keys(self, classifier):
        """chain.invoke 被调用时传入包含 sender/subject/content 键的字典。"""
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = (
            '{"category": "normal", "action_code": "x", "reason": "r", "confidence": 0.8}'
        )
        classifier._chain = mock_chain
        parsed = _make_parsed_email()

        classifier.classify(parsed)

        call_args = mock_chain.invoke.call_args[0][0]
        assert call_args["sender"] == parsed.sender
        assert call_args["subject"] == parsed.subject
        assert call_args["content"] == parsed.body

    def test_lazy_chain_build_when_chain_is_none(self, classifier):
        """_chain 为 None 时，classify 触发懒加载 _build_chain。"""
        assert classifier._chain is None
        valid_output = '{"category": "normal", "action_code": "x", "reason": "r", "confidence": 0.8}'

        def fake_build():
            mock = MagicMock()
            mock.invoke.return_value = valid_output
            classifier._chain = mock

        with patch.object(classifier, "_build_chain", side_effect=fake_build):
            result = classifier.classify(_make_parsed_email())

        assert result.category == "normal"
