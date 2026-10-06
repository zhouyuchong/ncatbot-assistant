from unittest import TestCase
from unittest.mock import Mock, patch
import types
import tests.bootstrap
from ncatbot_assistant.drive_bot.services import jm


class StructuredSearchTest(TestCase):
    def search(self, rows):
        client = Mock()
        client.search_site.return_value = rows
        option = Mock()
        option.default.return_value.new_jm_client.return_value = client
        with patch.dict('sys.modules', {'jmcomic': types.SimpleNamespace(JmOption=option)}):
            return jm.search_items(['关键词'], Mock())

    def test_search_items_preserves_ids_and_order(self):
        items = self.search([('456', '标题 B'), ('123', '标题 A')])
        self.assertEqual([(i.album_id, i.title) for i in items], [(456, '标题 B'), (123, '标题 A')])

    def test_search_limits_to_ten(self):
        items = self.search([(str(i), '标题') for i in range(1, 30)])
        self.assertEqual(len(items), 10)
        self.assertEqual(items[-1].album_id, 10)

    def test_empty_results(self):
        self.assertEqual(self.search([]), [])
