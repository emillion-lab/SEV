import json, re, urllib.request, urllib.parse

PROXY = 'https://mvr-proxy.mihov-emil.workers.dev/scrape?url='
def get(u):
    req = urllib.request.Request(PROXY + urllib.parse.quote(u, safe=''),
                                 headers={'User-Agent': 'sev-probe/1.0'})
    return urllib.request.urlopen(req, timeout=35).read().decode('utf-8', 'replace')

html = get('https://www.bilet.bg/bg/')

# връзки към конкретни събития
links = sorted(set(re.findall(r'href="(/bg/[a-z0-9\-]+/[a-z0-9\-]{6,})"', html)))
print('връзки към събития:', len(links))
for l in links[:20]: print('  ', l)

# има ли дати някъде в текста
dates = re.findall(r'(\d{1,2}\s+(?:яну|фев|мар|апр|май|юни|юли|авг|сеп|окт|ное|дек)[а-я]*\.?\s*\d{0,4})', html, re.I)
print('\nнамерени дати:', len(dates), '| примери:', dates[:8])

# пробваме конкретна категория
for cat in ['/bg/partita', '/bg/koncerti', '/bg/festivali']:
    try:
        h = get('https://www.bilet.bg' + cat)
        ls = sorted(set(re.findall(r'href="(/bg/[a-z0-9\-]+/[a-z0-9\-]{6,})"', h)))
        ds = re.findall(r'(\d{1,2}\.\d{2}\.\d{4})', h)
        print(f'\n{cat}: {len(h)} байта | връзки: {len(ls)} | дати: {len(ds)}')
        for l in ls[:8]: print('    ', l)
        if ds: print('    дати:', ds[:6])
    except Exception as e:
        print(f'\n{cat}: ГРЕШКА {e}')
