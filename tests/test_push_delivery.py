"""Business regression tests with mocked AstrBot services.

Load the real plugin methods without importing or registering AstrBot. These
tests verify routing, delivery state, retries and persistence, not SDK loading
or actual QQ delivery. Run with: python -m unittest discover -s tests -v
"""

import ast
import asyncio
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class MessageChainStub:
    def message(self, text):
        self.text = text
        return self


class FrozenDatetime(datetime):
    @classmethod
    def now(cls):
        return datetime(2026, 10, 2, 11, 31)


SOURCE = Path(os.environ.get("DAILY_AI_NEWS_TEST_SOURCE", Path(__file__).resolve().parents[1] / "main.py"))
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
plugin_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DailyAINewsPlugin")
methods = [node for node in plugin_class.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name != "__init__"]
for method in methods:
    method.decorator_list = []
test_class = ast.ClassDef(name="PushMethods", bases=[], keywords=[], body=methods, decorator_list=[])
module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), test_class], type_ignores=[])
GLOBALS = {
    "asyncio": asyncio,
    "datetime": FrozenDatetime,
    "timedelta": timedelta,
    "json": json,
    "os": os,
    "re": re,
    "tempfile": tempfile,
    "MessageChain": MessageChainStub,
    "logger": MagicMock(),
}
exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), GLOBALS)
PushMethods = GLOBALS["PushMethods"]


def platform(platform_id, platform_type="aiocqhttp"):
    metadata = SimpleNamespace(id=platform_id, name=platform_type)
    return SimpleNamespace(meta=lambda: metadata)


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.plugin = PushMethods()
        self.plugin.config = {"subscribed_users": "12345", "rss_poll_interval": 10}
        self.plugin._cmd_subscriptions = set()
        self.plugin._sent_dates = set()
        self.plugin._sent_links = set()
        self.plugin._sent_targets = {}
        self.plugin._unresolved_targets = set()
        self.plugin._file_lock = asyncio.Lock()
        self.plugin._push_lock = asyncio.Lock()
        self.plugin._sent_file = Path(self.temp.name) / "sent_news.json"
        self.plugin.context = SimpleNamespace(
            platform_manager=SimpleNamespace(platform_insts=[platform("qq-one")]),
            send_message=AsyncMock(return_value=True),
        )
        self.article = {
            "title": "2026-10-02",
            "link": "https://example.test/issues/2026-10-02/",
            "content": "test news",
        }
        self.plugin._fetch_rss_latest = AsyncMock(return_value=self.article)
        self.plugin._get_or_create_summary = AsyncMock(return_value="summary")
        GLOBALS["logger"].reset_mock()

    def test_bare_private_id_uses_actual_qq_instance(self):
        self.assertEqual(self.plugin._get_all_targets(), {"qq-one:FriendMessage:12345"})

    def test_bare_group_id_uses_actual_qq_instance(self):
        self.plugin.config = {"subscribed_groups": "54321"}
        self.assertEqual(self.plugin._get_all_targets(), {"qq-one:GroupMessage:54321"})

    def test_explicit_instance_and_full_session_are_preserved(self):
        self.plugin.config["subscribed_users"] = "qq-two:67890\nqq-two:FriendMessage:thread:67890"
        self.assertEqual(self.plugin._get_all_targets(), {
            "qq-two:FriendMessage:67890", "qq-two:FriendMessage:thread:67890",
        })

    def test_command_and_config_subscription_are_deduplicated(self):
        self.plugin._cmd_subscriptions.add("qq-one:FriendMessage:12345")
        self.assertEqual(len(self.plugin._get_all_targets()), 1)

    def test_multiple_qq_instances_require_selection(self):
        self.plugin.context.platform_manager.platform_insts.append(platform("qq-two"))
        self.assertEqual(self.plugin._get_all_targets(), set())
        self.assertTrue(self.plugin._unresolved_targets)
        self.plugin.config["push_platform_id"] = "qq-two"
        self.assertEqual(self.plugin._get_all_targets(), {"qq-two:FriendMessage:12345"})

    def test_bare_qq_id_does_not_choose_other_platform(self):
        self.plugin.context.platform_manager.platform_insts = [platform("tg-one", "telegram")]
        self.assertEqual(self.plugin._get_all_targets(), set())

    async def test_false_return_does_not_mark_success(self):
        self.plugin.context.send_message.return_value = False
        result = await self.plugin._do_push(self.article, "2026-10-02")
        self.assertFalse(result)
        self.assertNotIn("2026-10-02", self.plugin._sent_dates)
        self.assertNotIn(self.article["link"], self.plugin._sent_links)
        self.assertFalse(self.plugin._sent_targets)
        info_messages = [call.args[0] for call in GLOBALS["logger"].info.call_args_list]
        self.assertFalse(any("推送完成" in message for message in info_messages))

    async def test_failure_propagates_to_polling_caller(self):
        self.plugin.context.send_message.return_value = False
        self.assertFalse(await self.plugin._try_fetch_and_push("2026-10-02"))

    async def test_send_exception_does_not_mark_success(self):
        self.plugin.context.send_message.side_effect = RuntimeError("disconnected")
        self.assertFalse(await self.plugin._try_fetch_and_push("2026-10-02"))
        self.assertFalse(self.plugin._sent_dates)

    async def test_missing_targets_does_not_stop_retrying(self):
        self.plugin.config["subscribed_users"] = ""
        self.assertFalse(await self.plugin._try_fetch_and_push("2026-10-02"))
        self.plugin.context.send_message.assert_not_awaited()

    async def test_success_is_recorded_and_deduplicated(self):
        self.assertTrue(await self.plugin._try_fetch_and_push("2026-10-02"))
        self.assertTrue(await self.plugin._try_fetch_and_push("2026-10-02"))
        self.plugin.context.send_message.assert_awaited_once()
        self.assertIn("2026-10-02", self.plugin._sent_dates)
        saved = json.loads(self.plugin._sent_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["sent_targets"][self.article["link"]], ["qq-one:FriendMessage:12345"])

    async def test_partial_failure_retries_only_failed_recipient_after_reload(self):
        self.plugin.config["subscribed_users"] = "qq-one:12345\nqq-one:67890"
        self.plugin.context.send_message.side_effect = [True, False]
        self.assertFalse(await self.plugin._try_fetch_and_push("2026-10-02"))
        self.assertNotIn("2026-10-02", self.plugin._sent_dates)
        self.plugin._sent_targets = {}
        await self.plugin._load_sent_news()
        self.plugin.context.send_message.reset_mock()
        self.plugin.context.send_message.side_effect = None
        self.plugin.context.send_message.return_value = True
        self.assertTrue(await self.plugin._try_fetch_and_push("2026-10-02"))
        self.assertEqual(self.plugin.context.send_message.await_args.args[0], "qq-one:FriendMessage:67890")
        self.plugin.context.send_message.assert_awaited_once()

    async def test_unresolved_entry_prevents_false_completion(self):
        self.plugin.config["subscribed_users"] = "12345\nqq-one:67890"
        self.plugin.context.platform_manager.platform_insts.append(platform("qq-two"))
        self.assertFalse(await self.plugin._try_fetch_and_push("2026-10-02"))
        self.assertNotIn("2026-10-02", self.plugin._sent_dates)

    async def test_force_retry_recovers_old_false_success_and_preserves_other_dates(self):
        old_link = "https://example.test/issues/2026-10-01/"
        self.plugin._sent_dates = {"2026-10-01", "2026-10-02"}
        self.plugin._sent_links = {old_link, self.article["link"]}
        self.plugin._sent_targets = {old_link: {"qq-one:FriendMessage:12345"}}
        self.assertTrue(await self.plugin._try_fetch_and_push("2026-10-02", force=True))
        self.plugin.context.send_message.assert_awaited_once()
        self.assertIn(old_link, self.plugin._sent_targets)
        self.assertIn("2026-10-01", self.plugin._sent_dates)

    async def test_failed_force_retry_clears_only_current_false_success(self):
        self.plugin._sent_dates = {"2026-10-01", "2026-10-02"}
        self.plugin._sent_links = {self.article["link"]}
        self.plugin.context.send_message.return_value = False
        self.assertFalse(await self.plugin._try_fetch_and_push("2026-10-02", force=True))
        self.assertEqual(self.plugin._sent_dates, {"2026-10-01"})
        self.assertNotIn(self.article["link"], self.plugin._sent_links)

    async def test_force_retry_does_not_send_yesterday_as_today(self):
        self.article["title"] = "2026-10-01"
        self.assertFalse(await self.plugin._try_fetch_and_push("2026-10-02", force=True))
        self.plugin.context.send_message.assert_not_awaited()

    async def test_concurrent_checks_submit_only_once(self):
        results = await asyncio.gather(
            self.plugin._try_fetch_and_push("2026-10-02"),
            self.plugin._try_fetch_and_push("2026-10-02"),
        )
        self.assertEqual(results, [True, True])
        self.plugin.context.send_message.assert_awaited_once()

    async def test_startup_compensation_keeps_polling_after_failure(self):
        self.plugin.config.update({"push_hour": 8, "push_minute": 0})
        self.plugin._try_fetch_and_push = AsyncMock(side_effect=[False, True])
        sleep = AsyncMock()
        with patch.dict(GLOBALS, {"asyncio": SimpleNamespace(sleep=sleep)}):
            await self.plugin._startup_compensation_check()
        self.assertEqual(self.plugin._try_fetch_and_push.await_count, 2)
        sleep.assert_awaited_once_with(10)

    async def test_legacy_state_remains_readable(self):
        self.plugin._sent_file.write_text(json.dumps({
            "sent_dates": ["2026-10-01"], "sent_links": ["old-link"],
        }), encoding="utf-8")
        await self.plugin._load_sent_news()
        self.assertEqual(self.plugin._sent_dates, {"2026-10-01"})
        self.assertEqual(self.plugin._sent_links, {"old-link"})
        self.assertEqual(self.plugin._sent_targets, {})

    async def test_retry_command_calls_force_delivery(self):
        self.plugin._try_fetch_and_push = AsyncMock(return_value=True)
        event = SimpleNamespace(plain_result=lambda text: text)
        messages = [text async for text in self.plugin.cmd_retry(event)]
        self.assertIn("所有订阅目标", messages[-1])
        self.plugin._try_fetch_and_push.assert_awaited_once_with("2026-10-02", force=True)


if __name__ == "__main__":
    unittest.main()
