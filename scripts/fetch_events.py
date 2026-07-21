# SEV — Sofia Events fetcher v1.5
# Хоризонт 180 дни; stopword филтър за заглавия ("купете билети от тук" и т.н.)
import json, re, sys, os, html, ssl
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.parse import quote, urlsplit, urlunsplit

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "Accept-Language": "bg,en;q=0.8", "Accept": "application/json, text/html;q=0.9,*/*;q=0.8"}
NOW = datetime.now(timezone.utc)
HORIZON = NOW + timedelta(days=180)
SUMMARY = []
PROXY = "https://mvr-proxy.mihov-emil.workers.dev/scrape?url="
CTX = ssl.create_default_context()
INSECURE = ssl._create_unverified_context()
HOST_MODE = {}

MONTHS = {"януари":1,"февруари":2,"март":3,"април":4,"май":5,"юни":6,
          "юли":7,"август":8,"септември":9,"октомври":10,"ноември":11,"декември":12}
BAD_TITLE = re.compile(r"билет|купи|купете|вижте|виж |програма|начало|още|повече|\bтук\b|цялата|scroll|cookie|меню",
                       re.I)

def log(msg):
    print(msg)
    SUMMARY.append(str(msg))

def flush():
    txt = f"run: {NOW.isoformat()}\n" + "\n".join(SUMMARY) + "\n"
    with open("last_run.log", "w", encoding="utf-8") as f:
        f.write(txt)
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write("### SEV fetch\n```\n" + txt + "```\n")

def enc(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, quote(p.path, safe="/%"), quote(p.query, safe="=&%"), ""))

def get(url, timeout=30):
    u = enc(url)
    host = urlsplit(u).netloc
    modes = [("direct", u, CTX), ("insecure", u, INSECURE),
             ("proxy", PROXY + quote(u, safe=""), CTX)]
    if host in HOST_MODE:
        modes.sort(key=lambda m: 0 if m[0] == HOST_MODE[host] else 1)
    last = None
    for tag, target, ctx in modes:
        try:
            req = Request(target, headers=UA)
            with urlopen(req, timeout=timeout, context=ctx) as r:
                body = r.read().decode("utf-8", "ignore")
            if host not in HOST_MODE:
                HOST_MODE[host] = tag
                if tag != "direct": log(f"  [{host} -> {tag}]")
            return body
        except Exception as e:
            last = e
    raise last

def load_venues():
    with open("venues.json", encoding="utf-8") as f:
        return json.load(f)

def match_venue(name, venues):
    low = (name or "").lower()
    for key, v in venues.items():
        if key in low:
            return v
    return None

def parse_dt(s):
    if not s: return None
    s = s.strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone(timedelta(hours=3)))
        return d
    except Exception:
        return None

# ---------- 1) EVENTIM public-api ----------
def fetch_eventim():
    out = []
    base = ("https://public-api.eventim.com/websearch/search/api/exploration/v2/productGroups"
            "?webId=web__eventim-bg&language=bg&retail_partner=EVE"
            "&city_names=%D0%A1%D0%BE%D1%84%D0%B8%D1%8F&sort=DateAsc&page={p}")
    for p in range(1, 6):
        try:
            body = get(base.format(p=p))
        except Exception as e:
            log(f"eventim page {p} HTTP fail: {e!r}"); break
        try:
            data = json.loads(body)
        except Exception as e:
            log(f"eventim page {p} JSON fail: {e!r} | body[:200]={body[:200]!r}"); break
        groups = data.get("productGroups") or []
        if p == 1:
            log(f"eventim keys: {sorted(data.keys())} groups: {len(groups)}")
            if groups:
                log(f"eventim g0 keys: {sorted(groups[0].keys())}")
        if not groups: break
        for g in groups:
            name = g.get("name") or ""
            prods = g.get("products") or []
            for pr in prods:
                ti = pr.get("typeAttributes", {}).get("liveEntertainment", {})
                start = parse_dt(pr.get("start") or ti.get("startDate") or g.get("startDate"))
                venue = (ti.get("location", {}) or {}).get("name") or g.get("venueName") or ""
                city = (ti.get("location", {}) or {}).get("city") or ""
                if city and "софия" not in city.lower() and "sofia" not in city.lower():
                    continue
                if start:
                    out.append({"name": name, "venue": venue, "start": start.isoformat(),
                                "url": pr.get("link") or g.get("link") or "",
                                "src": "eventim"})
            if not prods:
                start = parse_dt(g.get("startDate"))
                if start:
                    out.append({"name": name, "venue": g.get("venueName") or "",
                                "start": start.isoformat(), "url": g.get("link") or "",
                                "src": "eventim"})
    log(f"eventim: {len(out)}")
    return out

# ---------- обща HTML екстракция ----------
def extract_events(h, default_venue, src, default_hour=20):
    out = []
    for m in re.finditer(r"(\d{1,2})\.(\d{1,2})\.(\d{4})(?:[^<\d]{0,40}(\d{1,2}):(\d{2}))?", h):
        d, mo, y, hh, mm = m.groups()
        add_ev(out, d, mo, y, hh or default_hour, mm or 0,
               nearest_title(h, m.start()), default_venue, src)
    for m in re.finditer(r"(\d{1,2})\s+(януари|февруари|март|април|май|юни|юли|август|септември|октомври|ноември|декември)\s+(\d{4})", h, re.I):
        d, mon, y = m.groups()
        add_ev(out, d, MONTHS[mon.lower()], y, default_hour, 0,
               nearest_title(h, m.start()), default_venue, src)
    # формат без година: "27 юни" -> тази или следващата година (винаги напред)
    for m in re.finditer(r"(\d{1,2})\s+(януари|февруари|март|април|май|юни|юли|август|септември|октомври|ноември|декември)(?!\s+\d{4})", h, re.I):
        d, mon = m.groups()
        y = NOW.year
        try:
            cand = datetime(y, MONTHS[mon.lower()], int(d), tzinfo=timezone.utc)
            if cand < NOW - timedelta(days=2): y += 1
        except ValueError:
            continue
        add_ev(out, d, MONTHS[mon.lower()], y, default_hour, 0,
               nearest_title(h, m.start()), default_venue, src)
    seen, ded = set(), []
    for e in out:
        k = (e["name"].lower(), e["start"][:10])
        if k not in seen: seen.add(k); ded.append(e)
    for e in ded[:8]:
        log(f"  {src} sample: {e['start'][:16]} | {e['name'][:50]}")
    return ded

def nearest_title(h, pos):
    chunk = h[max(0, pos-1200):pos]
    cands = re.findall(r"<(?:h\d|a|strong|b)[^>]*>([^<]{4,120})<", chunk)
    for c in reversed(cands):
        t = html.unescape(c).strip()
        if len(t) >= 4 and not BAD_TITLE.search(t):
            return t
    return None

def add_ev(out, d, mo, y, hh, mm, title, venue, src):
    if not title: return
    try:
        dt = datetime(int(y), int(mo), int(d), int(hh), int(mm),
                      tzinfo=timezone(timedelta(hours=3)))
    except ValueError:
        return
    out.append({"name": title, "venue": venue, "start": dt.isoformat(),
                "url": "", "src": src})

# ---------- 2) НДК ----------
def fetch_ndk():
    h = None
    for url in ("https://www.ndk.bg/програма", "https://ndk.bg/програма", "https://www.ndk.bg/"):
        try:
            h = get(url); log(f"ndk src: {url} len={len(h)}"); break
        except Exception as e:
            log(f"ndk try fail: {url} {e!r}")
    if not h:
        log("ndk: 0"); return []
    out = extract_events(h, "НДК", "ndk", default_hour=19)
    log(f"ndk: {len(out)}")
    return out

# ---------- 3) АРЕНА ----------
def fetch_arena():
    h = None
    for url in ("https://arenaarmeecsofia.net/програма-арена-8888-софия/",
                "https://arenaarmeecsofia.net/"):
        try:
            h = get(url); log(f"arena src: {url} len={len(h)}"); break
        except Exception as e:
            log(f"arena try fail: {url} {e!r}")
    if not h:
        log("arena: 0"); return []
    out = extract_events(h, "Арена 8888 София", "arena", default_hour=20)
    log(f"arena: {len(out)}")
    return out

# ---------- MERGE + VALIDATE ----------
def main():
    venues = load_venues()
    raw = fetch_eventim() + fetch_ndk() + fetch_arena()
    ev, seen = [], set()
    rej_past = rej_fut = 0
    for e in raw:
        dt = parse_dt(e["start"])
        if not dt:
            continue
        if dt < NOW - timedelta(hours=12):
            rej_past += 1
            if rej_past <= 3: log(f"  rej past: {e['start'][:16]} | {e['name'][:40]}")
            continue
        if dt > HORIZON:
            rej_fut += 1
            continue
        v = match_venue(e["venue"] or e["name"], venues)
        item = {"name": e["name"][:120], "venue": v["n"] if v else (e["venue"] or "?"),
                "lat": v["lat"] if v else None, "lon": v["lon"] if v else None,
                "cap": v["cap"] if v else 600,
                "start": dt.isoformat(), "url": e.get("url",""), "src": e["src"]}
        k = (item["name"].lower()[:40], item["start"][:13])
        if k in seen: continue
        seen.add(k); ev.append(item)
    ev.sort(key=lambda x: x["start"])
    log(f"merge: {len(ev)} прието, {rej_past} минали, {rej_fut} след хоризонта")

    with_geo = [e for e in ev if e["lat"]]
    srcs = {e["src"] for e in ev}
    if len(with_geo) < 5:
        log(f"⚠️ VALIDATION FAIL: {len(ev)} общо, само {len(with_geo)} с гео. events.json НЕ се променя (legacy остава).")
        flush()
        sys.exit(0)

    out = {"generated": NOW.isoformat(), "count": len(ev),
           "sources_ok": sorted(srcs), "events": ev}
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    log(f"✅ OK: {len(ev)} събития ({len(with_geo)} с гео), източници: {sorted(srcs)}")
    flush()

if __name__ == "__main__":
    main()
