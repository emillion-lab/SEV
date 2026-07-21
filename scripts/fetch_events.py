# SEV — Sofia Events fetcher v1.2
# Логът се записва и в last_run.log (commit-ва се в репото за дистанционна диагностика)
import json, re, sys, os, html
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "Accept-Language": "bg,en;q=0.8", "Accept": "application/json, text/html;q=0.9,*/*;q=0.8"}
NOW = datetime.now(timezone.utc)
HORIZON = NOW + timedelta(days=60)
SUMMARY = []

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

def get(url, timeout=30):
    req = Request(url, headers=UA)
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")

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

# ---------- 2) НДК ----------
def fetch_ndk():
    out = []
    h = None
    for url in ("https://www.ndk.bg/програма", "https://ndk.bg/програма", "https://www.ndk.bg/"):
        try:
            h = get(url); log(f"ndk src: {url} len={len(h)}"); break
        except Exception as e:
            log(f"ndk try fail: {url} {e!r}")
    if not h:
        log("ndk: 0"); return out
    for m in re.finditer(r"(\d{1,2})\.(\d{1,2})\.(\d{4})[^<]{0,80}?(?:(\d{1,2}):(\d{2}))?.{0,600}?<a[^>]*>([^<]{4,120})</a>", h, re.S):
        d, mo, y, hh, mm, title = m.groups()
        try:
            dt = datetime(int(y), int(mo), int(d), int(hh or 19), int(mm or 0),
                          tzinfo=timezone(timedelta(hours=3)))
        except ValueError:
            continue
        title = html.unescape(title).strip()
        if len(title) < 4 or title.lower() in ("програма","билети","още"): continue
        out.append({"name": title, "venue": "НДК", "start": dt.isoformat(),
                    "url": "https://www.ndk.bg", "src": "ndk"})
    seen, ded = set(), []
    for e in out:
        k = (e["name"].lower(), e["start"][:10])
        if k not in seen: seen.add(k); ded.append(e)
    log(f"ndk: {len(ded)}")
    return ded

# ---------- 3) АРЕНА СОФИЯ ----------
def fetch_arena():
    out = []
    h = None
    for url in ("https://www.arenasofia.bg/събития/", "https://www.arenasofia.bg/events/",
                "https://arenasofia.bg/"):
        try:
            h = get(url); log(f"arena src: {url} len={len(h)}"); break
        except Exception as e:
            log(f"arena try fail: {url} {e!r}")
    if not h:
        log("arena: 0"); return out
    for m in re.finditer(r"(\d{1,2})\.(\d{1,2})\.(\d{4})[^<]{0,120}?.{0,600}?<(?:h\d|a)[^>]*>([^<]{4,120})</", h, re.S):
        d, mo, y, title = m.groups()
        try:
            dt = datetime(int(y), int(mo), int(d), 20, 0, tzinfo=timezone(timedelta(hours=3)))
        except ValueError:
            continue
        title = html.unescape(title).strip()
        if len(title) < 4: continue
        out.append({"name": title, "venue": "Арена 8888 София", "start": dt.isoformat(),
                    "url": "https://www.arenasofia.bg", "src": "arena"})
    seen, ded = set(), []
    for e in out:
        k = (e["name"].lower(), e["start"][:10])
        if k not in seen: seen.add(k); ded.append(e)
    log(f"arena: {len(ded)}")
    return ded

# ---------- MERGE + VALIDATE ----------
def main():
    venues = load_venues()
    raw = fetch_eventim() + fetch_ndk() + fetch_arena()
    ev, seen = [], set()
    for e in raw:
        dt = parse_dt(e["start"])
        if not dt or dt < NOW - timedelta(hours=12) or dt > HORIZON:
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
