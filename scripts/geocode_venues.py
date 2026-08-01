#!/usr/bin/env python3
"""
Точни координати на залите чрез OpenStreetMap.

Ръчно въведените координати са приблизителни и бъркат с 200-800 м.
Този скрипт търси всяка зала по адрес и записва резултата в кеш,
така че координатите се уточняват сами, без ръчна проверка.
"""
import json, os, re, sys, time, urllib.parse, urllib.request

CACHE = 'venue_geo.json'
UA = {'User-Agent': 'sev-venue-geocoder/1.0 (sofia taxi demand research)'}

# Известни зали с ТОЧЕН адрес — търсим по адреса, не по името,
# защото адресът дава далеч по-надежден резултат.
KNOWN = {
    'хижа септември':      'Хижа Септември, Витоша, България',
    'септемvri hut':       'Хижа Септември, Витоша, България',
    'networking premium':  'улица Генерал Йосиф В. Гурко 16, София',
    'гурко 16':            'улица Генерал Йосиф В. Гурко 16, София',
    'theatro':             'улица Върбица 12, София',
    'театро':              'улица Върбица 12, София',
    'bar gatto':           'улица Шишман 22, София',
    'мixtape 5':           'бул. Черни връх 1, София',
    'mixtape 5':           'бул. Черни връх 1, София',
    'ндк':                 'Национален дворец на културата, София',
    'арена 8888':          'Арена София, бул. Асен Йорданов 1, София',
    'асикс арена':         'зала Фестивална, бул. Асен Йорданов, София',
    'интер експо':         'Интер Експо Център, бул. Цариградско шосе 147, София',
    'софия тех парк':      'София Тех Парк, бул. Цариградско шосе 111, София',
    'joy station':         'Joy Station, бул. Черни връх, София',
    'yalta':               'Yalta Club, бул. Цар Освободител 20, София',
    'paradise center':     'Paradise Center, бул. Черни връх 100, София',
    'малката текила':      'Малката Текила, ул. Ангел Кънчев, София',
    'пиротска':            'улица Пиротска 5, София',
    'sofia event center':  'Sofia Event Center, бул. Черни връх 100, София',
    'театър 199':          'Театър 199, ул. Славянска 8, София',
}


def load():
    try:
        return json.load(open(CACHE, encoding='utf-8'))
    except Exception:
        return {}


def geocode(query):
    url = ('https://nominatim.openstreetmap.org/search?q='
           + urllib.parse.quote(query) + '&format=json&limit=1&countrycodes=bg')
    try:
        req = urllib.request.Request(url, headers=UA)
        d = json.loads(urllib.request.urlopen(req, timeout=25).read().decode())
        if not d:
            return None
        lat, lon = float(d[0]['lat']), float(d[0]['lon'])
        # приемаме само район София и Витоша
        if not (42.50 <= lat <= 42.82 and 23.10 <= lon <= 23.55):
            print(f'   извън района: {lat},{lon}', file=sys.stderr)
            return None
        return {'lat': round(lat, 5), 'lon': round(lon, 5),
                'display': d[0].get('display_name', '')[:80], 'q': query}
    except Exception as e:
        print('   грешка:', e, file=sys.stderr)
        return None


def main():
    cache = load()
    updated = 0
    for key, query in KNOWN.items():
        if key in cache and cache[key] and cache[key].get('q') == query:
            continue
        print(f'търся: {key}  ←  {query}')
        r = geocode(query)
        if r:
            cache[key] = r
            updated += 1
            print(f'   ✓ {r["lat"]},{r["lon"]}  {r["display"][:56]}')
        else:
            print('   ✗ не е намерена')
        time.sleep(1.2)          # услугата иска най-много 1 заявка/сек

    json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\nобновени {updated} зали, общо в кеша: {len(cache)}')


if __name__ == '__main__':
    main()
