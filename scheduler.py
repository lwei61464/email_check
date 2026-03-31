"""
scheduler.py — 定时任务调度模块
职责：使用 APScheduler 定时触发邮件检测与处理流程，驱动系统主循环。
      串联 MailFetcher / MailParser / BlacklistManager / EmailClassifier / MailHandler / Notifier。
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from modules.mail_fetcher import MailFetcher
from modules.mail_parser import MailParser
from modules.blacklist import BlacklistManager
from modules.classifier import EmailClassifier
from modules.mail_handler import MailHandler
from modules.notifier import Notifier
from modules.rule_engine import RuleEngine

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
        self._rule_engine = RuleEngine(db)
        # IMAP 连接非线程安全，并发处理时序列化所有 IMAP 操作
        self._imap_lock = threading.Lock()

    def _run_pipeline(self):
        """
        单次完整邮件处理流水线：
        IMAP 连接 → 获取新邮件 → 逐封处理 → 断开连接
        """
        pipeline_start = time.monotonic()
        email_count = 0
        error_count = 0
        fetcher = MailFetcher(self.settings, self.db)
        try:
            fetcher.connect()
            new_uids = fetcher.fetch_new_uids()
            if not new_uids:
                logger.info("本轮无新邮件")
                return

            email_count = len(new_uids)
            handler = MailHandler(self.settings, fetcher.client, self._blacklist)

            max_workers = getattr(self.settings, "max_concurrent_emails", 3)
            if max_workers > 1 and len(new_uids) > 1:
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    pool.map(partial(self._process_one, fetcher=fetcher, handler=handler), new_uids)
            else:
                for uid in new_uids:
                    self._process_one(uid, fetcher, handler)

            # 定期清理过期邮件
            handler.cleanup_quarantine()
            handler.cleanup_review()

        except Exception as e:
            logger.error("流水线执行异常: %s", e, exc_info=True)
            error_count += 1
        finally:
            fetcher.disconnect()
            pipeline_time = time.monotonic() - pipeline_start
            if email_count > 0:
                try:
                    self.db.insert_metrics(
                        pipeline_time=round(pipeline_time, 3),
                        llm_time=0.0,
                        llm_success=1 if error_count == 0 else 0,
                        email_count=email_count,
                        error_count=error_count,
                    )
                except Exception:
                    pass

    def _process_one(self, uid: int, fetcher: MailFetcher, handler: MailHandler):
        """
        处理单封邮件：解析 → 黑白名单检查 → LLM 分类 → 执行动作 → 写日志。
        单封邮件异常不影响后续邮件处理。
        """
        try:
            # 1. 获取原始邮件（IMAP，序列化锁保护）
            with self._imap_lock:
                raw_bytes = fetcher.fetch_raw_email(uid)
            parsed = self._parser.parse(str(uid), raw_bytes)
            logger.info("处理邮件 UID=%s | 发件人: %s | 主题: %s",
                        uid, parsed.sender, parsed.subject)

            # 2. 黑名单检查（最高优先级，命中直接删除，跳过 LLM）
            list_result = self._blacklist.check(parsed.sender)
            if list_result == "blacklist":
                with self._imap_lock:
                    handler.handle_spam(uid, parsed.sender, confidence=1.0)
                self._log(parsed, "spam", "DELETE_AND_BLOCK", 1.0, "黑名单命中，直接拦截")
                return

            # 3. 白名单检查（强制归为 normal，跳过 LLM）
            if list_result == "whitelist":
                with self._imap_lock:
                    handler.handle_normal(uid)
                self._log(parsed, "normal", "MARK_READ_ARCHIVE", 1.0, "白名单放行，复制到 Archive")
                return

            # 4a. 自定义规则匹配（优先级高于 LLM，无需锁）
            rule_cat = self._rule_engine.match(parsed)
            if rule_cat is not None:
                from modules.classifier import ClassificationResult, _CATEGORY_TO_ACTION
                action = _CATEGORY_TO_ACTION.get(rule_cat, "MARK_READ_ARCHIVE")
                result = ClassificationResult(
                    category=rule_cat,
                    action_code=action,
                    reason="自定义规则命中",
                    confidence=1.0,
                )
                with self._imap_lock:
                    handler.handle(uid, parsed, result)
                if self._notifier.should_notify(result.category):
                    self._notifier.notify_important(parsed, result.reason)
                self._log(parsed, result.category, result.action_code,
                          result.confidence, result.reason)
                return

            # 4b. LLM 智能分类（网络调用，无需锁，并发处理的核心阶段）
            result = self._classifier.classify(parsed, self.db)
            logger.info("分类结果: %s（置信度: %.2f）原因: %s",
                        result.category, result.confidence, result.reason)

            # 5. 执行对应处理动作（IMAP，序列化锁保护）
            with self._imap_lock:
                handler.handle(uid, parsed, result)

            # 6. 触发通知（按配置的分类列表）
            if self._notifier.should_notify(result.category):
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
        """启动调度。根据 IMAP_MODE 选择轮询或 IDLE 实时推送模式。"""
        imap_mode = getattr(self.settings, "imap_mode", "poll")
        if imap_mode == "idle":
            self._start_idle()
        else:
            self._start_poll()

    def _start_poll(self):
        """轮询模式：APScheduler 定时触发，阻塞运行。"""
        interval_seconds = self.settings.poll_interval_seconds
        self._scheduler.add_job(
            self._run_pipeline,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="email_pipeline",
            replace_existing=True,
        )
        logger.info("调度器启动（轮询模式），间隔：%ss，立即执行首次检测", interval_seconds)
        self._run_pipeline()
        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("调度器已停止。")

    def _start_idle(self):
        """
        IDLE 实时推送模式：独立线程运行 IDLE 循环，主线程保活。
        同时启动后台轮询（每 30 分钟）作为保底，防止 IDLE 消息丢失。
        """
        logger.info("调度器启动（IDLE 实时推送模式）")
        self._run_pipeline()  # 启动时立即扫描一次

        # 后台 IDLE 线程
        idle_thread = threading.Thread(target=self._idle_loop, daemon=True, name="imap-idle")
        idle_thread.start()

        # 保底轮询（每 30 分钟）
        self._scheduler.add_job(
            self._run_pipeline,
            trigger=IntervalTrigger(minutes=30),
            id="email_pipeline_backup",
            replace_existing=True,
        )
        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("调度器已停止。")

    def _idle_loop(self):
        """在独立线程中持续 IDLE，断线后自动重连。"""
        fetcher = MailFetcher(self.settings, self.db)
        while True:
            try:
                fetcher.connect()
                fetcher.watch_idle(on_new_mail=self._run_pipeline)
            except Exception as e:
                logger.error("IDLE 循环异常，5s 后重连: %s", e)
                fetcher.disconnect()
                import time
                time.sleep(5)
