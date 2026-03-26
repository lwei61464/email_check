"""
main.py — 程序入口
职责：初始化各模块，启动定时调度器，处理启动/退出信号。
"""

import logging
import os
import sys
from config.settings import Settings
from storage.db import Database
from scheduler import EmailScheduler

# 确保 logs/ 目录存在，避免 FileHandler 启动报错
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/app.log", encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)


def main():
    logger.info("邮件自动分拣系统启动...")

    # 初始化并校验配置（缺少必填项时立即报错退出）
    settings = Settings()
    settings.validate()

    # 初始化数据库（建表）
    db = Database(settings.db_path)
    db.initialize()

    # 启动调度器
    scheduler = EmailScheduler(settings, db)
    scheduler.start()


if __name__ == "__main__":
    main()
