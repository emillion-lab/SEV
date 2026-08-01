import json, re, urllib.request, urllib.parse
PROXY = 'https://mvr-proxy.mihov-emil.workers.dev/scrape?url='
UA = {'User-Agent': 'sev-probe/1.0'}

def get(u):
    req = urllib.request.Request(PROXY + urllib.parse.quote(u, safe=''), headers=UA)
    return urllib.request.urlopen(req, timeout=35).read().decode('utf-8','replace')

# вземаме няколко реални събития и гледаме какъв адрес дават
b = json.load(open('bilet_events.json'))
for e in b['events'][:5]:
    url = e.get('url','')
    if not url: continue
    print('='*66)
    print(e['name'][:50], '| таблица →', e.get('venue'), e.get('lat'), e.get('lon'))
    try:
        h = get(url)
    except Exception as ex:
        print('  грешка:', ex); continue
    for ld in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try: o = json.loads(ld)
        except Exception: continue
        items = o if isinstance(o, list) else [o]
        for it in items:
            if not isinstance(it, dict) or 'Event' not in str(it.get('@type','')): continue
            loc = it.get('location') or {}
            print('  location.name:', repr(loc.get('name'))[:70])
            print('  address:', json.dumps(loc.get('address'), ensure_ascii=False)[:180])
            print('  geo:', json.dumps(loc.get('geo'), ensure_ascii=False)[:120])
