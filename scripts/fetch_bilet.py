#!/usr/bin/env python3
"""
Bilet.bg → SEV събития.
Eventim блокира с 520, Bilet.bg е отворен и покрива партита,
концерти и фестивали — точно каквото театралният източник пропуска.
"""
import json, re, sys, urllib.request, urllib.parse, datetime

PROXY = 'https://mvr-proxy.mihov-emil.workers.dev/scrape?url='
BASE  = 'https://www.bilet.bg'
UA    = {'User-Agent': 'sev-bilet/1.0 (taxi demand research)'}

# Софийски зали с приблизителен капацитет
VENUES = {
    'арена 8888':          ('Арена 8888', 12000, 42.6711, 23.3692),
    'арена армеец':        ('Арена 8888', 12000, 42.6711, 23.3692),
    'ндк':                 ('НДК', 3380, 42.6866, 23.3190),
    'зала 1':              ('НДК Зала 1', 3380, 42.6866, 23.3190),
    'националния дворец':  ('НДК', 3380, 42.6866, 23.3190),
    'васил левски':        ('Стадион Васил Левски', 43000, 42.6879, 23.3396),
    'академик':            ('Зала Академик', 1200, 42.6680, 23.3520),
    'софия ринг':          ('София Ринг Мол', 2000, 42.6210, 23.3690),
    'винтидж':             ('Vintage Industrial', 800, 42.6980, 23.3300),
    'мixtape':             ('Mixtape 5', 900, 42.6866, 23.3190),
    'mixtape':             ('Mixtape 5', 900, 42.6866, 23.3190),
    'joy station':         ('Joy Station', 1500, 42.6700, 23.3520),
    'vidas':               ('Vidas Art Arena', 1500, 42.6690, 23.3760),
    'видас':               ('Vidas Art Arena', 1500, 42.6690, 23.3760),
    'малката текила':      ('Малката Текила', 400, 42.6950, 23.3280),
    'терминал 1':          ('Терминал 1', 600, 42.6980, 23.3250),
    'sofia live':          ('Sofia Live Club', 1000, 42.6866, 23.3190),
    'софия лайв':          ('Sofia Live Club', 1000, 42.6866, 23.3190),
}

MONTHS = {'януари':1,'февруари':2,'март':3,'април':4,'май':5,'юни':6,
          'юли':7,'август':8,'септември':9,'октомври':10,'ноември':11,'декември':12}


def get(url, timeout=35):
    req = urllib.request.Request(PROXY + urllib.parse.quote(url, safe=''), headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'replace')


def find_venue(text):
    low = (text or '').lower()
    for key, (name, cap, lat, lon) in VENUES.items():
        if key in low:
            return name, cap, lat, lon
    return None, None, None, None


def parse_date(text):
    """Разпознава 12.08.2026, 2026-08-12 и „12 август 2026“."""
    if not text:
        return None
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})', text)
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        return datetime.datetime(y, mo, d, h, mi)
    m = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\D{0,6}(\d{1,2}):(\d{2}))?', text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        h  = int(m.group(4)) if m.group(4) else 20
        mi = int(m.group(5)) if m.group(5) else 0
        return datetime.datetime(y, mo, d, h, mi)
    m = re.search(r'(\d{1,2})\s+(' + '|'.join(MONTHS) + r')\s*(\d{4})?', text, re.I)
    if m:
        d  = int(m.group(1))
        mo = MONTHS[m.group(2).lower()]
        y  = int(m.group(3)) if m.group(3) else datetime.date.today().year
        return datetime.datetime(y, mo, d, 20, 0)
    return None


def collect_links():
    links = set()
    for page in [BASE + '/bg/', BASE + '/bg/calendar']:
        try:
            html = get(page)
        except Exception as e:
            print('пропускам', page, e, file=sys.stderr)
            continue
        for href in re.findall(r'href="(/bg/events/[a-z0-9\-]+)(?:\?[^"]*)?"', html):
            links.add(BASE + href)
    return sorted(links)


def parse_event(url):
    try:
        html = get(url)
    except Exception:
        return None

    # 1) JSON-LD е най-надеждният път
    for ld in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            o = json.loads(ld)
        except Exception:
            continue
        items = o if isinstance(o, list) else [o]
        for it in items:
            if not isinstance(it, dict) or 'Event' not in str(it.get('@type', '')):
                continue
            name  = (it.get('name') or '').strip()
            start = parse_date(it.get('startDate') or '')
            loc   = it.get('location') or {}
            vtext = loc.get('name', '') if isinstance(loc, dict) else str(loc)
            addr  = loc.get('address', '') if isinstance(loc, dict) else ''
            blob  = f'{vtext} {addr}'
            vname, cap, lat, lon = find_venue(blob)
            if name and start:
                return {'name': name[:90], 'venue': vname or (vtext or '')[:60],
                        'lat': lat, 'lon': lon, 'cap': cap or 500,
                        'start': start.strftime('%Y-%m-%dT%H:%M:00+03:00'),
                        'url': url, 'src': 'bilet',
                        'city_ok': bool(vname) or 'софия' in blob.lower()}

    # 2) резервно: заглавие + дата от текста
    t = re.search(r'<title>([^<]{4,120})</title>', html)
    name = re.sub(r'\s*\|\s*Bilet\.bg.*$', '', t.group(1)).strip() if t else ''
    body = re.sub(r'<[^>]+>', ' ', html)
    start = parse_date(body[:6000])
    vname, cap, lat, lon = find_venue(body[:6000])
    if name and start:
        return {'name': name[:90], 'venue': vname or '', 'lat': lat, 'lon': lon,
                'cap': cap or 500, 'start': start.strftime('%Y-%m-%dT%H:%M:00+03:00'),
                'url': url, 'src': 'bilet',
                'city_ok': bool(vname) or 'софия' in body[:6000].lower()}
    return None


def main():
    links = collect_links()
    print(f'намерени връзки: {len(links)}')
    out, seen = [], set()
    for i, u in enumerate(links[:60], 1):
        ev = parse_event(u)
        if not ev:
            continue
        if not ev.pop('city_ok', False):      # само София
            continue
        key = (ev['name'], ev['start'])
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
        print(f"  {ev['start'][:16]}  {ev['name'][:50]}  @ {ev['venue']}")
    out.sort(key=lambda e: e['start'])
    json.dump({'source': 'bilet.bg', 'generated': datetime.datetime.now().isoformat(),
               'count': len(out), 'events': out},
              open('bilet_events.json', 'w'), ensure_ascii=False, indent=1)
    print(f'\nзаписани {len(out)} софийски събития')


if __name__ == '__main__':
    main()
