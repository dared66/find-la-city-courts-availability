import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('courts', ROOT / 'scripts/find_availability.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(name):
    return json.loads((ROOT / 'tests/fixtures' / (name + '.json')).read_text())


def find(rows, name):
    return next(r for r in rows if r['name'] == name)


class LiveObservationRegression(unittest.TestCase):
    def test_live_midnight_extractor_output(self):
        rows = m.normalize(fixture('valley_any'), '2026-09-14')
        self.assertEqual(rows[0]['blocks'][0]['start'], '08:00')
        self.assertEqual(rows[0]['open_windows'], [{'start':'10:00','end':'12:00'}])
        self.assertEqual(rows[0]['maximum_minutes'], 120)

    def test_valley_weekday_morning(self):
        rows = m.normalize(fixture('valley'), '2026-09-14', '10:00', '12:00')
        self.assertEqual(find(rows, 'Court 1')['status'], 'available')
        self.assertTrue(find(rows, 'Court 1')['requested_duration_valid'])
        self.assertEqual(find(rows, 'Court 2')['status'], 'unavailable')

    def test_valley_busy_first_hour(self):
        rows = m.normalize(fixture('valley'), '2026-09-14', '09:00', '10:00')
        self.assertEqual(find(rows, 'Court 1')['status'], 'unavailable')

    def test_valley_pickleball_evening(self):
        rows = m.normalize(fixture('valley'), '2026-09-14', '17:00', '18:00', 'pickleball')
        self.assertEqual([r['name'] for r in rows], ['Court 4 - Pickleball A'])
        self.assertEqual(rows[0]['status'], 'available')
        self.assertIn('net is not provided', rows[0]['restrictions'])

    def test_paddle_not_misclassified_as_tennis(self):
        rows = m.normalize(fixture('valley'), '2026-09-14', sport='tennis')
        self.assertNotIn('Court 10 - Paddle Tennis', [r['name'] for r in rows])
        paddle = m.normalize(fixture('valley'), '2026-09-14', '17:00', '19:00', 'paddle tennis')
        self.assertEqual(paddle[0]['status'], 'available')

    def test_westchester_weekday_evening(self):
        rows = m.normalize(fixture('westchester'), '2026-09-15', '17:00', '18:00')
        self.assertEqual(find(rows, 'Court 3')['status'], 'available')
        self.assertEqual(find(rows, 'Court 1')['status'], 'unavailable')

    def test_westchester_longer_window_crosses_unavailable(self):
        rows = m.normalize(fixture('westchester'), '2026-09-15', '17:00', '19:00')
        self.assertEqual(find(rows, 'Court 3')['status'], 'unavailable')

    def test_hybrid_preserves_identity_and_both_sports(self):
        rows = m.normalize(fixture('westchester'), '2026-09-15', sport='pickleball')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['sports'], ['tennis', 'pickleball'])
        self.assertIn('FMID=518407', rows[0]['detail_url'])

    def test_pro_court_without_blocks_unknown(self):
        rows = m.normalize(fixture('westchester'), '2026-09-15')
        self.assertEqual(find(rows, 'Westchester Pro Court 2')['status'], 'unknown')

    def test_griffith_weekend_morning(self):
        rows = m.normalize(fixture('griffith'), '2026-09-13', '08:00', '10:00')
        self.assertTrue(all(r['status'] == 'unavailable' for r in rows))

    def test_griffith_weekend_afternoon(self):
        rows = m.normalize(fixture('griffith'), '2026-09-13', '12:00', '14:00')
        self.assertEqual(find(rows, 'Court 10')['status'], 'available')
        self.assertEqual(find(rows, 'Court 1')['status'], 'unavailable')

    def test_long_free_range_does_not_override_maximum(self):
        rows = m.normalize(fixture('griffith'), '2026-09-13', '12:00', '17:00')
        court = find(rows, 'Court 10')
        self.assertEqual(court['status'], 'available')
        self.assertFalse(court['requested_duration_valid'])
        self.assertEqual(court['maximum_minutes'], 120)

    def test_any_merges_adjacent_slots(self):
        rows = m.normalize(fixture('griffith'), '2026-09-13')
        self.assertEqual(find(rows, 'Court 10')['open_windows'], [{'start':'12:00','end':'17:00'}])


class SafetyAndEdgeCases(unittest.TestCase):
    def test_live_advance_rule_tooltip_preserved(self):
        data = fixture('griffith')
        data['source_url'] = data['source_url'].replace('09%2F13%2F2026','10%2F20%2F2026')
        data['date'] = '10/20/2026'
        data['courts'] = [data['courts'][0]]
        data['courts'][0]['date'] = '10/20/2026'
        data['courts'][0]['blocks'] = [dict(time='8:00 am - 9:00 am', classes='button full-block error cart-button cart-button--state-block', tooltip='<h2>Unavailable</h2><div class="rule-tooltip"><strong>Online Reservations</strong><br /><ul><li><span>Not (Maximum 8 days before the Reservation(s) begin date. Cutoff time on last day is after  8:00 am.)</span></li><li><span>Interface Type of WebTrac,Mobile WebTrac.</span></li></ul></div>')]
        row = m.normalize(data, '2026-10-20', '08:00','09:00')[0]
        self.assertEqual(row['status'], 'unavailable')
        self.assertTrue(row['blocks'][0]['booking_restriction'])
        self.assertIn('Maximum 8 days',row['blocks'][0]['provider_text'])

    def test_partial_hour_not_promised_as_selectable(self):
        row = m.normalize(fixture('valley'), '2026-09-14', '10:30', '11:30')[0]
        self.assertEqual(row['status'],'available')
        self.assertFalse(row['requested_matches_published_boundaries'])

    def test_malformed_time_is_unknown(self):
        data = fixture('valley')
        data['courts'][0]['blocks'] = [dict(time='changed format',classes='success',tooltip='Book Now')]
        self.assertEqual(m.normalize(data,'2026-09-14')[0]['status'],'unknown')

    def test_wrong_date_url(self):
        with self.assertRaises(m.ProviderError):
            m.normalize(fixture('valley'), '2026-09-15')

    def test_wrong_row_date(self):
        data = fixture('valley')
        data['courts'][0]['date'] = '09/15/2026'
        with self.assertRaises(m.ProviderError):
            m.normalize(data, '2026-09-14')

    def test_wrong_displayed_date(self):
        data = fixture('valley')
        data['date'] = '09/15/2026'
        with self.assertRaises(m.ProviderError):
            m.normalize(data, '2026-09-14')

    def test_empty_calendar_is_error_not_unavailable(self):
        data = fixture('valley')
        data['courts'] = []
        with self.assertRaises(m.ProviderError):
            m.normalize(data, '2026-09-14')

    def test_redirect_html_and_forbidden_fail_closed(self):
        for html in ('<h1>Discover Facilities</h1>', '<h1>403 Forbidden</h1>', ''):
            with self.subTest(html=html), self.assertRaises(m.ProviderError):
                m.parse_html(html, m.DISCOVERY)

    def test_plain_time_link_is_not_availability(self):
        data = fixture('valley')
        data['courts'] = [data['courts'][0]]
        data['courts'][0]['blocks'] = [dict(time='10:00 am - 11:00 am', classes='button', tooltip='Book Now')]
        self.assertEqual(m.normalize(data, '2026-09-14')[0]['status'], 'unknown')

    def test_unknown_tooltip_not_positive(self):
        data = fixture('valley')
        data['courts'] = [data['courts'][0]]
        data['courts'][0]['blocks'] = [dict(time='10:00 am - 11:00 am', classes='success', tooltip='Sign in')]
        self.assertEqual(m.normalize(data, '2026-09-14')[0]['status'], 'unknown')

    def test_conflicting_blocks_fail_closed(self):
        data = fixture('valley')
        data['courts'][0]['blocks'].append(dict(time='10:00 am - 11:00 am', classes='error', tooltip='Unavailable'))
        self.assertEqual(m.normalize(data, '2026-09-14', '10:00','11:00')[0]['status'], 'unknown')

    def test_unpublished_midday_is_unknown(self):
        rows = m.normalize(fixture('valley'), '2026-09-14', '13:00','14:00')
        self.assertEqual(rows[0]['status'], 'unknown')

    def test_do_not_merge_across_gap(self):
        self.assertFalse(m.covers([[600,660],[720,780]],600,780))

    def test_no_cross_court_combination(self):
        rows = m.normalize(fixture('valley'), '2026-09-14', '09:00','12:00')
        self.assertEqual(find(rows, 'Court 1')['status'], 'unavailable')

    def test_sport_aliases_are_specific(self):
        for sport in m.SPORTS:
            self.assertIn(sport, m.court_sports(sport.title()+' Court',''))

    def test_safe_detail_url(self):
        data = fixture('valley')
        data['courts'][0]['detail_url'] += '&_csrf_token=secret&action=UpdateSelection'
        url = m.normalize(data, '2026-09-14')[0]['detail_url']
        self.assertNotIn('secret', url)
        self.assertNotIn('action', url)

    def test_parse_actual_provider_markup_structure(self):
        html = (ROOT/'tests/fixtures/provider_excerpt.html').read_text()
        snap = m.parse_html(html, fixture('valley')['source_url'])
        rows = m.normalize(snap, '2026-09-14', '10:00', '12:00')
        self.assertEqual(rows[0]['status'], 'available')
        self.assertEqual(rows[0]['maximum_minutes'], 120)
        self.assertEqual(len(rows[0]['blocks']), 4)


class CommandBehavior(unittest.TestCase):
    def test_westwood_provider_typo_preserves_hybrid_sports(self):
        self.assertEqual(m.court_sports('Court 1 - Tennis/Pickelball Hybrid', 'Tennis Court'),
                         ['tennis', 'pickleball'])

    def test_griffith_pickleball_not_in_seed_still_requires_discovery(self):
        r=m.run(self.args(place='Griffith Park',sport='pickleball',date='2026-09-13',start='17:00',end='19:00'))
        self.assertEqual(r['resources'],[])
        self.assertEqual(r['fallback_requests'][0]['url'],m.DISCOVERY)
        self.assertEqual(r['coverage'],'partial')

    def test_browser_snapshot_supports_area_and_alias(self):
        for place in ['VNSO','Valley','Sherman Oaks','LA City']:
            with self.subTest(place=place):
                r=m.run(self.args(place=place,snapshot=str(ROOT/'tests/fixtures/valley_any.json')))
                self.assertEqual(r['available_count'],1)

    def test_search_time_uses_verified_provider_format(self):
        self.assertIn('begintime=5%3A00+PM',m.search_url('VNSO Pay Tennis','2026-09-14','17:00'))
        self.assertIn('begintime=12%3A00+AM',m.search_url('VNSO Pay Tennis','2026-09-14'))

    def test_snapshot_cli_path_preserves_date_and_count(self):
        r=m.run(self.args(place='',snapshot=str(ROOT/'tests/fixtures/valley_any.json')))
        self.assertEqual(r['available_count'],1)
        self.assertEqual(r['resources'][0]['observed_at'],'2026-09-11T16:59:02.714Z')

    def test_arbitrary_calendar_links_are_rejected(self):
        with self.assertRaises(ValueError):
            m.run(self.args(calendar_url='https://example.com/search.html'))

    def args(self, **kwargs):
        values=dict(place='VNSO',date='2026-09-14',start=None,end=None,sport=None,snapshot=None,json=True)
        return argparse.Namespace(**(values|kwargs))

    def test_http_failure_returns_browser_task(self):
        with patch.object(m,'fetch',side_effect=OSError('HTTP 403')):
            r=m.run(self.args())
        self.assertTrue(r['ok'])
        self.assertEqual(r['resources'][0]['status'],'lookup_failed')
        self.assertIn('InterfaceParameter=Iframe_Live_WebTrac',r['fallback_requests'][0]['url'])

    def test_start_only_defaults_to_hour(self):
        with patch.object(m,'fetch',side_effect=OSError('test')):
            r=m.run(self.args(start='17:00'))
        self.assertEqual(r['end'],'18:00')

    def test_invalid_windows(self):
        for kwargs in ({'end':'18:00'},{'start':'18:00','end':'17:00'}, {'start':'23:30'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                m.run(self.args(**kwargs))

    def test_basketball_contact_fallback_westside(self):
        r=m.run(self.args(place='Westwood',sport='basketball'))
        self.assertEqual(r['resources'][0]['status'],'unknown')
        self.assertEqual(r['resources'][0]['name'],'Westwood Recreation Center')
        self.assertTrue(r['fallback_requests'])

    def test_basketball_south_la(self):
        r=m.run(self.args(place='South LA',sport='basketball'))
        self.assertEqual(r['resources'][0]['name'],'Gilbert W. Lindsay Recreation Center')
        self.assertEqual(r['available_count'],0)

    def test_unlisted_sport_discovery(self):
        r=m.run(self.args(place='Downtown',sport='badminton'))
        self.assertEqual(r['available_count'],0)
        self.assertEqual(r['fallback_requests'][0]['url'],m.DISCOVERY)


if __name__ == '__main__':
    unittest.main()
