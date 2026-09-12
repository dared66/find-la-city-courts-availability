#!/usr/bin/env python3
"""Read public WebTrac calendars in an isolated, headed Chrome session."""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from find_availability import search_url, minutes, clock, normalize

LOCATIONS = ('BalboaPayTennis', 'Cheviot Hills Pay Tennis', 'Poinsettia Pay Tennis',
             'Riverside Courts Pay Tennis', 'VNSO Pay Tennis', 'Vermont Canyon Pay Tennis',
             'Westchester Pay Tennis', 'Westwood Pay Tennis', 'Westwood RC',
             'Travel Town', 'Palisades RC')


def retrieve(location, day, start=None, end=None):
    from playwright.sync_api import sync_playwright
    date.fromisoformat(day)
    if location not in LOCATIONS:
        raise ValueError('Location outside the supported calendar list')
    if end and not start:
        raise ValueError('End requires start')
    first = minutes(start) if start else 0
    last = minutes(end) if end else first + 60 if start else 1440
    if not first < last <= 1440:
        raise ValueError('Invalid same-day interval')
    extract = (Path(__file__).with_name('extract_calendar.js')).read_text()
    snapshots = []
    with sync_playwright() as p:
        # Headed Chrome is necessary on this host. Use a temporary profile;
        # no personal cookies, CDP server, browser setting changes or stealth.
        browser = p.chromium.launch(channel='chrome', headless=False, chromium_sandbox=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(30000)
            for begin in range(first, last, 120):
                url = search_url(location, day, clock(begin))
                response = page.goto(url, wait_until='domcontentloaded')
                if not response or response.status >= 400:
                    raise RuntimeError(f'Calendar HTTP {response.status if response else "unknown"}')
                page.locator('table#frwebsearch_output_table').first.wait_for()
                seen = set()
                while True:
                    page.locator('[data-title="Facility Description"]').first.wait_for()
                    page.locator('[id^="date_vm_"][id$="_button"]').wait_for()
                    snap = page.evaluate(extract)
                    # Use the actual requested date query as navigation can omit
                    # it on pagination; the independently extracted UI and row
                    # dates must still match in normalize / checks below.
                    snap['source_url'] = url
                    expected = date.fromisoformat(day).strftime('%m/%d/%Y')
                    if snap.get('date') != expected or any(c.get('date') != expected or c.get('location') != {'BalboaPayTennis': 'Balboa Pay Tennis', 'VNSO Pay Tennis': 'Van Nuys/Sherman Oaks Pay Tennis'}.get(location, location) for c in snap['courts']):
                        raise RuntimeError(f'Calendar date/location mismatch: displayed={snap.get("date")}, rows={sorted(set((c.get("date"), c.get("location")) for c in snap["courts"]))}')
                    match = re.search(r'Showing results (\d+)-(\d+) of (\d+)', snap.get('summary') or '')
                    if not match:
                        raise RuntimeError('Cannot verify calendar pagination')
                    lo, hi, total = map(int, match.groups())
                    if len(snap['courts']) != hi - lo + 1:
                        raise RuntimeError('Calendar rows do not match the displayed result count')
                    if lo in seen:
                        raise RuntimeError('Calendar pagination did not advance')
                    seen.add(lo)
                    snapshots.append(snap)
                    if hi == total:
                        break
                    next_page = len(seen) + 1
                    page.locator(f'button[data-click-set-name="page"][data-click-set-value="{next_page}"]').first.click()
                    page.wait_for_function('(old) => document.querySelector("#frwebsearch_nextgenresultsgroup h1")?.textContent.trim() !== old', arg=snap['summary'])
        finally:
            browser.close()
    merged = dict(snapshots[0], courts=[])
    resources = {}
    for snap in snapshots:
        for row in snap['courts']:
            key = (row['name'], row['location'], row['detail_url'])
            if key not in resources:
                resources[key] = dict(row, blocks=[])
            for block in row['blocks']:
                if block not in resources[key]['blocks']:
                    resources[key]['blocks'].append(block)
    merged['courts'] = list(resources.values())
    general = location in ('Travel Town', 'Palisades RC')
    rows = merged['courts'] if general else normalize(merged, day, start, end or clock(last) if start else None)
    for row in rows:
        for block in row['blocks']:
            classes = block.get('classes', '').split()
            bookable = (block.get('status') == 'available' if not general else
                        'success' in classes and 'error' not in classes and
                        block.get('tooltip', '').strip().lower() == 'book now')
            if bookable:
                begin = block['time'].split(' - ')[0] if general else block['start']
                block['booking_url'] = search_url(location, day, begin)
    return dict(ok=True, retrieval='live_isolated_chrome', location=location, date=day,
                start=start, end=end or (clock(last) if start else None),
                observed_at=merged['captured_at'], source_url=merged['source_url'],
                pages_read=len(snapshots), resource_count=len(rows), resources=rows,
                interpretation='Read raw block classes and tooltip: Book Now = online-bookable; Inquiry Only = staff confirmation; missing blocks = unknown.' if general else 'Normalized court status; check duration and slot boundaries.',
                coverage='All result pages read. Time queries every two hours; missing blocks remain unknown.',
                physical_occupancy_verified=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--location', required=True, choices=LOCATIONS)
    p.add_argument('--date', required=True)
    p.add_argument('--start')
    p.add_argument('--end')
    p.add_argument('--sport')
    args = p.parse_args()
    try:
        result = retrieve(args.location, args.date, args.start, args.end)
        if args.sport:
            if args.location in ('Travel Town', 'Palisades RC'):
                raise ValueError('Use resource names, not --sport, for this calendar')
            result['resources'] = [r for r in result['resources'] if args.sport in r['sports']]
            result['resource_count'] = len(result['resources'])
    except Exception as exc:
        result = dict(ok=False, retrieval='failed', error=str(exc), resources=[])
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
