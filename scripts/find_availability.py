#!/usr/bin/env python3
"""Read-only LA City courts lookup; standard library only."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SEARCH = 'https://reg.recreation.parks.lacity.gov/web/wbwsc/webtrac.wsc/search.html'
DISCOVERY = 'https://recreation.parks.lacity.gov/discover-facilities'
SPORTS = ('tennis', 'pickleball', 'paddle tennis', 'basketball', 'volleyball',
          'badminton', 'handball', 'racquetball', 'futsal')


class ProviderError(ValueError):
    pass


class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    @property
    def text(self):
        return ' '.join(' '.join(c.text if isinstance(c, Node) else c
                                 for c in self.children).split())

    def find(self, predicate):
        found = []
        for c in self.children:
            if isinstance(c, Node):
                if predicate(c):
                    found.append(c)
                found.extend(c.find(predicate))
        return found


class Tree(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node()
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                       'link', 'meta', 'param', 'source', 'track', 'wbr'):
            self.current = node

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def minutes(value):
    for fmt in ('%H:%M', '%I:%M %p'):
        try:
            t = datetime.strptime(value.strip().upper(), fmt)
            return t.hour * 60 + t.minute
        except ValueError:
            pass
    raise ValueError(f'Invalid time: {value}')


def clock(value):
    return f'{value // 60:02d}:{value % 60:02d}'


def search_url(location, day, start=None):
    start_minutes = minutes(start) if start else 0
    begin = datetime.strptime(clock(start_minutes), '%H:%M').strftime('%I:%M %p').lstrip('0')
    return SEARCH + '?' + urlencode(dict(InterfaceParameter='Iframe_Live_WebTrac',
        arwebsearch_buttonsearch='yes', begintime=begin,
        date=date.fromisoformat(day).strftime('%m/%d/%Y'), location=location, module='FR'))


def parse_html(html, source_url):
    tree = Tree(html).root
    tables = tree.find(lambda n: n.tag == 'table' and n.attrs.get('id') == 'frwebsearch_output_table')
    if not tables:
        raise ProviderError('No court calendar was returned; browser fallback required.')
    courts = []
    for table in tables:
        def field(label):
            ns = table.find(lambda n: n.attrs.get('data-title') == label)
            return ns[0].text if ns else ''
        details = table.find(lambda n: n.tag == 'a' and 'iteminfo.html' in n.attrs.get('href', ''))
        dates = table.find(lambda n: n.attrs.get('class') == 'dateblock')
        # WebTrac groups the description and table in a resource wrapper.
        headers = tree.find(lambda n: 'result-header__info' in n.attrs.get('class', '').split())
        matched = [h for h in headers if any(n.text == field('Facility Description')
                   for n in h.find(lambda n: n.tag == 'h2'))]
        rules = matched[0].text if matched else ''
        blocks = table.find(lambda n: n.tag == 'a' and
                            'cart-button--state-block' in n.attrs.get('class', '').split())
        courts.append(dict(name=field('Facility Description'), location=field('Location Description'),
            category=field('Class Description'), date=dates[0].attrs.get('data-tooltip') if dates else None,
            detail_url=details[0].attrs['href'] if details else None, rules=rules,
            blocks=[dict(time=n.text, classes=n.attrs.get('class', ''),
                         tooltip=n.attrs.get('data-tooltip', '')) for n in blocks]))
    summary = tree.find(lambda n: n.tag in ('h1', 'h2') and 'Showing results' in n.text)
    return dict(source_url=source_url, captured_at=datetime.now(timezone.utc).isoformat(),
                summary=summary[0].text if summary else '', courts=courts)


def court_sports(name, category):
    # Court identity overrides the generic "Tennis Court" class on pickleball/paddle rows.
    name = name.lower().replace('pickelball', 'pickleball')
    category = category.lower().replace('pickelball', 'pickleball')
    explicit = [s for s in SPORTS if s in name.lower()]
    if 'paddle tennis' in explicit:
        explicit.remove('tennis')
    return explicit or [s for s in SPORTS if s in category.lower()]


def merge(ranges):
    result = []
    for a, b in sorted(ranges):
        if result and a <= result[-1][1]:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([a, b])
    return result


def covers(ranges, start, end):
    return any(a <= start and b >= end for a, b in merge(ranges))


def normalize(snapshot, day, start=None, end=None, sport=None):
    source = snapshot.get('source_url', '')
    parsed = urlparse(source)
    query = parse_qs(parsed.query)
    if parsed.hostname != 'reg.recreation.parks.lacity.gov' or parsed.path != urlparse(SEARCH).path:
        raise ProviderError('Snapshot is not from the official court-search page.')
    expected = date.fromisoformat(day).strftime('%m/%d/%Y')
    if query.get('date') != [expected]:
        raise ProviderError('Calendar URL date does not match the requested date.')
    if snapshot.get('date') and snapshot['date'] != expected:
        raise ProviderError('Displayed calendar date does not match the request.')
    if not isinstance(snapshot.get('courts'), list) or not snapshot['courts']:
        raise ProviderError('No readable court calendar; availability is unknown.')
    result = []
    for c in snapshot['courts']:
        if c.get('date') != expected:
            raise ProviderError('A court row has a missing or different date.')
        sports = court_sports(c.get('name', ''), c.get('category', ''))
        if not sports or (sport and sport not in sports):
            continue
        available, unavailable, blocks = [], [], []
        malformed = False
        for b in c.get('blocks', []):
            pair = re.split(r'\s*-\s*', b.get('time', ''))
            if len(pair) != 2:
                malformed = True
                continue
            try:
                a, z = map(minutes, pair)
            except ValueError:
                malformed = True
                continue
            if z <= a:
                malformed = True
                continue
            classes = b.get('classes', '').split()
            tooltip = unescape(re.sub('<[^>]+>', '', b.get('tooltip', '')))
            status = 'unknown'
            if 'error' in classes and 'unavailable' in tooltip.lower():
                status = 'unavailable'
                unavailable.append([a, z])
            elif 'success' in classes and 'error' not in classes and tooltip.lower() == 'book now':
                status = 'available'
                available.append([a, z])
            blocks.append(dict(start=clock(a), end=clock(z), status=status, provider_text=tooltip,
                booking_restriction='days before' in tooltip.lower() or 'cutoff time' in tooltip.lower()))
        rules = c.get('rules') or ''
        limit = re.search(r'maximum of (\w+) hours?', rules, re.I)
        numbers = {'one': 1, 'two': 2, 'three': 3, 'four': 4}
        maximum = None
        if limit:
            val = limit[1].lower()
            maximum = 60 * (int(val) if val.isdigit() else numbers.get(val, 0)) or None
        # Contradictory blocks cannot support a positive availability claim.
        conflict = any(a < d and z > b for a, z in available for b, d in unavailable)
        status = 'unknown' if conflict else ('available' if available else
                 'unavailable' if unavailable and not malformed and all(b['status'] == 'unavailable' for b in blocks) else 'unknown')
        duration_valid = None
        slot_aligned = None
        if start is not None:
            a, z = minutes(start), minutes(end)
            duration_valid = z - a <= maximum if maximum else None
            slot_aligned = a in [b for b, _ in available] and z in [d for _, d in available]
            if not conflict and covers(available, a, z):
                status = 'available'
            elif not conflict and any(b < z and d > a for b, d in unavailable):
                status = 'unavailable'
            else:
                status = 'unknown'
        detail = c.get('detail_url') or ''
        dp = urlparse(detail)
        safe_detail = None
        if dp.hostname == parsed.hostname and dp.path.endswith('/iteminfo.html'):
            did = parse_qs(dp.query).get('FMID', [''])[0]
            if did.isdigit():
                safe_detail = f'{dp.scheme}://{dp.netloc}{dp.path}?' + urlencode({'Module':'FR','FMID':did})
        result.append(dict(name=c['name'], location=c['location'], sports=sports,
            status=status, open_windows=[dict(start=clock(a), end=clock(z)) for a,z in merge(available)] if not conflict else [],
            blocks=blocks, maximum_minutes=maximum, requested_duration_valid=duration_valid,
            requested_matches_published_boundaries=slot_aligned,
            restrictions=rules, booking_method='official_online_calendar', detail_url=safe_detail,
            search_url=source, observed_at=snapshot.get('captured_at')))
    return result


def fetch(url):
    req = Request(url, headers={'User-Agent':'LACityCourtsAvailability/1.0', 'Accept':'text/html'})
    with urlopen(req, timeout=25) as response:
        return response.read(5_000_000).decode('utf-8', errors='replace'), response.url


def run(args):
    date.fromisoformat(args.date)
    if args.place.casefold().strip() in ('la', 'la city', 'los angeles', 'los angeles city', 'citywide'):
        args.place = ''
    if args.end and not args.start:
        raise ValueError('--end requires --start')
    if args.start:
        a = minutes(args.start)
        z = minutes(args.end) if args.end else a + 60
        if z <= a or z >= 1440:
            raise ValueError('Time window must end after start, within the same day.')
        args.start, args.end = clock(a), clock(z)
    result = dict(ok=True, date=args.date, timezone='America/Los_Angeles',
        time_mode='specific' if args.start else 'any', start=args.start, end=args.end,
        resources=[], fallback_requests=[], coverage='partial',
        notes=['Reservation availability is not physical occupancy or a completed reservation.',
               'Catalog coverage is partial; use official facility discovery for other LA City courts.'])
    if args.snapshot:
        data = json.loads(sys.stdin.read() if args.snapshot == '-' else Path(args.snapshot).read_text())
        snapshots = data if isinstance(data, list) else [data]
        for snap in snapshots:
            result['resources'].extend(normalize(snap, args.date, args.start, args.end, args.sport))
        if args.place:
            wanted = args.place.casefold()
            catalog = json.loads((ROOT / 'references/catalog.json').read_text())['facilities']
            aliases = [p for p in catalog if all(t in ' '.join([p['name'],p['area']]+p.get('aliases',[])).casefold()
                       for t in wanted.split())]
            def norm(s):
                return ' '.join(re.sub(r'[^a-z0-9 ]',' ',s.casefold()).split())
            def matches(r):
                text = norm(r['name']+' '+r['location'])
                return norm(wanted) in text or any(norm(p['name'].replace(' Courts','')) in text for p in aliases)
            result['resources'] = [r for r in result['resources'] if matches(r)]
        result['available_count'] = sum(r['status'] == 'available' for r in result['resources'])
        result['notes'].append('Snapshot replay: availability is as of observed_at, not a fresh lookup.')
        return result
    if getattr(args, 'calendar_url', None):
        url = urlparse(args.calendar_url)
        if url.hostname != urlparse(SEARCH).hostname or url.path != urlparse(SEARCH).path:
            raise ValueError('--calendar-url must be an official WebTrac search URL.')
        location = parse_qs(url.query).get('location', [''])[0]
        if not location:
            raise ValueError('Official calendar URL must contain its location parameter.')
        clean_url = search_url(location, args.date, args.start)
        try:
            html, final_url = fetch(clean_url)
            result['resources'] = normalize(parse_html(html, final_url), args.date, args.start, args.end, args.sport)
        except (OSError, ValueError) as exc:
            result['fallback_requests'].append(dict(url=clean_url, reason=str(exc),
                action='Read calendar using scripts/extract_calendar.js; pass JSON to --snapshot.'))
        result['available_count'] = sum(r['status'] == 'available' for r in result['resources'])
        return result
    catalog = json.loads((ROOT / 'references/catalog.json').read_text())
    places = catalog['facilities']
    if args.place:
        terms = args.place.casefold().split()
        places = [p for p in places if all(t in ' '.join([p['name'], p['area']] + p.get('aliases', [])).casefold() for t in terms)]
    for p in places:
        if args.sport and p.get('sports') and args.sport not in p['sports']:
            continue
        if not p.get('webtrac_location'):
            result['resources'].append(dict(name=p['name'], location=p['area'], sports=p.get('sports', []),
                status='unknown', booking_method='verify_official_route', detail_url=p['url'],
                contact=p.get('contact'), open_windows=[], observed_at=None,
                reason='Public calendar not verified; check the official facility page.',
                catalog_verified_at=catalog['verified_at']))
            result['fallback_requests'].append(dict(url=p['url'], action='Inspect facility amenities and current reservation link.'))
            continue
        url = search_url(p['webtrac_location'], args.date, args.start)
        try:
            html, final_url = fetch(url)
            result['resources'].extend(normalize(parse_html(html, final_url), args.date, args.start, args.end, args.sport))
        except (OSError, ValueError) as exc:
            result['resources'].append(dict(name=p['name'], location=p['area'], status='lookup_failed',
                reason=str(exc), detail_url=p['url'], search_url=url, open_windows=[]))
            result['fallback_requests'].append(dict(url=url, action='Read calendar using scripts/extract_calendar.js; pass JSON to --snapshot.'))
    if not places or not result['resources'] or args.sport not in (None, 'tennis', 'pickleball', 'paddle tennis') or not args.place:
        result['fallback_requests'].append(dict(url=DISCOVERY,
            action='Search requested area and sport; verify court amenities, reservation links, and staff contacts.'))
    result['available_count'] = sum(r['status'] == 'available' for r in result['resources'])
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('place', nargs='?', default='')
    p.add_argument('--date', required=True)
    p.add_argument('--start')
    p.add_argument('--end')
    p.add_argument('--sport', choices=SPORTS)
    p.add_argument('--snapshot', help='Browser JSON observation file, or - for stdin; never treated as fresh data.')
    p.add_argument('--calendar-url', help='Official WebTrac search link for a location outside the seed catalog.')
    p.add_argument('--json', action='store_true')
    args = p.parse_args()
    try:
        result = run(args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result = dict(ok=False, error=str(exc))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"LA City courts — {args.date} — {result.get('time_mode', 'error')}")
        for r in result.get('resources', [])[:5]:
            print(f"{r['name']} ({r['location']}): {r['status']}")
            print('  ' + str(r.get('open_windows', [])))
            print('  ' + str(r.get('detail_url') or r.get('search_url') or ''))
        for request in result.get('fallback_requests', []):
            print('Browser follow-up: ' + request['url'])
        for note in result.get('notes', []):
            print(note)
        if not result['ok']:
            print(result['error'])
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
