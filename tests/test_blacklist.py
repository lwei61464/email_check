"""
tests/test_blacklist.py — modules.blacklist.BlacklistManager 单元测试

覆盖：
  - check() 未命中 / 黑名单命中 / 白名单命中 / 域名匹配 / 优先级 / 大小写
  - add_to_blacklist() / add_to_whitelist() / remove() / list_all()
"""

import pytest
from modules.blacklist import LIST_TYPE_BLACKLIST, LIST_TYPE_WHITELIST


class TestCheck:

    def test_returns_none_for_unknown_sender(self, blacklist_manager):
        """未在任何名单中的发件人返回 None。"""
        assert blacklist_manager.check("nobody@unknown.com") is None

    def test_returns_blacklist_for_exact_blacklisted_sender(self, blacklist_manager):
        """精确地址加入黑名单后，check 返回 'blacklist'。"""
        blacklist_manager.add_to_blacklist("spammer@bad.com")
        assert blacklist_manager.check("spammer@bad.com") == "blacklist"

    def test_returns_whitelist_for_exact_whitelisted_sender(self, blacklist_manager):
        """精确地址加入白名单后，check 返回 'whitelist'。"""
        blacklist_manager.add_to_whitelist("boss@company.com")
        assert blacklist_manager.check("boss@company.com") == "whitelist"

    def test_domain_level_blacklist_matches_any_address_in_domain(self, blacklist_manager):
        """域名级别黑名单（@spam.com）命中该域下任意发件人。"""
        blacklist_manager.add_to_blacklist("@spam.com", "entire domain blocked")
        assert blacklist_manager.check("anyone@spam.com") == "blacklist"
        assert blacklist_manager.check("other@spam.com") == "blacklist"

    def test_domain_rule_does_not_match_different_domain(self, blacklist_manager):
        """域名规则不会匹配其他域名下的地址。"""
        blacklist_manager.add_to_blacklist("@evil.com")
        assert blacklist_manager.check("user@good.com") is None

    def test_whitelist_takes_priority_over_blacklist(self, blacklist_manager):
        """同一地址同时在黑白名单时，白名单优先，返回 'whitelist'。"""
        blacklist_manager.add_to_blacklist("dual@example.com")
        blacklist_manager.add_to_whitelist("dual@example.com")
        assert blacklist_manager.check("dual@example.com") == "whitelist"

    def test_check_is_case_insensitive(self, blacklist_manager):
        """发件人地址大小写不影响 check 的匹配结果。"""
        blacklist_manager.add_to_blacklist("lower@example.com")
        assert blacklist_manager.check("LOWER@EXAMPLE.COM") == "blacklist"


class TestAddToBlacklist:

    def test_persists_address(self, blacklist_manager):
        """add_to_blacklist 调用后 check 返回 'blacklist'。"""
        blacklist_manager.add_to_blacklist("new@spam.com", "test reason")
        assert blacklist_manager.check("new@spam.com") == "blacklist"

    def test_without_reason_does_not_raise(self, blacklist_manager):
        """省略 reason 参数时不抛出异常。"""
        blacklist_manager.add_to_blacklist("noreason@spam.com")
        assert blacklist_manager.check("noreason@spam.com") == "blacklist"

    def test_is_idempotent(self, blacklist_manager):
        """重复添加同一地址不抛出异常。"""
        blacklist_manager.add_to_blacklist("dup@spam.com", "r1")
        blacklist_manager.add_to_blacklist("dup@spam.com", "r2")
        assert blacklist_manager.check("dup@spam.com") == "blacklist"


class TestAddToWhitelist:

    def test_persists_address(self, blacklist_manager):
        """add_to_whitelist 调用后 check 返回 'whitelist'。"""
        blacklist_manager.add_to_whitelist("trusted@corp.com")
        assert blacklist_manager.check("trusted@corp.com") == "whitelist"

    def test_is_idempotent(self, blacklist_manager):
        """重复添加同一地址到白名单不抛出异常。"""
        blacklist_manager.add_to_whitelist("dup@corp.com")
        blacklist_manager.add_to_whitelist("dup@corp.com")
        assert blacklist_manager.check("dup@corp.com") == "whitelist"

    def test_with_reason_persisted(self, blacklist_manager, db):
        """add_to_whitelist 传入 reason 后可在 address_list 中查到。"""
        blacklist_manager.add_to_whitelist("vip@corp.com", reason="客户白名单")
        rows = db.list_addresses(LIST_TYPE_WHITELIST)
        assert any(r["address"] == "vip@corp.com" and r["reason"] == "客户白名单" for r in rows)

    def test_without_reason_does_not_raise(self, blacklist_manager):
        """省略 reason 参数时不抛出异常。"""
        blacklist_manager.add_to_whitelist("noreason@corp.com")
        assert blacklist_manager.check("noreason@corp.com") == "whitelist"

    def test_reason_updated_on_upsert(self, blacklist_manager, db):
        """重复添加时 reason 被更新为最新值。"""
        blacklist_manager.add_to_whitelist("update@corp.com", reason="初始原因")
        blacklist_manager.add_to_whitelist("update@corp.com", reason="更新原因")
        rows = db.list_addresses(LIST_TYPE_WHITELIST)
        match = next(r for r in rows if r["address"] == "update@corp.com")
        assert match["reason"] == "更新原因"


class TestRemove:

    def test_remove_blacklisted_address(self, blacklist_manager):
        """从黑名单移除后，check 返回 None（无域名规则时）。"""
        blacklist_manager.add_to_blacklist("removeme@spam.com")
        blacklist_manager.remove("removeme@spam.com", LIST_TYPE_BLACKLIST)
        assert blacklist_manager.check("removeme@spam.com") is None

    def test_remove_whitelisted_address(self, blacklist_manager):
        """从白名单移除后，check 返回 None。"""
        blacklist_manager.add_to_whitelist("removeme@corp.com")
        blacklist_manager.remove("removeme@corp.com", LIST_TYPE_WHITELIST)
        assert blacklist_manager.check("removeme@corp.com") is None

    def test_remove_nonexistent_does_not_raise(self, blacklist_manager):
        """移除不存在的地址不抛出异常。"""
        blacklist_manager.remove("ghost@nowhere.com", LIST_TYPE_BLACKLIST)

    def test_remove_blacklist_does_not_affect_whitelist(self, blacklist_manager):
        """移除黑名单条目不影响同一地址的白名单条目。"""
        blacklist_manager.add_to_blacklist("shared@example.com")
        blacklist_manager.add_to_whitelist("shared@example.com")
        blacklist_manager.remove("shared@example.com", LIST_TYPE_BLACKLIST)
        assert blacklist_manager.check("shared@example.com") == "whitelist"


class TestListAll:

    def test_returns_only_specified_list_type(self, blacklist_manager):
        """list_all('blacklist') 只返回黑名单条目，不含白名单。"""
        blacklist_manager.add_to_blacklist("bl1@spam.com")
        blacklist_manager.add_to_whitelist("wl1@corp.com")
        rows = blacklist_manager.list_all(LIST_TYPE_BLACKLIST)
        assert len(rows) == 1
        assert all(r["list_type"] == "blacklist" for r in rows)

    def test_returns_empty_list_when_no_entries(self, blacklist_manager):
        """名单为空时返回空列表。"""
        assert blacklist_manager.list_all(LIST_TYPE_BLACKLIST) == []

    def test_returns_multiple_entries(self, blacklist_manager):
        """list_all 可正确返回多条记录。"""
        blacklist_manager.add_to_blacklist("a@spam.com")
        blacklist_manager.add_to_blacklist("b@spam.com")
        rows = blacklist_manager.list_all(LIST_TYPE_BLACKLIST)
        addresses = [r["address"] for r in rows]
        assert len(rows) == 2
        assert "a@spam.com" in addresses
        assert "b@spam.com" in addresses


# ── try_auto_blacklist ────────────────────────────────────────────────────────

class TestTryAutoBlacklist:
    """
    验证阈值策略：历史次数 >= threshold-1 时才加入黑名单。
    测试使用真实 db（conftest fixture），通过 insert_email_log 写入历史记录。
    """

    def test_returns_false_when_below_threshold(self, blacklist_manager, db):
        """历史 spam 次数不足时返回 False，不加入黑名单。"""
        # threshold=3，需要历史>=2次，此处只有 1 次
        db.insert_email_log("uid-s1", "new@evil.com", "S", "spam", "DELETE_AND_BLOCK", 0.95, "")
        result = blacklist_manager.try_auto_blacklist("new@evil.com", threshold=3)
        assert result is False
        assert blacklist_manager.check("new@evil.com") is None

    def test_returns_true_when_threshold_reached(self, blacklist_manager, db):
        """历史 spam 次数达到 threshold-1 时返回 True，加入黑名单。"""
        db.insert_email_log("uid-s1", "repeat@evil.com", "S1", "spam", "DELETE_AND_BLOCK", 0.95, "")
        db.insert_email_log("uid-s2", "repeat@evil.com", "S2", "spam", "DELETE_AND_BLOCK", 0.96, "")
        result = blacklist_manager.try_auto_blacklist("repeat@evil.com", threshold=3)
        assert result is True
        assert blacklist_manager.check("repeat@evil.com") == "blacklist"

    def test_returns_true_when_above_threshold(self, blacklist_manager, db):
        """历史次数超过阈值时也返回 True。"""
        for i in range(5):
            db.insert_email_log(f"uid-s{i}", "veteran@evil.com", "S", "spam",
                                "DELETE_AND_BLOCK", 0.95, "")
        result = blacklist_manager.try_auto_blacklist("veteran@evil.com", threshold=3)
        assert result is True

    def test_zero_history_below_threshold(self, blacklist_manager):
        """无历史记录时（首次检测），不加入黑名单。"""
        result = blacklist_manager.try_auto_blacklist("first@evil.com", threshold=3)
        assert result is False

    def test_threshold_of_one_adds_immediately(self, blacklist_manager):
        """阈值设为 1 时，首次检测即加入黑名单（兼容旧行为）。"""
        result = blacklist_manager.try_auto_blacklist("instant@evil.com", threshold=1)
        assert result is True
        assert blacklist_manager.check("instant@evil.com") == "blacklist"
