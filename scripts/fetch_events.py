# SEV — Sofia Events fetcher v1.8
# bilet.bg: JSON миньор (__NEXT_DATA__/вградени данни) вместо HTML regex
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
BAD_TITLE = re.compile(r"билет|купи|купете|вижте|виж |програма|начало|още|повече|\bтук\b|цялата|scroll|cookie|меню|skip|content|детайли|начална|search|menu|вход|регистрац|facebook|instagram",
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

def get(url, timeout=30, retries=2):
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
                    body = r.read().decode("utf-8", "ignore")
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

# ---------- 1) EVENTIM (API v1 -> v2 -> HTML JSON-LD) ----------
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
            log(f"eventim api p{p} not JSON: {body[:120]!r}"); break
        items = data.get(list_key) or []
        if p == 1:
            log(f"eventim [{list_key}] items: {len(items)}")
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
            body = get(url)
        except Exception as e:
            log(f"eventim html p{page} fail: {e!r}"); break
        blocks = re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', body, re.S)
        if page == 1: log(f"eventim html: {len(body)}b, {len(blocks)} ld+json блока")
        found = 0
        for b in blocks:
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
    if not out:
        out = eventim_api(v2, "productGroups")
    if not out:
        out = eventim_html()
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
    base = "https://www.ndk.bg/"
    try:
        h = get(base); log(f"ndk src: {base} len={len(h)}")
    except Exception as e:
        log(f"ndk fail: {e!r}"); log("ndk: 0"); return []
    out = extract_events(h, "НДК", "ndk", default_hour=19)
    prog = re.search(r'href="([^"]*(?:програм|program|events|събития)[^"]*)"', h, re.I)
    if prog:
        purl = urljoin(base, html.unescape(prog.group(1)))
        try:
            ph = get(purl); log(f"ndk prog: {purl} len={len(ph)}")
            out += extract_events(ph, "НДК", "ndk", default_hour=19)
        except Exception as e:
            log(f"ndk prog fail: {purl} {e!r}")
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
            h = get(url); log(f"arena src: {url} len={len(h)}"); break
        except Exception as e:
            log(f"arena try fail: {url} {e!r}")
    if not h:
        log("arena: 0"); return []
    out = extract_events(h, "Арена 8888 София", "arena", default_hour=20)
    log(f"arena: {len(out)}")
    return out

# ---------- 4) BILET.BG (JSON миньор) ----------
def walk_json(node, found, depth=0):
    if depth > 14: return
    if isinstance(node, dict):
        keys = {k.lower(): k for k in node.keys()}
        name_k = next((keys[k] for k in ("name","title","event_name","eventname") if k in keys), None)
        date_k = next((keys[k] for k in ("startdate","start_date","start","date","event_date","datetime","start_time") if k in keys), None)
        if name_k and date_k:
            dt = parse_dt(node.get(date_k))
            nm = node.get(name_k)
            if dt and isinstance(nm, str) and len(nm) >= 4:
                venue = ""
                for vk in ("venue","place","hall","location","venue_name","place_name"):
                    if vk in keys:
                        v = node.get(keys[vk])
                        if isinstance(v, str): venue = v
                        elif isinstance(v, dict): venue = v.get("name") or v.get("title") or ""
                        break
                found.append({"name": strip_tags(nm), "venue": strip_tags(venue),
                              "start": dt.isoformat(), "url": "", "src": "bilet"})
        for v in node.values():
            walk_json(v, found, depth+1)
    elif isinstance(node, list):
        for v in node:
            walk_json(v, found, depth+1)

def fetch_bilet():
    out = []
    try:
        h = get("https://bilet.bg/")
        log(f"bilet src: bilet.bg len={len(h)} startDate-та в页: {h.count('startDate')}")
    except Exception as e:
        log(f"bilet fail: {e!r}"); log("bilet: 0"); return []
    # 1) JSON-LD
    for b in re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', h, re.S):
        try:
            data = json.loads(b)
        except Exception:
            continue
        walk_json(data, out)
    # 2) __NEXT_DATA__ / вградени state скриптове
    if not out:
        for m in re.finditer(r'<script[^>]*>\s*(\{.*?\})\s*</script>', h, re.S):
            b = m.group(1)
            if '"startDate"' not in b and '"start_date"' not in b and '"date"' not in b:
                continue
            try:
                data = json.loads(b)
            except Exception:
                continue
            walk_json(data, out)
    # 3) двойки name/startDate направо в суровия текст (какъвто и wrapper да има)
    if not out:
        for m in re.finditer(r'"name"\s*:\s*"([^"]{4,120})"[^{}\[\]]{0,600}?"start(?:D|_d)ate"\s*:\s*"([^"]+)"', h):
            nm, sd = m.groups()
            dt = parse_dt(sd)
            if dt:
                out.append({"name": strip_tags(nm.encode().decode("unicode_escape", "ignore")),
                            "venue": "", "start": dt.isoformat(), "url": "", "src": "bilet"})
        for m in re.finditer(r'"start(?:D|_d)ate"\s*:\s*"([^"]+)"[^{}\[\]]{0,600}?"name"\s*:\s*"([^"]{4,120})"', h):
            sd, nm = m.groups()
            dt = parse_dt(sd)
            if dt:
                out.append({"name": strip_tags(nm.encode().decode("unicode_escape", "ignore")),
                            "venue": "", "start": dt.isoformat(), "url": "", "src": "bilet"})
    seen, ded = set(), []
    for e in out:
        k = (e["name"].lower(), e["start"][:10])
        if k not in seen: seen.add(k); ded.append(e)
    for e in ded[:8]:
        log(f"  bilet sample: {e['start'][:16]} | {e['name'][:50]} @ {e['venue'][:30]}")
    log(f"bilet: {len(ded)}")
    return ded

# ---------- MERGE + VALIDATE ----------
def main():
    venues = load_venues()
    raw = fetch_eventim() + fetch_ndk() + fetch_arena() + fetch_bilet()
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
