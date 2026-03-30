"""
web/deps.py — 依赖注入单例
为 FastAPI 路由提供共享的 Settings、Database、BlacklistManager 实例。
使用 lru_cache 保证进程内单例，避免每次请求重复初始化。
"""

from functools import lru_cache

from config.settings import Settings
from storage.db import Database
from modules.blacklist import BlacklistManager


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate()
    return s


@lru_cache
def get_db() -> Database:
    db = Database(get_settings().db_path)
    db.initialize()
    return db


def get_blacklist_manager() -> BlacklistManager:
    return BlacklistManager(get_db())
