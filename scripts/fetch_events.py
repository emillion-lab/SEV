# SEV — Sofia Events fetcher
# Източници: Eventim public-api (JSON), НДК (HTML), Арена София (HTML)
# Защита: ако новите данни не минат валидация -> events.json НЕ се пипа (legacy остава)
import json, re, sys, html
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "Accept-Language": "bg,en;q=0.8"}
NOW = datetime.now(timezone.utc)
HORIZON = NOW + timedelta(days=60)

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
    # приема ISO с/без tz, "2026-08-01T20:00:00+03:00" и т.н.
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
            data = json.loads(get(base.format(p=p)))
        except Exception as e:
            print("eventim page", p, "fail:", e); break
        groups = data.get("productGroups") or []
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
    print("eventim:", len(out))
    return out

# ---------- 2) НДК ----------
def fetch_ndk():
    out = []
    try:
        h = get("https://www.ndk.bg/програма")
    except Exception:
        try:
            h = get("https://ndk.bg/програма")
        except Exception as e:
            print("ndk fail:", e); return out
    # търсим блокове с дата (дд.мм.гггг) и заглавие наблизо
    months = {"януари":1,"февруари":2,"март":3,"април":4,"май":5,"юни":6,
              "юли":7,"август":8,"септември":9,"октомври":10,"ноември":11,"декември":12}
    # шаблон 1: 01.08.2026 [час 20:00] ... <a>Заглавие</a>
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
    # дедупликация по (title, date)
    seen, ded = set(), []
    for e in out:
        k = (e["name"].lower(), e["start"][:10])
        if k not in seen: seen.add(k); ded.append(e)
    print("ndk:", len(ded))
    return ded

# ---------- 3) АРЕНА СОФИЯ ----------
def fetch_arena():
    out = []
    for url in ("https://www.arenasofia.bg/събития/", "https://www.arenasofia.bg/events/",
                "https://arenasofia.bg/"):
        try:
            h = get(url); break
        except Exception as e:
            print("arena try fail:", url, e); h = None
    if not h:
        return out
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
    print("arena:", len(ded))
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

    # ВАЛИДАЦИЯ: минимум 5 събития с координати, поне 1 източник жив
    with_geo = [e for e in ev if e["lat"]]
    srcs = {e["src"] for e in ev}
    if len(with_geo) < 5:
        print(f"VALIDATION FAIL: само {len(with_geo)} гео-събития. events.json НЕ се променя (legacy остава).")
        sys.exit(0)

    out = {"generated": NOW.isoformat(), "count": len(ev),
           "sources_ok": sorted(srcs), "events": ev}
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"OK: {len(ev)} събития ({len(with_geo)} с гео), източници: {srcs}")

if __name__ == "__main__":
    main()
