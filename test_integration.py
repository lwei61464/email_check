"""
test_integration.py — 受控集成测试脚本
仅对 INBOX 未读邮件中时间最新的 N 封执行完整处理流程，其余邮件不操作。
"""

import logging
import sys
import os

# 确保从项目根目录导入模块
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Windows 终端强制 UTF-8 输出，避免日文/特殊字符编码错误
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from config.settings import Settings
from storage.db import Database
from modules.mail_fetcher import MailFetcher
from modules.mail_parser import MailParser
from modules.blacklist import BlacklistManager
from modules.classifier import EmailClassifier
from modules.mail_handler import MailHandler
from modules.notifier import Notifier

# ── 常量 ──────────────────────────────────────────────────────────────────────

MAX_TEST_EMAILS = 10     # 每次只处理最新的 N 封未读邮件

# 分类标签映射（用于报告展示）
CATEGORY_LABEL = {
    "spam":          "垃圾/骚扰",
    "transactional": "事务通知",
    "newsletter":    "订阅资讯",
    "normal":        "普通邮件",
    "important":     "重要邮件",
}
ACTION_LABEL = {
    "DELETE_AND_BLOCK":   "复制到隔离区",
    "MARK_READ_ARCHIVE":  "复制到归档",
    "STAR_AND_NOTIFY":    "打星标+复制到重要",
}

# ── 初始化 ────────────────────────────────────────────────────────────────────

def init_modules():
    settings = Settings()
    settings.validate()

    db = Database(settings.db_path)
    db.initialize()

    blacklist  = BlacklistManager(db)
    parser     = MailParser()
    classifier = EmailClassifier(settings)
    notifier   = Notifier(settings)

    return settings, db, blacklist, parser, classifier, notifier


# ── 获取最新 N 封未读邮件的 UID ───────────────────────────────────────────────

def fetch_latest_unseen_uids(fetcher, limit: int) -> list:
    """
    获取 INBOX 全部未读邮件中尚未处理的 UID，
    按时间从新到旧排序后取前 limit 封。
    已在数据库中记录的 UID 自动跳过（幂等）。
    """
    fetcher._client.select_folder("INBOX", readonly=False)
    all_unseen = fetcher._client.search(["UNSEEN"])
    if not all_unseen:
        return []

    # 过滤已处理（幂等保障）
    unprocessed = [uid for uid in all_unseen
                   if not fetcher.db.is_uid_processed(str(uid))]

    print(f"\n未读邮件共 {len(all_unseen)} 封，其中 {len(all_unseen)-len(unprocessed)} 封已处理，"
          f"剩余待处理 {len(unprocessed)} 封，本次最多处理最新 {limit} 封...\n")

    if not unprocessed:
        return []

    # 批量获取内部时间戳，按时间从新到旧排序
    date_data = fetcher._client.fetch(unprocessed, ["INTERNALDATE"])
    uid_dates = [
        (uid, date_data[uid][b"INTERNALDATE"])
        for uid in unprocessed
        if uid in date_data and b"INTERNALDATE" in date_data[uid]
    ]
    uid_dates.sort(key=lambda x: x[1], reverse=True)   # 最新的在前
    return [uid for uid, _ in uid_dates[:limit]]


# ── 处理单封邮件 ──────────────────────────────────────────────────────────────

def process_one(uid, fetcher, parser, blacklist, classifier, handler, notifier, db):
    """
    完整流水线：解析 → 黑白名单 → LLM 分类 → 执行动作 → 写日志。
    返回结果字典，异常时记录错误信息。
    """
    record = {
        "uid":        uid,
        "sender":     "",
        "subject":    "",
        "date":       "",
        "list_hit":   None,
        "category":   "",
        "confidence": 0.0,
        "reason":     "",
        "action":     "",
        "error":      None,
    }
    try:
        # 1. 获取原始邮件并解析
        raw = fetcher.fetch_raw_email(uid)
        parsed = parser.parse(str(uid), raw)

        record["sender"]  = parsed.sender
        record["subject"] = parsed.subject
        record["date"]    = parsed.raw_date

        # 2. 黑名单检查
        list_result = blacklist.check(parsed.sender)
        record["list_hit"] = list_result

        if list_result == "blacklist":
            handler.handle_spam(uid, parsed.sender, confidence=1.0)
            db.insert_email_log(parsed.uid, parsed.sender, parsed.subject,
                                "spam", "DELETE_AND_BLOCK", 1.0, "黑名单命中")
            record.update(category="spam", confidence=1.0,
                          reason="黑名单命中，直接拦截", action="DELETE_AND_BLOCK")
            return record

        if list_result == "whitelist":
            handler.handle_normal(uid)
            db.insert_email_log(parsed.uid, parsed.sender, parsed.subject,
                                "normal", "MARK_READ_ARCHIVE", 1.0, "白名单放行")
            record.update(category="normal", confidence=1.0,
                          reason="白名单放行", action="MARK_READ_ARCHIVE")
            return record

        # 3. LLM 智能分类
        result = classifier.classify(parsed)
        record.update(
            category=result.category,
            confidence=result.confidence,
            reason=result.reason,
            action=result.action_code,
        )

        # 4. 执行动作
        handler.handle(uid, parsed, result)

        # 5. 重要邮件通知
        if result.category == "important":
            notifier.notify_important(parsed, result.reason)

        # 6. 写入日志
        db.insert_email_log(parsed.uid, parsed.sender, parsed.subject,
                            result.category, result.action_code,
                            result.confidence, result.reason)

    except Exception as e:
        record["error"] = str(e)

    return record


# ── 打印测试报告 ──────────────────────────────────────────────────────────────

def print_report(results: list):
    total         = len(results)
    errors        = [r for r in results if r["error"]]
    spam          = [r for r in results if r["category"] == "spam"]
    transactional = [r for r in results if r["category"] == "transactional"]
    newsletter    = [r for r in results if r["category"] == "newsletter"]
    normal        = [r for r in results if r["category"] == "normal"]
    important     = [r for r in results if r["category"] == "important"]

    SEP  = "=" * 72
    SEP2 = "-" * 72

    print(f"\n{SEP}")
    print("  集成测试报告")
    print(SEP)
    print(f"  处理总数: {total} 封  |  垃圾: {len(spam)}  事务: {len(transactional)}"
          f"  资讯: {len(newsletter)}  普通: {len(normal)}  重要: {len(important)}  异常: {len(errors)}")
    print(SEP)

    for i, r in enumerate(results, 1):
        status = "[ERROR]" if r["error"] else f"[{CATEGORY_LABEL.get(r['category'], r['category'])}]"
        conf   = f"{r['confidence']:.0%}" if r["confidence"] else "  -  "
        hit    = f" ★{r['list_hit'].upper()}" if r["list_hit"] else ""

        print(f"\n  #{i:02d} {status}{hit}  置信度: {conf}")
        print(f"       发件人 : {r['sender']}")
        print(f"       主题   : {r['subject'][:60]}")
        print(f"       操作   : {ACTION_LABEL.get(r['action'], r['action'])}")
        if r["reason"]:
            print(f"       原因   : {r['reason'][:80]}")
        if r["error"]:
            print(f"       错误   : {r['error']}")

    print(f"\n{SEP2}")

    # 分类统计
    print(f"\n  分类统计")
    print(f"  {'垃圾/骚扰':<10} {len(spam):>3} 封  ({len(spam)/total*100:.0f}%)")
    print(f"  {'事务通知':<10} {len(transactional):>3} 封  ({len(transactional)/total*100:.0f}%)")
    print(f"  {'订阅资讯':<10} {len(newsletter):>3} 封  ({len(newsletter)/total*100:.0f}%)")
    print(f"  {'普通邮件':<10} {len(normal):>3} 封  ({len(normal)/total*100:.0f}%)")
    print(f"  {'重要邮件':<10} {len(important):>3} 封  ({len(important)/total*100:.0f}%)")
    if errors:
        print(f"  {'处理异常':<10} {len(errors):>3} 封")

    # 准确性评估
    print(f"\n  准确性评估")
    high_conf = [r for r in results if not r["error"] and r["confidence"] >= 0.85]
    low_conf  = [r for r in results if not r["error"] and 0 < r["confidence"] < 0.85]
    fallback  = [r for r in results if not r["error"] and r["confidence"] == 0.0]
    print(f"  高置信度(≥85%) : {len(high_conf)} 封 — 分类可信度高")
    print(f"  中低置信度(<85%): {len(low_conf)} 封 — 建议人工复核")
    if fallback:
        print(f"  LLM降级(置信=0) : {len(fallback)} 封 — API异常，已默认归为普通邮件")
    if errors:
        print(f"  处理失败        : {len(errors)} 封 — 见上方错误详情")

    print(f"\n{SEP}\n")


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print(f"  邮件分拣系统 — 集成测试（最新未读 {MAX_TEST_EMAILS} 封）")
    print("=" * 72)

    settings, db, blacklist, parser, classifier, notifier = init_modules()

    fetcher = MailFetcher(settings, db)
    fetcher.connect()
    print("[OK] IMAP 连接成功")

    try:
        target_uids = fetch_latest_unseen_uids(fetcher, MAX_TEST_EMAILS)
        if not target_uids:
            print("INBOX 中无未读邮件，测试结束。")
            return

        print(f"开始处理 {len(target_uids)} 封邮件...\n")

        handler = MailHandler(settings, fetcher.client, blacklist)
        results = []

        for i, uid in enumerate(target_uids, 1):
            print(f"  处理中 {i}/{len(target_uids)}  UID={uid} ...", end=" ", flush=True)
            record = process_one(uid, fetcher, parser, blacklist,
                                 classifier, handler, notifier, db)
            label = CATEGORY_LABEL.get(record["category"], record["category"])
            status = f"[{label}]" if not record["error"] else "[ERROR]"
            print(status)
            results.append(record)

        # 清理隔离区过期邮件（测试中通常无过期，幂等操作）
        handler.cleanup_quarantine()
        handler.cleanup_review()

    finally:
        fetcher.disconnect()
        print("\n[OK] IMAP 连接已断开")

    print_report(results)


if __name__ == "__main__":
    main()
