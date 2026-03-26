"""
modules/mail_handler.py — 邮件处理模块

处理策略（非破坏性）：
  - 所有邮件操作均采用 COPY，不使用 MOVE，INBOX 原件始终保留
  - 绝不设置 \\Seen 标志，邮件在客户端中保持未读状态
  - 分类副本写入对应文件夹，用户可在各文件夹中查看已分拣结果
  - 重要邮件：在 INBOX 原件上加星标（\\Flagged），同时复制到 Important
  - 垃圾邮件：尝试在 INBOX 原件上标记 $Junk 关键字（服务器不支持则跳过），复制到隔离区
  - 清理操作仅删除隔离区/审核区的过期副本，不影响 INBOX
"""

import datetime
import logging

import imapclient

logger = logging.getLogger(__name__)

FOLDER_ARCHIVE       = "普通邮件"
FOLDER_IMPORTANT     = "重要邮件"
FOLDER_NEWSLETTER    = "订阅资讯"
FOLDER_TRANSACTIONAL = "事务通知"
FOLDER_QUARANTINE    = "垃圾隔离"
FOLDER_REVIEW        = "待审核"


class MailHandler:
    def __init__(self, settings, imap_client: imapclient.IMAPClient, blacklist_manager):
        self.settings = settings
        self.imap_client = imap_client
        self.blacklist_manager = blacklist_manager
        self._ensured_folders: set = set()   # 本次连接已确认存在的文件夹，避免重复查询

    # ── 分发入口 ──────────────────────────────────────────────────────────────

    def handle(self, uid: int, parsed_email, classification_result):
        """根据分类结果分发到对应处理策略。"""
        category = classification_result.category
        if category == "spam":
            self.handle_spam(uid, parsed_email.sender, classification_result.confidence)
        elif category == "important":
            self.handle_important(uid)
        elif category == "newsletter":
            self.handle_newsletter(uid)
        elif category == "transactional":
            self.handle_transactional(uid)
        else:
            self.handle_normal(uid)

    # ── 各分类处理策略 ────────────────────────────────────────────────────────

    def handle_spam(self, uid: int, sender: str, confidence: float):
        """
        垃圾邮件处理（非破坏性）：
        - 高置信（>= 阈值）→ 复制到 Quarantine + 写入黑名单 + 尝试标记 $Junk
        - 低置信（< 阈值） → 复制到 Review，不写黑名单
        INBOX 原件保留、保持未读，Quarantine/Review 副本到期后自动清理。
        """
        conf_threshold = self.settings.spam_confidence_threshold
        if confidence >= conf_threshold:
            self._ensure_folder(FOLDER_QUARANTINE)
            self._copy_message(uid, FOLDER_QUARANTINE)
            self._try_set_junk_flag(uid)
            bl_threshold = getattr(self.settings, "blacklist_threshold", 3)
            added = self.blacklist_manager.try_auto_blacklist(
                sender, bl_threshold, reason="LLM 高置信 Spam 累计达到阈值"
            )
            if added:
                logger.info("Spam（高置信 %.2f）→ 复制到垃圾隔离，发件人 %s 已加入黑名单",
                            confidence, sender)
            else:
                logger.info("Spam（高置信 %.2f）→ 复制到垃圾隔离，发件人 %s 未达加黑名单阈值",
                            confidence, sender)
        else:
            self._ensure_folder(FOLDER_REVIEW)
            self._copy_message(uid, FOLDER_REVIEW)
            logger.info("Spam（低置信 %.2f）→ 复制到待审核，INBOX 原件保留，发件人 %s 不加黑名单",
                        confidence, sender)

    def handle_normal(self, uid: int):
        """普通邮件：复制到 Archive。INBOX 原件保留、保持未读。"""
        self._handle_with_folder(uid, FOLDER_ARCHIVE, "Normal")

    def handle_important(self, uid: int):
        """重要邮件：INBOX 打星标 + 复制到 Important。保持未读。通知由 Notifier 处理。"""
        self.imap_client.add_flags([uid], [imapclient.FLAGGED])
        self._handle_with_folder(uid, FOLDER_IMPORTANT, "Important", inbox_starred=True)

    def handle_newsletter(self, uid: int):
        """订阅资讯：复制到 Newsletter。INBOX 原件保留、保持未读。"""
        self._handle_with_folder(uid, FOLDER_NEWSLETTER, "Newsletter")

    def handle_transactional(self, uid: int):
        """事务性通知：复制到 Transactional。INBOX 原件保留、保持未读。"""
        self._handle_with_folder(uid, FOLDER_TRANSACTIONAL, "Transactional")

    # ── 清理过期副本 ──────────────────────────────────────────────────────────

    def cleanup_review(self):
        """清理 Review 文件夹中超过保留期的副本（硬删除副本，不影响 INBOX）。"""
        self._cleanup_folder(FOLDER_REVIEW, self.settings.review_retention_days)

    def cleanup_quarantine(self):
        """清理 Quarantine 文件夹中超过保留期的副本（硬删除副本，不影响 INBOX）。"""
        self._cleanup_folder(FOLDER_QUARANTINE, self.settings.quarantine_retention_days)

    # ── 内部工具方法 ──────────────────────────────────────────────────────────

    def _handle_with_folder(self, uid: int, folder: str, label: str,
                             inbox_starred: bool = False):
        """
        公共处理模板：确保文件夹存在 → 复制邮件 → 记录日志。
        inbox_starred=True 时日志说明 INBOX 已打星标。
        """
        self._ensure_folder(folder)
        self._copy_message(uid, folder)
        if inbox_starred:
            logger.info("%s → INBOX 已标星，复制到 %s，UID: %s", label, folder, uid)
        else:
            logger.info("%s → 复制到 %s，INBOX 原件保留，UID: %s", label, folder, uid)

    def _copy_message(self, uid: int, target_folder: str):
        """将邮件复制到目标文件夹，INBOX 原件不受影响。"""
        self.imap_client.copy([uid], target_folder)
        logger.debug("已复制 UID %s 到 %s", uid, target_folder)

    def _try_set_junk_flag(self, uid: int):
        """
        尝试在 INBOX 原件上设置 $Junk 关键字，帮助邮件客户端识别垃圾邮件。
        若服务器不支持自定义关键字则静默跳过，不影响主流程。
        """
        try:
            self.imap_client.add_flags([uid], [b"$Junk"])
            logger.debug("已为 UID %s 设置 $Junk 关键字", uid)
        except Exception:
            logger.debug("服务器不支持 $Junk 关键字，UID: %s，跳过", uid)

    def _cleanup_folder(self, folder_name: str, retention_days: int):
        """通用文件夹过期副本清理：删除早于 retention_days 天的邮件副本。"""
        if not self.imap_client.folder_exists(folder_name):
            return

        cutoff = datetime.date.today() - datetime.timedelta(days=retention_days)
        self.imap_client.select_folder(folder_name, readonly=False)
        old_uids = self.imap_client.search(["BEFORE", cutoff])
        if not old_uids:
            return

        self.imap_client.delete_messages(old_uids)
        self.imap_client.expunge()
        logger.info("已清理 %s 过期副本 %d 封（截止日期: %s）",
                    folder_name, len(old_uids), cutoff)

    def _ensure_folder(self, folder_name: str):
        """确保目标文件夹存在，不存在则创建。同一连接内每个文件夹只检查一次。"""
        if folder_name in self._ensured_folders:
            return
        if not self.imap_client.folder_exists(folder_name):
            self.imap_client.create_folder(folder_name)
            logger.info("已创建 IMAP 文件夹: %s", folder_name)
        self._ensured_folders.add(folder_name)
