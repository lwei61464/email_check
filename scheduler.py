"""
scheduler.py — 定时任务调度模块
职责：使用 APScheduler 定时触发邮件检测与处理流程，驱动系统主循环。
      串联 MailFetcher / MailParser / BlacklistManager / EmailClassifier / MailHandler / Notifier。
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from modules.mail_fetcher import MailFetcher
from modules.mail_parser import MailParser
from modules.blacklist import BlacklistManager
from modules.classifier import EmailClassifier
from modules.mail_handler import MailHandler
from modules.notifier import Notifier

logger = logging.getLogger(__name__)


class EmailScheduler:
    def __init__(self, settings, db):
        self.settings = settings
        self.db = db
        self._scheduler = BlockingScheduler(timezone="Asia/Shanghai")

        # 初始化无状态模块（可复用于每次流水线）
        self._parser = MailParser()
        self._blacklist = BlacklistManager(db)
        self._classifier = EmailClassifier(settings)
        self._notifier = Notifier(settings)

    def _run_pipeline(self):
        """
        单次完整邮件处理流水线：
        IMAP 连接 → 获取新邮件 → 逐封处理 → 断开连接
        """
        fetcher = MailFetcher(self.settings, self.db)
        try:
            fetcher.connect()
            new_uids = fetcher.fetch_new_uids()
            if not new_uids:
                logger.info("本轮无新邮件")
                return

            handler = MailHandler(self.settings, fetcher.client, self._blacklist)

            for uid in new_uids:
                self._process_one(uid, fetcher, handler)

            # 定期清理过期邮件
            handler.cleanup_quarantine()
            handler.cleanup_review()

        except Exception as e:
            logger.error("流水线执行异常: %s", e, exc_info=True)
        finally:
            fetcher.disconnect()

    def _process_one(self, uid: int, fetcher: MailFetcher, handler: MailHandler):
        """
        处理单封邮件：解析 → 黑白名单检查 → LLM 分类 → 执行动作 → 写日志。
        单封邮件异常不影响后续邮件处理。
        """
        try:
            # 1. 获取原始邮件并解析
            raw_bytes = fetcher.fetch_raw_email(uid)
            parsed = self._parser.parse(str(uid), raw_bytes)
            logger.info("处理邮件 UID=%s | 发件人: %s | 主题: %s",
                        uid, parsed.sender, parsed.subject)

            # 2. 黑名单检查（最高优先级，命中直接删除，跳过 LLM）
            list_result = self._blacklist.check(parsed.sender)
            if list_result == "blacklist":
                handler.handle_spam(uid, parsed.sender, confidence=1.0)
                self._log(parsed, "spam", "DELETE_AND_BLOCK", 1.0, "黑名单命中，直接拦截")
                return

            # 3. 白名单检查（强制归为 normal，跳过 LLM）
            if list_result == "whitelist":
                handler.handle_normal(uid)
                self._log(parsed, "normal", "MARK_READ_ARCHIVE", 1.0, "白名单放行，复制到 Archive")
                return

            # 4. LLM 智能分类
            result = self._classifier.classify(parsed)
            logger.info("分类结果: %s（置信度: %.2f）原因: %s",
                        result.category, result.confidence, result.reason)

            # 5. 执行对应处理动作
            handler.handle(uid, parsed, result)

            # 6. 重要邮件触发通知
            if result.category == "important":
                self._notifier.notify_important(parsed, result.reason)

            # 7. 写入处理日志
            self._log(parsed, result.category, result.action_code,
                      result.confidence, result.reason)

        except Exception as e:
            logger.error("邮件 UID=%s 处理失败: %s", uid, e, exc_info=True)

    def _log(self, parsed, category: str, action_code: str, confidence: float, reason: str):
        self.db.insert_email_log(
            uid=parsed.uid,
            sender=parsed.sender,
            subject=parsed.subject,
            category=category,
            action_code=action_code,
            confidence=confidence,
            reason=reason,
        )

    def start(self):
        """启动定时调度，阻塞运行。首次启动立即执行一次，后续按间隔轮询。"""
        interval_seconds = self.settings.poll_interval_seconds
        self._scheduler.add_job(
            self._run_pipeline,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="email_pipeline",
            replace_existing=True,
        )
        logger.info("调度器启动，轮询间隔：%ss，立即执行首次检测", interval_seconds)
        self._run_pipeline()
        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("调度器已停止。")
