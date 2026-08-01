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
# Проверени координати. Хижа Септември и Гурко 16 са потвърдени по Google Maps.
VENUES = {
    'септември':           ('Хижа Септември (Витоша)', 500, 42.5945, 23.2857),
    'septemvri':           ('Хижа Септември (Витоша)', 500, 42.5945, 23.2857),
    'гурко':               ('Networking Premium (Гурко 16)', 500, 42.6919, 23.3260),
    'gurko':               ('Networking Premium (Гурко 16)', 500, 42.6919, 23.3260),
    'networking':          ('Networking Premium (Гурко 16)', 500, 42.6919, 23.3260),
    'театро':              ('Théatro отсам канала', 600, 42.6873, 23.3452),
    'theatro':             ('Théatro отсам канала', 600, 42.6873, 23.3452),
    'отсам канала':        ('Théatro отсам канала', 600, 42.6873, 23.3452),
    'върбица':             ('Théatro отсам канала', 600, 42.6873, 23.3452),
    'интер експо':         ('Интер Експо Център', 3000, 42.6520, 23.3760),
    'inter expo':          ('Интер Експо Център', 3000, 42.6520, 23.3760),
    'тех парк':            ('София Тех Парк', 1500, 42.6668, 23.3760),
    'tech park':           ('София Тех Парк', 1500, 42.6668, 23.3760),
    'атанасов':            ('София Тех Парк', 1500, 42.6668, 23.3760),
    'парадайс':            ('Paradise Center', 2000, 42.6607, 23.3122),
    'paradise':            ('Paradise Center', 2000, 42.6607, 23.3122),
    'yalta':               ('Yalta Garden', 700, 42.6918, 23.3243),
    'ялта':                ('Yalta Garden', 700, 42.6918, 23.3243),
    'gatto':               ('Bar Gatto', 300, 42.6907, 23.3320),
    'пиротска':            ('Пиротска 5', 600, 42.6987, 23.3195),
    'асикс':               ('Асикс Арена', 4000, 42.6690, 23.3757),
    'фестивална':          ('Асикс Арена', 4000, 42.6690, 23.3757),
    'sofia event':         ('Sofia Event Center', 2000, 42.6607, 23.3122),
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


# ── Автоматично геокодиране за непознати зали ──
_GEO_CACHE_PATH = 'venue_geo.json'
try:
    _GEO_CACHE = json.load(open(_GEO_CACHE_PATH, encoding='utf-8'))
except Exception:
    _GEO_CACHE = {}


def geocode(venue_name):
    """Търси координати през OpenStreetMap. Резултатите се кешират,
    за да не питаме повторно и да не натоварваме услугата."""
    if not venue_name:
        return None, None
    key = venue_name.strip().lower()[:70]
    if key in _GEO_CACHE:
        c = _GEO_CACHE[key]
        return (c.get('lat'), c.get('lon')) if c else (None, None)

    q = urllib.parse.quote(venue_name.strip()[:70] + ', София, България')
    url = f'https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1&countrycodes=bg'
    lat = lon = None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'sev-bilet-geocoder/1.0 (taxi demand)'})
        data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
        if data:
            lat, lon = float(data[0]['lat']), float(data[0]['lon'])
            # приемаме само резултати в района на София
            if not (42.55 <= lat <= 42.80 and 23.15 <= lon <= 23.50):
                lat = lon = None
    except Exception as e:
        print('геокодиране пропаднало:', venue_name[:40], e, file=sys.stderr)

    _GEO_CACHE[key] = {'lat': lat, 'lon': lon} if lat else None
    try:
        json.dump(_GEO_CACHE, open(_GEO_CACHE_PATH, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
    except Exception:
        pass
    import time as _t
    _t.sleep(1.1)          # услугата иска най-много една заявка в секунда
    return lat, lon


# Думи, които се срещат и в дати — искат допълнително потвърждение
AMBIGUOUS = {'септември': 'хижа', 'septemvri': 'hut'}


# Кешираните геокодирани адреси са по-точни от ръчната таблица,
# защото идват от реалния адрес на залата.
PREFER_GEO = True


def find_venue(text):
    low = (text or '').lower()
    for key, (name, cap, lat, lon) in VENUES.items():
        if key not in low:
            continue
        need = AMBIGUOUS.get(key)
        if need:
            ok = False
            for m in re.finditer(re.escape(key), low):
                around = low[max(0, m.start()-25): m.end()+25]
                if need in around:        # „хижа Септември“, не „5 септември“
                    ok = True
                    break
            if not ok:
                continue
        # ако имаме геокодиран адрес за същата зала, той има предимство
        if PREFER_GEO:
            for ck in (key, name.strip().lower()[:70]):
                c = _GEO_CACHE.get(ck)
                if c and c.get('lat'):
                    return name, cap, c['lat'], c['lon']
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
            # адресът може да е обект със street/locality — сглобяваме го
            street = city = ''
            if isinstance(addr, dict):
                street = addr.get('streetAddress', '') or ''
                city   = addr.get('addressLocality', '') or ''
                addr   = ' '.join(x for x in [street, city] if x)
            # координати направо от източника, ако ги дава
            geo = loc.get('geo') if isinstance(loc, dict) else None
            src_lat = src_lon = None
            if isinstance(geo, dict):
                try:
                    src_lat = float(geo.get('latitude'))
                    src_lon = float(geo.get('longitude'))
                except Exception:
                    src_lat = src_lon = None
            blob  = f'{vtext} {addr}'
            vname, cap, lat, lon = find_venue(blob)
            if name and start:
                # 1) координати от самия източник — най-достоверни
                if src_lat and 42.55 <= src_lat <= 42.80:
                    lat, lon = src_lat, src_lon
                # 2) точен уличен адрес бие приблизителната таблица
                elif street:
                    glat, glon = geocode(street + ', София')
                    if glat:
                        lat, lon = glat, glon
                # 2) геокодиране по ПЪЛНИЯ адрес — най-точното, което имаме
                if lat is None and (street or addr):
                    lat, lon = geocode((street or addr) + ', София')
                # 3) по името на залата
                if lat is None:
                    lat, lon = geocode(vtext or '')
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
    # Търсим залата САМО в заглавието и в явно обозначено място.
    # Търсенето в тялото лепеше случайни съвпадения (напр. всяко
    # събитие през август попадаше на „хижа Септември").
    mloc = re.search(r'(?:място|локация|зала|venue|адрес)\s*[:\-]\s*(.{0,90})', body[:8000], re.I)
    vscope = name + ' ' + (mloc.group(1) if mloc else '')
    vname, cap, lat, lon = find_venue(vscope)
    if name and start:
        if lat is None:
            m2 = re.search(r'(?:зала|клуб|център|хижа|hall|club|center)[^<\n,\.]{2,40}', body[:6000], re.I)
            lat, lon = geocode(m2.group(0) if m2 else '')
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
