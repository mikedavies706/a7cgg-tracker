#!/usr/bin/env python3
"""
WC26 Stars news collector — stdlib only (mirrors the a7cgg jet-tracker pattern).

Runs on GitHub Actions (server-side, so no CORS concerns). Queries Google News RSS
per marquee player, parses the top headlines, dedupes, and writes data/stars_news.json.
The hub reads that file from raw.githubusercontent (CORS-open) and shows the latest
1-2 headlines on each star card. We store only title + source + url + timestamp
(short factual headlines; full article is a click away) to stay clean on copyright.
"""
import json, re, sys, time, urllib.request, urllib.parse, unicodedata
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

UA = "Mozilla/5.0 (wc26-stars-news collector; +https://github.com/)"
ITEMS_PER_PLAYER = 3
TIMEOUT = 20

# Marquee list. `key` MUST match the hub's normStar(feed name) so news attaches to the
# right star card. `q` is the Google News search. Keep names aligned to FIFA feed spelling.
STARS = [
    ("lionel messi",      "Lionel Messi",       "Argentina",   '"Lionel Messi" World Cup'),
    ("cristiano ronaldo", "Cristiano Ronaldo",  "Portugal",    '"Cristiano Ronaldo" World Cup'),
    ("kylian mbappe",     "Kylian Mbappé",      "France",      '"Kylian Mbappe" World Cup'),
    ("erling haaland",    "Erling Haaland",     "Norway",      '"Erling Haaland" World Cup'),
    ("harry kane",        "Harry Kane",         "England",     '"Harry Kane" World Cup'),
    ("christian pulisic", "Christian Pulisic",  "USA",         '"Christian Pulisic" World Cup'),
    ("alphonso davies",   "Alphonso Davies",    "Canada",      '"Alphonso Davies" World Cup'),
    ("vinicius junior",   "Vinícius Júnior",    "Brazil",      '"Vinicius Junior" World Cup'),
    ("jude bellingham",   "Jude Bellingham",    "England",     '"Jude Bellingham" World Cup'),
    ("lamine yamal",      "Lamine Yamal",       "Spain",       '"Lamine Yamal" World Cup'),
    ("lautaro martinez",  "Lautaro Martínez",   "Argentina",   '"Lautaro Martinez" World Cup'),
    ("julian alvarez",    "Julián Álvarez",     "Argentina",   '"Julian Alvarez" World Cup'),
    ("kevin de bruyne",   "Kevin De Bruyne",    "Belgium",     '"Kevin De Bruyne" World Cup'),
    ("luka modric",       "Luka Modrić",        "Croatia",     '"Luka Modric" World Cup'),
    ("jamal musiala",     "Jamal Musiala",      "Germany",     '"Jamal Musiala" World Cup'),
    ("florian wirtz",     "Florian Wirtz",      "Germany",     '"Florian Wirtz" World Cup'),
    ("ousmane dembele",   "Ousmane Dembélé",    "France",      '"Ousmane Dembele" World Cup'),
    ("cody gakpo",        "Cody Gakpo",         "Netherlands", '"Cody Gakpo" World Cup'),
    ("bukayo saka",       "Bukayo Saka",        "England",     '"Bukayo Saka" World Cup'),
    ("achraf hakimi",     "Achraf Hakimi",      "Morocco",     '"Achraf Hakimi" World Cup'),
]

def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.lower()).strip()

def gnews(q):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()

def iso(pubdate):
    try:
        return parsedate_to_datetime(pubdate).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None

def parse(xmlb, n):
    root = ET.fromstring(xmlb)
    out, seen = [], set()
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        src_el = it.find("source")
        source = (src_el.text.strip() if src_el is not None and src_el.text else "")
        m = re.match(r"^(.*)\s+-\s+([^-]+)$", title)   # Google appends " - Source"
        if m and not source:
            title, source = m.group(1).strip(), m.group(2).strip()
        k = norm(title)
        if not title or k in seen:
            continue
        seen.add(k)
        out.append({"title": title, "source": source, "url": link, "published": iso(pub)})
        if len(out) >= n:
            break
    return out

def main():
    players = {}
    for key, name, team, q in STARS:
        try:
            items = parse(gnews(q), ITEMS_PER_PLAYER)
            if items:
                players[key] = {"name": name, "team": team, "items": items}
            print(f"  {name:20s} {len(items)} items", file=sys.stderr)
        except Exception as e:
            print(f"  {name:20s} ERR {e}", file=sys.stderr)
        time.sleep(0.6)  # be polite to the feed
    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Google News RSS",
        "players": players,
    }
    with open("data/stars_news.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote data/stars_news.json — {len(players)} players", file=sys.stderr)

if __name__ == "__main__":
    main()
