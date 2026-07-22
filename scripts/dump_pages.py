# Диагностичен дъмп: записва суровия HTML на проблемните страници в debug/
# за да напишем parser-ите по реалната структура, без сляпо гадаене.
import os, ssl, re
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.parse import quote

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "Accept-Language": "bg,en;q=0.8"}
PROXY = "https://mvr-proxy.mihov-emil.workers.dev/scrape?url="
INSECURE = ssl._create_unverified_context()
SOFIA = timezone(timedelta(hours=3))
today = datetime.now(SOFIA)
tomorrow = today + timedelta(days=1)

def fetch(url):
    for target, ctx in ((url, None), (url, INSECURE),
                        (PROXY + quote(url, safe=""), None)):
        try:
            req = Request(target, headers=UA)
            with urlopen(req, timeout=30, context=ctx) as r:
                b = r.read()
            head = b[:3000].decode("ascii", "ignore").lower()
            if "1251" in head:
                return b.decode("cp1251", "ignore"), f"OK via {'proxy' if 'workers.dev' in target else 'direct'}"
            try:
                return b.decode("utf-8"), f"OK via {'proxy' if 'workers.dev' in target else 'direct'}"
            except UnicodeDecodeError:
                return b.decode("cp1251", "ignore"), "OK cp1251-fallback"
        except Exception as e:
            err = repr(e)
    return None, err

PAGES = {
    "theatre_day0": f"https://theatre.art.bg/театри-софия-програма______{today.year}-{today.month:02d}-{today.day}_",
    "theatre_home": "https://theatre.art.bg/",
    "gong_programa": "https://gong.bg/programa",
    "gong_home": "https://gong.bg/",
    "visitsofia_kalendar": "https://www.visitsofia.bg/bg/kalendar",
    "arena_programa": "https://arenaarmeecsofia.net/програма-арена-8888-софия/",
}

os.makedirs("debug", exist_ok=True)
report = []
for name, url in PAGES.items():
    body, status = fetch(url)
    if body is None:
        report.append(f"{name}: FAIL {status} | {url}")
        continue
    # режем скриптове/стилове за компактност, пазим структурата
    slim = re.sub(r"<script\b.*?</script>", "<!--script-->", body, flags=re.S | re.I)
    slim = re.sub(r"<style\b.*?</style>", "<!--style-->", slim, flags=re.S | re.I)
    slim = slim[:90000]
    with open(f"debug/{name}.html", "w", encoding="utf-8") as f:
        f.write(slim)
    report.append(f"{name}: {status} raw={len(body)}b slim={len(slim)}b | {url}")

with open("debug/report.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(report) + "\n")
print("\n".join(report))
