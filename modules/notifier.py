"""
modules/notifier.py — 通知提醒模块
职责：当重要邮件被识别后触发通知提醒，支持多种通知渠道（策略模式）。
      通知渠道通过 NOTIFY_CHANNEL 配置切换，无需修改核心代码。

支持渠道：
  log       — 仅日志输出（默认，开发/测试用）
  webhook   — 通用 Webhook（旧值，向下兼容，行为等同 dingtalk）
  dingtalk  — 钉钉机器人（text 消息类型）
  feishu    — 飞书机器人（text 消息类型）
  slack     — Slack Incoming Webhook（text 消息类型）
"""

import logging

import requests

logger = logging.getLogger(__name__)

# 向下兼容旧配置值
CHANNEL_LOG      = "log"
CHANNEL_WEBHOOK  = "webhook"   # 保留旧值
CHANNEL_DINGTALK = "dingtalk"
CHANNEL_FEISHU   = "feishu"
CHANNEL_SLACK    = "slack"


class _BaseNotifier:
    def notify(self, parsed_email, reason: str):
        raise NotImplementedError


class _LogNotifier(_BaseNotifier):
    def notify(self, parsed_email, reason: str):
        logger.warning(
            "[重要邮件提醒] 发件人: %s <%s> | 主题: %s | 原因: %s",
            parsed_email.sender_name,
            parsed_email.sender,
            parsed_email.subject,
            reason,
        )


class _DingTalkNotifier(_BaseNotifier):
    """钉钉自定义机器人 Webhook（text 类型）。"""

    def __init__(self, webhook_url: str, fallback: _BaseNotifier):
        self._url = webhook_url
        self._fallback = fallback

    def notify(self, parsed_email, reason: str):
        if not self._url:
            logger.warning("DINGTALK/WEBHOOK 渠道未配置 NOTIFY_WEBHOOK_URL，降级日志通知")
            self._fallback.notify(parsed_email, reason)
            return
        payload = {
            "msgtype": "text",
            "text": {
                "content": (
                    f"[邮件系统重要提醒]\n"
                    f"发件人: {parsed_email.sender_name} <{parsed_email.sender}>\n"
                    f"主题: {parsed_email.subject}\n"
                    f"原因: {reason}"
                )
            },
        }
        self._post(payload)

    def _post(self, payload: dict):
        try:
            resp = requests.post(self._url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("DingTalk 通知已发送，状态码: %s", resp.status_code)
        except requests.RequestException as e:
            logger.error("DingTalk 通知失败: %s", e)


class _FeishuNotifier(_BaseNotifier):
    """飞书自定义机器人 Webhook（text 类型）。"""

    def __init__(self, webhook_url: str, fallback: _BaseNotifier):
        self._url = webhook_url
        self._fallback = fallback

    def notify(self, parsed_email, reason: str):
        if not self._url:
            logger.warning("FEISHU 渠道未配置 NOTIFY_WEBHOOK_URL，降级日志通知")
            self._fallback.notify(parsed_email, reason)
            return
        content = (
            f"【重要邮件提醒】\n"
            f"发件人: {parsed_email.sender_name} <{parsed_email.sender}>\n"
            f"主题: {parsed_email.subject}\n"
            f"原因: {reason}"
        )
        payload = {"msg_type": "text", "content": {"text": content}}
        try:
            resp = requests.post(self._url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("飞书通知已发送，状态码: %s", resp.status_code)
        except requests.RequestException as e:
            logger.error("飞书通知失败: %s", e)


class _SlackNotifier(_BaseNotifier):
    """Slack Incoming Webhook（text 类型）。"""

    def __init__(self, webhook_url: str, fallback: _BaseNotifier):
        self._url = webhook_url
        self._fallback = fallback

    def notify(self, parsed_email, reason: str):
        if not self._url:
            logger.warning("SLACK 渠道未配置 NOTIFY_WEBHOOK_URL，降级日志通知")
            self._fallback.notify(parsed_email, reason)
            return
        text = (
            f"*重要邮件提醒*\n"
            f"发件人: {parsed_email.sender_name} <{parsed_email.sender}>\n"
            f"主题: {parsed_email.subject}\n"
            f"原因: {reason}"
        )
        payload = {"text": text}
        try:
            resp = requests.post(self._url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("Slack 通知已发送，状态码: %s", resp.status_code)
        except requests.RequestException as e:
            logger.error("Slack 通知失败: %s", e)


def _build_notifier(settings) -> _BaseNotifier:
    channel = getattr(settings, "notify_channel", "log").lower()
    webhook_url = getattr(settings, "notify_webhook_url", "")
    log_notifier = _LogNotifier()

    if channel in (CHANNEL_WEBHOOK, CHANNEL_DINGTALK):
        return _DingTalkNotifier(webhook_url, log_notifier)
    elif channel == CHANNEL_FEISHU:
        return _FeishuNotifier(webhook_url, log_notifier)
    elif channel == CHANNEL_SLACK:
        return _SlackNotifier(webhook_url, log_notifier)
    else:
        return log_notifier


class Notifier:
    def __init__(self, settings):
        self.settings = settings
        self._impl = _build_notifier(settings)
        self._notify_categories = set(
            getattr(settings, "notify_on_categories", ["important"])
        )

    def notify_important(self, parsed_email, reason: str):
        """对重要邮件发送提醒通知，按配置渠道路由。"""
        self._impl.notify(parsed_email, reason)

    def should_notify(self, category: str) -> bool:
        """判断该分类是否需要触发通知。"""
        return category in self._notify_categories
