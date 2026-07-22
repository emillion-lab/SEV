# SEV — Sofia Events fetcher v2.2
# smart charset (cp1251 сайтове), dd.mm без година ограничено до 75 дни напред
import json, re, sys, os, html, ssl, time
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.parse import quote, urlsplit, urlunsplit, urljoin

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
BAD_TITLE = re.compile(r"билет|купи|купете|вижте|виж |програма|начало|още|повече|\bтук\b|цялата|scroll|cookie|меню|skip|content|детайли|начална|search|menu|вход|регистрац|facebook|instagram|афиш",
                       re.I)

FOOT_HOME = [("цска 1948", None),
             ("левски", "герена"), ("цска", "българска армия"),
             ("славия", "стадион славия"), ("локомотив сф", "стадион локомотив"),
             ("локомотив софия", "стадион локомотив"), ("българия", "васил левски")]

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

def smart_decode(b):
    head = b[:3000].decode("ascii", "ignore").lower()
    if "windows-1251" in head or "cp1251" in head or "charset=win" in head:
        return b.decode("cp1251", "ignore")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return b.decode("cp1251")
        except Exception:
            return b.decode("utf-8", "ignore")

def get(url, timeout=30, retries=2, min_len=0):
    u = enc(url)
    host = urlsplit(u).netloc
    modes = [("direct", u, CTX), ("insecure", u, INSECURE),
             ("proxy", PROXY + quote(u, safe=""), CTX)]
    if host in HOST_MODE:
        modes.sort(key=lambda m: 0 if m[0] == HOST_MODE[host] else 1)
    last = None
    for attempt in range(retries):
        for tag, target, ctx in modes:
            try:
                req = Request(target, headers=UA)
                with urlopen(req, timeout=timeout, context=ctx) as r:
                    body = smart_decode(r.read())
                if min_len and len(body) < min_len:
                    last = Exception(f"body too small: {len(body)}b"); continue
                if host not in HOST_MODE:
                    HOST_MODE[host] = tag
                    if tag != "direct": log(f"  [{host} -> {tag}]")
                return body
            except Exception as e:
                last = e
        time.sleep(2)
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
    s = str(s).strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone(timedelta(hours=3)))
        return d
    except Exception:
        return None

def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", s)).strip()

def future_year(d, mo, cap_days=75):
    # за дати без изрична година: най-близката бъдеща, но не по-далеч от cap_days
    y = NOW.year
    try:
        cand = datetime(y, mo, d, tzinfo=timezone.utc)
    except ValueError:
        return None
    if cand < NOW - timedelta(days=2):
        y += 1
        try:
            cand = datetime(y, mo, d, tzinfo=timezone.utc)
        except ValueError:
            return None
    if cand > NOW + timedelta(days=cap_days):
        return None
    return y

# ---------- 1) EVENTIM ----------
def eventim_api(url_tpl, list_key):
    out = []
    for p in range(1, 6):
        try:
            body = get(url_tpl.format(p=p), retries=1)
        except Exception as e:
            log(f"eventim api p{p} fail: {e!r}"); break
        try:
            data = json.loads(body)
        except Exception:
            break
        items = data.get(list_key) or []
        if not items: break
        for it in items:
            ti = (it.get("typeAttributes") or {}).get("liveEntertainment") or {}
            loc = ti.get("location") or {}
            name = it.get("name") or it.get("title") or ""
            start = parse_dt(it.get("start") or ti.get("startDate") or it.get("startDate"))
            city = loc.get("city") or ""
            if city and "софия" not in city.lower() and "sofia" not in city.lower():
                continue
            for pr in (it.get("products") or []):
                pti = (pr.get("typeAttributes") or {}).get("liveEntertainment") or {}
                ploc = pti.get("location") or {}
                pst = parse_dt(pr.get("start") or pti.get("startDate"))
                if pst:
                    out.append({"name": name, "venue": ploc.get("name") or loc.get("name") or "",
                                "start": pst.isoformat(), "url": pr.get("link") or "", "src": "eventim"})
            if start and not it.get("products"):
                out.append({"name": name, "venue": loc.get("name") or "",
                            "start": start.isoformat(), "url": it.get("link") or "", "src": "eventim"})
    return out

def eventim_html():
    out = []
    for page in range(1, 4):
        url = "https://www.eventim.bg/city/%D1%81%D0%BE%D1%84%D0%B8%D1%8F-7510/"
        if page > 1: url += f"?page={page}"
        try:
            body = get(url, min_len=5000)
        except Exception as e:
            log(f"eventim html p{page} fail: {e!r}"); break
        found = 0
        for b in re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', body, re.S):
            try:
                data = json.loads(b)
            except Exception:
                continue
            items = data if isinstance(data, list) else data.get("@graph", [data])
            for it in items:
                if not isinstance(it, dict): continue
                if "Event" not in str(it.get("@type", "")): continue
                loc = it.get("location") or {}
                if isinstance(loc, list): loc = loc[0] if loc else {}
                start = parse_dt(it.get("startDate"))
                if not start: continue
                out.append({"name": strip_tags(str(it.get("name",""))),
                            "venue": (loc.get("name") or ""),
                            "start": start.isoformat(),
                            "url": it.get("url") or "", "src": "eventim"})
                found += 1
        if not found: break
    return out

def fetch_eventim():
    v1 = ("https://public-api.eventim.com/websearch/search/api/exploration/v1/products"
          "?webId=web__eventim-bg&language=bg&retail_partner=EVE"
          "&city_names=%D0%A1%D0%BE%D1%84%D0%B8%D1%8F&sort=DateAsc&page={p}")
    v2 = ("https://public-api.eventim.com/websearch/search/api/exploration/v2/productGroups"
          "?webId=web__eventim-bg&language=bg&retail_partner=EVE"
          "&city_names=%D0%A1%D0%BE%D1%84%D0%B8%D1%8F&sort=DateAsc&page={p}")
    out = eventim_api(v1, "products")
    if not out: out = eventim_api(v2, "productGroups")
    if not out: out = eventim_html()
    log(f"eventim: {len(out)}")
    return out

# ---------- обща HTML екстракция ----------
def extract_events(h, default_venue, src, default_hour=20):
    out = []
    stats = [0, 0, 0, 0]
    for m in re.finditer(r"(\d{1,2})\.(\d{1,2})\.(\d{4})(?:[^<\d]{0,40}(\d{1,2}):(\d{2}))?", h):
        d, mo, y, hh, mm = m.groups()
        stats[0] += 1
        add_ev(out, d, mo, y, hh or default_hour, mm or 0,
               nearest_title(h, m.start()), default_venue, src)
    for m in re.finditer(r"(?<![\d.])(\d{1,2})\.(\d{1,2})(?!\.?\d)(?:[^<\d]{0,40}(\d{1,2}):(\d{2}))?", h):
        d, mo, hh, mm = m.groups()
        d, mo = int(d), int(mo)
        if not (1 <= mo <= 12 and 1 <= d <= 31): continue
        stats[1] += 1
        y = future_year(d, mo)
        if not y: continue
        add_ev(out, d, mo, y, hh or default_hour, mm or 0,
               nearest_title(h, m.start()), default_venue, src)
    for m in re.finditer(r"(\d{1,2})\s+(януари|февруари|март|април|май|юни|юли|август|септември|октомври|ноември|декември)\s+(\d{4})", h, re.I):
        d, mon, y = m.groups()
        stats[2] += 1
        add_ev(out, d, MONTHS[mon.lower()], y, default_hour, 0,
               nearest_title(h, m.start()), default_venue, src)
    for m in re.finditer(r"(\d{1,2})\s+(януари|февруари|март|април|май|юни|юли|август|септември|октомври|ноември|декември)(?!\s+\d{4})", h, re.I):
        d, mon = m.groups()
        stats[3] += 1
        y = future_year(int(d), MONTHS[mon.lower()])
        if not y: continue
        add_ev(out, d, MONTHS[mon.lower()], y, default_hour, 0,
               nearest_title(h, m.start()), default_venue, src)
    seen, ded = set(), []
    for e in out:
        k = (e["name"].lower(), e["start"][:10])
        if k not in seen: seen.add(k); ded.append(e)
    for e in ded[:2]:
        log(f"  {src}: {e['start'][:16]} | {e['name'][:45]}")
    if not ded and len(h) > 5000:
        log(f"  {src} diag: pattern hits {stats}, 0 заглавия оцеляха")
    return ded

def nearest_title(h, pos):
    chunk = h[max(0, pos-1200):pos]
    cands = re.findall(r"<(?:h\d|a|strong|b|span|div)[^>]*>([^<]{4,120})<", chunk)
    for c in reversed(cands):
        t = html.unescape(c).strip()
        if len(t) >= 4 and not BAD_TITLE.search(t) and not re.fullmatch(r"[\d\s:.\-–/]+", t):
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
    base = "https://www.ndk.bg/"
    try:
        h = get(base, min_len=5000)
    except Exception as e:
        log(f"ndk fail: {e!r}"); log("ndk: 0"); return []
    out = extract_events(h, "НДК", "ndk", default_hour=19)
    prog = re.search(r'href="([^"]*(?:програм|program|events|събития)[^"]*)"', h, re.I)
    if prog:
        purl = urljoin(base, html.unescape(prog.group(1)))
        try:
            ph = get(purl, min_len=5000)
            out += extract_events(ph, "НДК", "ndk", default_hour=19)
        except Exception as e:
            log(f"ndk prog fail: {e!r}")
    seen, ded = set(), []
    for e in out:
        k = (e["name"].lower(), e["start"][:10])
        if k not in seen: seen.add(k); ded.append(e)
    log(f"ndk: {len(ded)}")
    return ded

# ---------- 3) АРЕНА ----------
def fetch_arena():
    h = None
    for url in ("https://arenaarmeecsofia.net/програма-арена-8888-софия/",
                "https://arenaarmeecsofia.net/"):
        try:
            h = get(url, min_len=5000); break
        except Exception as e:
            log(f"arena try fail: {e!r}")
    if not h:
        log("arena: 0"); return []
    out = extract_events(h, "Арена 8888 София", "arena", default_hour=20)
    log(f"arena: {len(out)}")
    return out

# ---------- 4) THEATRE.ART.BG ----------
def fetch_theatre():
    base = "https://theatre.art.bg/"
    try:
        h = get(base, min_len=5000); log(f"theatre src len={len(h)}")
    except Exception as e:
        log(f"theatre fail: {e!r}"); log("theatre: 0"); return []
    out = extract_events(h, "", "theatre", default_hour=19)
    prog = re.search(r'href="([^"]*(?:афиш|afish|програм|program)[^"]*)"', h, re.I)
    if prog:
        purl = urljoin(base, html.unescape(prog.group(1)))
        try:
            ph = get(purl, min_len=5000); log(f"theatre prog: {purl[:60]} len={len(ph)}")
            out += extract_events(ph, "", "theatre", default_hour=19)
        except Exception as e:
            log(f"theatre prog fail: {e!r}")
    seen, ded = set(), []
    for e in out:
        k = (e["name"].lower(), e["start"][:10])
        if k not in seen: seen.add(k); ded.append(e)
    log(f"theatre: {len(ded)}")
    return ded

# ---------- 5) ФУТБОЛ (bgfutbol.com) ----------
def fetch_football():
    out = []
    h = None
    for url in ("https://www.bgfutbol.com/programa.php", "https://www.bgfutbol.com/",
                "https://bgfutbol.com/"):
        try:
            h = get(url, min_len=5000); log(f"футбол src: {url} len={len(h)}"); break
        except Exception as e:
            log(f"футбол try fail: {url.split('/')[-1] or 'home'} {e!r}")
    if not h:
        log("футбол: 0"); return []
    cyr = len(re.findall(r"[А-Яа-я]", h[:20000]))
    log(f"  футбол кирилица в първите 20K: {cyr}")
    for m in re.finditer(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?", h):
        d, mo, y = m.groups()
        d, mo = int(d), int(mo)
        if not (1 <= mo <= 12 and 1 <= d <= 31): continue
        yy = int(y) if y else future_year(d, mo)
        if not yy: continue
        window = strip_tags(h[m.end():m.end()+500])
        tm = re.search(r"(\d{1,2}):(\d{2})", window)
        hh, mm2 = (int(tm.group(1)), int(tm.group(2))) if tm else (18, 0)
        pair = re.search(r"([А-Я][А-Яа-я0-9\.\s]{2,24}?)\s*[-–]\s*([А-Я][А-Яа-я0-9\.\s]{2,24})", window)
        if not pair: continue
        home, away = pair.group(1).strip(), pair.group(2).strip()
        hl = home.lower()
        venue_key = None
        for team, vk in FOOT_HOME:
            if team in hl:
                venue_key = vk; break
        if venue_key is None: continue
        try:
            dt = datetime(yy, mo, d, hh, mm2, tzinfo=timezone(timedelta(hours=3)))
        except ValueError:
            continue
        out.append({"name": f"⚽ {home} – {away}", "venue": venue_key,
                    "start": dt.isoformat(), "url": "", "src": "футбол"})
    seen, ded = set(), []
    for e in out:
        k = (e["name"].lower(), e["start"][:10])
        if k not in seen: seen.add(k); ded.append(e)
    for e in ded[:6]:
        log(f"  футбол sample: {e['start'][:16]} | {e['name'][:50]}")
    log(f"футбол: {len(ded)}")
    return ded

# ---------- 6) ЛОКАЛНИ (visitsofia.bg) ----------
def fetch_local():
    out = []
    h = None
    for url in ("https://www.visitsofia.bg/bg/kalendar", "https://www.visitsofia.bg/bg/events",
                "https://www.visitsofia.bg/"):
        try:
            h = get(url, min_len=5000); log(f"локални src: {url} len={len(h)}"); break
        except Exception as e:
            log(f"локални try fail: {e!r}")
    if not h:
        log("локални: 0"); return []
    out = extract_events(h, "", "локални", default_hour=18)
    if len(out) < 3:
        prog = re.search(r'href="([^"]*(?:kalendar|събити|events)[^"]*)"', h, re.I)
        if prog:
            purl = urljoin("https://www.visitsofia.bg/", html.unescape(prog.group(1)))
            try:
                ph = get(purl, min_len=5000); log(f"локални prog: {purl[:60]} len={len(ph)}")
                out += extract_events(ph, "", "локални", default_hour=18)
            except Exception as e:
                log(f"локални prog fail: {e!r}")
    seen, ded = set(), []
    for e in out:
        k = (e["name"].lower(), e["start"][:10])
        if k not in seen: seen.add(k); ded.append(e)
    log(f"локални: {len(ded)}")
    return ded

# ---------- MERGE + VALIDATE ----------
def main():
    venues = load_venues()
    raw = (fetch_eventim() + fetch_ndk() + fetch_arena()
           + fetch_theatre() + fetch_football() + fetch_local())
    ev, seen = [], set()
    rej_past = rej_fut = 0
    for e in raw:
        dt = parse_dt(e["start"])
        if not dt:
            continue
        if dt < NOW - timedelta(hours=12):
            rej_past += 1; continue
        if dt > HORIZON:
            rej_fut += 1; continue
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
