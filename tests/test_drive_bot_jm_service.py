import sys
import types
from unittest import TestCase, main

import tests.bootstrap  # noqa: F401
from ncatbot_assistant.drive_bot.services.jm import jm_search


class FakeLogger:
    def debug(self, *_args, **_kwargs):
        pass


class FakeSearchPage:
    def __iter__(self):
        return iter(())


class FakeJmClient:
    def search_site(self, search_query, page):
        return FakeSearchPage()


class FakeJmOption:
    @classmethod
    def default(cls):
        return cls()

    def new_jm_client(self):
        return FakeJmClient()


class DriveBotJmServiceTest(TestCase):
    def setUp(self):
        self.original_jmcomic = sys.modules.get("jmcomic")
        fake_jmcomic = types.ModuleType("jmcomic")
        fake_jmcomic.JmOption = FakeJmOption
        fake_jmcomic.JmSearchPage = FakeSearchPage
        sys.modules["jmcomic"] = fake_jmcomic

    def tearDown(self):
        if self.original_jmcomic is None:
            sys.modules.pop("jmcomic", None)
            return
        sys.modules["jmcomic"] = self.original_jmcomic

    def test_jm_search_returns_message_when_no_results(self):
        result = jm_search(["无畏契约"], FakeLogger())

        self.assertEqual(result, "没有找到与「无畏契约」相关的 JM 结果。")


if __name__ == "__main__":
    main()
