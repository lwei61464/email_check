"""
modules/notifier.py — 通知提醒模块
职责：当重要邮件被识别后触发通知提醒，支持多种通知渠道（策略模式），
      通知渠道通过配置切换，无需修改核心代码。
"""

import logging

import requests

logger = logging.getLogger(__name__)

CHANNEL_LOG = "log"
CHANNEL_WEBHOOK = "webhook"


class Notifier:
    def __init__(self, settings):
        self.settings = settings

    def notify_important(self, parsed_email, reason: str):
        """对重要邮件发送提醒通知，按配置渠道路由。"""
        channel = self.settings.notify_channel
        if channel == CHANNEL_WEBHOOK:
            self._notify_webhook(parsed_email, reason)
        else:
            self._notify_log(parsed_email, reason)

    def _notify_log(self, parsed_email, reason: str):
        """通过日志输出重要邮件提醒（开发/测试环境默认渠道）。"""
        logger.warning(
            "[重要邮件提醒] 发件人: %s <%s> | 主题: %s | 原因: %s",
            parsed_email.sender_name,
            parsed_email.sender,
            parsed_email.subject,
            reason,
        )

    def _notify_webhook(self, parsed_email, reason: str):
        """通过 HTTP POST 向 Webhook URL 推送通知（支持企业微信/钉钉/飞书等）。"""
        url = self.settings.notify_webhook_url
        if not url:
            logger.warning("notify_channel=webhook 但 NOTIFY_WEBHOOK_URL 未配置，降级为日志通知")
            self._notify_log(parsed_email, reason)
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
        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("Webhook 通知已发送，状态码: %s", resp.status_code)
        except requests.RequestException as e:
            logger.error("Webhook 通知失败: %s，降级为日志通知", e)
            self._notify_log(parsed_email, reason)
