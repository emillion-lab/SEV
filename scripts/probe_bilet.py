import json, re, urllib.request, urllib.parse

PROXY = 'https://mvr-proxy.mihov-emil.workers.dev/scrape?url='
def get(u):
    req = urllib.request.Request(PROXY + urllib.parse.quote(u, safe=''),
                                 headers={'User-Agent': 'sev-probe/1.0'})
    return urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')

html = get('https://www.bilet.bg/bg/')

# 1. Търсим API следи в кода на страницата
apis = set(re.findall(r'["\'](/api/[a-zA-Z0-9/_\-{}\.]+)["\']', html))
print('вътрешни /api/ пътища:', len(apis))
for a in sorted(apis)[:25]: print('  ', a)

abs_api = set(re.findall(r'https?://[a-z0-9\.\-]+/(?:api|graphql)[a-zA-Z0-9/_\-\.]*', html))
print('\nабсолютни API адреси:', len(abs_api))
for a in sorted(abs_api)[:12]: print('  ', a)

# 2. Има ли събития направо в HTML-а
print('\n--- следи от събития в HTML ---')
for pat, label in [(r'"eventId"', 'eventId'), (r'"startDate"', 'startDate'),
                   (r'"venue"', 'venue'), (r'data-event', 'data-event'),
                   (r'class="[^"]*event[^"]*"', 'class=event')]:
    print(f'  {label}: {len(re.findall(pat, html))}')

# 3. Заглавия на събития по типични селектори
titles = re.findall(r'<h[23][^>]*>\s*([^<]{6,70})\s*</h[23]>', html)
print('\nзаглавия h2/h3:', len(titles))
for t in titles[:15]: print('  ', t.strip())
