#!/usr/bin/env python3
"""Explicit, opt-in integration checks. These make real read-only browser requests.

Run with a Python 3 runtime that has Playwright and Chrome available:
  check_live_calendars.py --date YYYY-MM-DD

Optionally narrow with --location 'VNSO Pay Tennis' or change --start/--end.
Success proves calendar retrieval and row enumeration, not downstream formatting.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from live_calendar import LOCATIONS, retrieve

EXPECTED = dict(zip(LOCATIONS, (22, 14, 8, 12, 14, 12, 8, 8, 2, 7, 1)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--date', required=True)
    p.add_argument('--start', default='17:00')
    p.add_argument('--end', default='19:00')
    p.add_argument('--location', choices=LOCATIONS)
    args = p.parse_args()
    failures = 0
    for location in [args.location] if args.location else LOCATIONS:
        try:
            r = retrieve(location, args.date, args.start, args.end)
            assert r['retrieval'] == 'live_isolated_chrome'
            assert r['resource_count'] == EXPECTED[location], (r['resource_count'], EXPECTED[location])
            names = [x['name'] for x in r['resources']]
            assert len(names) == len(set(names)), 'Duplicate resources'
            if location == 'BalboaPayTennis':
                assert {'Pickleball Court G', 'Pickleball Court H'} <= set(names)
                assert r['pages_read'] >= 2
            print(json.dumps(dict(location=location, passed=True, count=r['resource_count'],
                                  pages=r['pages_read'], observed_at=r['observed_at'])), flush=True)
        except Exception as exc:
            failures += 1
            print(json.dumps(dict(location=location, passed=False, error=str(exc))), flush=True)
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
