"""
modules/mail_fetcher.py — 邮件检测模块
职责：通过 IMAP SSL 协议连接邮箱，检测并获取未处理的新邮件 UID 列表，
      提供邮件原始数据获取接口，保证同一封邮件不被重复处理（幂等）。
"""

import logging
from typing import List

import imapclient

logger = logging.getLogger(__name__)


class MailFetcher:
    def __init__(self, settings, db):
        self.settings = settings
        self.db = db
        self._client: imapclient.IMAPClient | None = None

    @property
    def client(self) -> imapclient.IMAPClient:
        """暴露底层 IMAP 客户端，供 MailHandler 执行邮件操作。"""
        return self._client

    def connect(self):
        """建立 IMAP SSL 连接并登录。"""
        timeout = getattr(self.settings, "imap_timeout", 30)
        logger.info("连接 IMAP 服务器: %s:%s（超时 %ss）",
                    self.settings.imap_host, self.settings.imap_port, timeout)
        self._client = imapclient.IMAPClient(
            host=self.settings.imap_host,
            port=self.settings.imap_port,
            use_uid=True,
            ssl=True,
            timeout=timeout,
        )
        self._client.login(self.settings.imap_username, self.settings.imap_password)
        logger.info("IMAP 登录成功: %s", self.settings.imap_username)

    def disconnect(self):
        """安全断开 IMAP 连接。"""
        if self._client:
            try:
                self._client.logout()
                logger.info("IMAP 连接已断开")
            except Exception as e:
                logger.warning("断开 IMAP 时出现异常（已忽略）: %s", e)
            finally:
                self._client = None

    def fetch_new_uids(self, folder: str = "INBOX") -> List[int]:
        """
        获取未处理的新邮件 UID 列表（UNSEEN 且未在处理日志中）。

        :param folder: 邮箱文件夹，默认 INBOX
        :return: 待处理邮件 UID 列表
        """
        self._client.select_folder(folder, readonly=False)
        all_uids = self._client.search(["UNSEEN"])
        if not all_uids:
            return []
        # 过滤已处理（幂等）
        new_uids = [uid for uid in all_uids if not self.db.is_uid_processed(str(uid))]
        logger.info("发现新邮件 %d 封（未读共 %d 封）", len(new_uids), len(all_uids))
        return new_uids

    def fetch_raw_email(self, uid: int) -> bytes:
        """
        根据 UID 获取邮件原始字节内容（RFC822）。

        :param uid: 邮件 UID
        :return: 邮件原始字节数据
        """
        response = self._client.fetch([uid], ["RFC822"])
        if uid not in response:
            raise ValueError(f"邮件 UID {uid} 未找到")
        return response[uid][b"RFC822"]

    def ensure_folder_exists(self, folder_name: str):
        """确保 IMAP 文件夹存在，不存在则创建。"""
        if not self._client.folder_exists(folder_name):
            self._client.create_folder(folder_name)
            logger.info("已创建 IMAP 文件夹: %s", folder_name)
