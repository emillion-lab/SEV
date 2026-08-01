import re, urllib.request, urllib.parse

PROXY = 'https://mvr-proxy.mihov-emil.workers.dev/scrape?url='
def get(u):
    req = urllib.request.Request(PROXY + urllib.parse.quote(u, safe=''),
                                 headers={'User-Agent': 'sev-probe/1.0'})
    return urllib.request.urlopen(req, timeout=35).read().decode('utf-8', 'replace')

html = get('https://www.bilet.bg/bg/')

# всички href-ове — да видим реалния формат
hrefs = sorted(set(re.findall(r'href="([^"]{4,90})"', html)))
print('общо връзки:', len(hrefs))
print('\n-- примери --')
for h in hrefs[:35]: print('  ', h)

# контекст около една дата
m = re.search(r'.{700}\d{1,2}\s+(?:август|септември|октомври).{500}', html, re.S)
if m:
    frag = re.sub(r'\s+', ' ', m.group(0))
    print('\n-- контекст около дата --')
    print(frag[:1100])
