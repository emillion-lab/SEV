import json, re, urllib.request, urllib.parse

PROXY = 'https://mvr-proxy.mihov-emil.workers.dev/scrape?url='
def get(u):
    req = urllib.request.Request(PROXY + urllib.parse.quote(u, safe=''),
                                 headers={'User-Agent': 'sev-probe/1.0'})
    return urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')

for path in ['https://www.bilet.bg/bg/', 'https://www.bilet.bg/bg/search']:
    try:
        html = get(path)
        print('=' * 60)
        print(path, '→', len(html), 'байта')
        # Next.js данни
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        print('__NEXT_DATA__:', 'ДА' if m else 'не')
        if m:
            d = json.loads(m.group(1))
            open('/tmp/next.json', 'w').write(json.dumps(d)[:400000])
            def walk(o, depth=0, path=''):
                if depth > 4: return
                if isinstance(o, dict):
                    for k, v in list(o.items())[:25]:
                        if isinstance(v, list) and v and isinstance(v[0], dict):
                            keys = list(v[0].keys())[:9]
                            if any(x in str(keys).lower() for x in ['name','title','date','venue','event']):
                                print(f'  {path}.{k}: {len(v)} записа → {keys}')
                        walk(v, depth+1, path + '.' + k)
            walk(d)
        # JSON-LD
        lds = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        print('JSON-LD блокове:', len(lds))
        for ld in lds[:3]:
            try:
                o = json.loads(ld)
                t = o.get('@type') if isinstance(o, dict) else '?'
                print('   тип:', t)
            except: pass
    except Exception as e:
        print(path, 'ГРЕШКА:', e)
