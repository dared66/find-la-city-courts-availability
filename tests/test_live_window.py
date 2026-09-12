import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import live_calendar as m


class Window(unittest.TestCase):
    def test_evening_bounds_and_all_day(self):
        start, end, queries = m.time_window(daypart='evening')
        self.assertEqual((start, end, list(queries)), ('17:00', '24:00', [1020, 1140, 1260, 1380]))
        self.assertEqual(len(m.time_window()[2]), 12)
        self.assertEqual(tuple(m.time_window('18:00')[2]), (1080,))

    def test_invalid_window(self):
        for args in [(None, '18:00', None), ('18:00', '17:00', None), ('18:00', None, 'evening')]:
            with self.assertRaises(ValueError): m.time_window(*args)

    def test_evening_reads_every_resource_page(self):
        page = MagicMock()
        page.goto.return_value.status = 200
        def snap(page_number):
            names = range(1, 21) if page_number == 1 else range(21, 23)
            return {'date': '09/14/2026', 'captured_at': 'fixture',
                    'summary': 'Showing results 1-20 of 22' if page_number == 1 else 'Showing results 21-22 of 22',
                    'courts': [{'name': str(n), 'location': 'Balboa Pay Tennis', 'date': '09/14/2026',
                                'detail_url': str(n), 'blocks': []} for n in names]}
        page.evaluate.side_effect = [snap(n) for _ in range(4) for n in (1, 2)]
        browser = MagicMock()
        browser.new_page.return_value = page
        manager = MagicMock()
        manager.__enter__.return_value.chromium.launch.return_value = browser
        fake = SimpleNamespace(sync_playwright=lambda: manager)
        with patch.dict(sys.modules, {'playwright.sync_api': fake}), patch.object(m, 'normalize', side_effect=lambda s,*a: s['courts']):
            result = m.retrieve('BalboaPayTennis', '2026-09-14', daypart='evening')
        self.assertEqual(result['pages_read'], 8)
        self.assertEqual(result['resource_count'], 22)
        self.assertEqual(page.goto.call_count, 4)
        self.assertEqual((result['start'], result['end']), ('17:00', '24:00'))
        browser.close.assert_called_once()

if __name__ == '__main__': unittest.main()
