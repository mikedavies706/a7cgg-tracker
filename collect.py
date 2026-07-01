#!/usr/bin/env python3
"""
Daily collector for tail A7-CGG (ICAO 06a1cc) — FIFA WC 2026 jet tracker.
Pulls raw ADS-B position traces from adsb.lol globe history, segments them into
flight legs, geocodes each endpoint to the nearest airport (OurAirports), and
writes data/a7cgg.json. Standard library only — no pip installs needed.
"""
import json, csv, math, gzip, io, urllib.request, datetime, os

ICAO   = "06a1cc"
REG    = "A7-CGG"
START  = datetime.date(2026, 6, 9)          # two days before kickoff
UA     = {"User-Agent": "a7cgg-tracker/1.0 (github action)"}

def get(url, timeout=45):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

# ---------- airports ----------
def load_airports():
    raw = get("https://davidmegginson.github.io/ourairports-data/airports.csv").decode("utf-8", "replace")
    out = []
    for row in csv.DictReader(io.StringIO(raw)):
        if row["type"] in ("closed", "heliport", "seaplane_base"):
            continue
        try:
            la = float(row["latitude_deg"]); lo = float(row["longitude_deg"])
        except ValueError:
            continue
        out.append({"lat": la, "lon": lo, "icao": row["ident"], "iata": row["iata_code"] or None,
                    "name": row["name"], "city": row["municipality"] or None, "type": row["type"]})
    return out

def hav(a, b, c, d):
    R = 6371.0; p1 = math.radians(a); p2 = math.radians(c)
    dp = math.radians(c - a); dl = math.radians(d - b)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(x))

BIG = {"large_airport", "medium_airport"}
def nearest(airports, lat, lon):
    cand = sorted(((hav(lat, lon, a["lat"], a["lon"]), a) for a in airports), key=lambda x: x[0])
    for d, a in cand:
        if d > 35: break
        if a["type"] in BIG: return _mk(a, d, d > 25)
    for d, a in cand:
        if d > 12: break
        return _mk(a, d, False)
    for d, a in cand:
        if a["type"] in BIG and d <= 90: return _mk(a, d, True)
    return None
def _mk(a, d, approx):
    return {"icao": a["icao"], "iata": a["iata"], "name": a["name"], "city": a["city"],
            "type": a["type"], "dist_km": round(d, 1), "approx": bool(approx),
            "lat": a["lat"], "lon": a["lon"]}

# ---------- traces ----------
def load_points():
    pts = []
    day = START
    today = datetime.datetime.now(datetime.UTC).date()
    while day <= today:
        url = f"https://adsb.lol/globe_history/{day.year}/{day.month:02d}/{day.day:02d}/traces/{ICAO[-2:]}/trace_full_{ICAO}.json"
        try:
            raw = get(url)
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            d = json.loads(raw)
            base = d["timestamp"]
            for e in d.get("trace", []):
                lat, lon, alt = e[1], e[2], e[3]
                if lat is None or lon is None: continue
                og = (alt == "ground")
                av = None if (alt is None or alt == "ground") else float(alt)
                pts.append((base + e[0], lat, lon, av, og))
        except Exception as ex:
            print(f"  {day}: no data ({ex})")
        day += datetime.timedelta(days=1)
    # adsb.lol's daily archive lags ~a day for the current date; the live trace
    # endpoint carries today's (and recent) flights, so pull it too and merge.
    try:
        raw = get(f"https://globe.adsb.lol/data/traces/{ICAO[-2:]}/trace_full_{ICAO}.json")
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        d = json.loads(raw); base = d["timestamp"]; n = 0
        for e in d.get("trace", []):
            lat, lon, alt = e[1], e[2], e[3]
            if lat is None or lon is None: continue
            av = None if (alt is None or alt == "ground") else float(alt)
            pts.append((base + e[0], lat, lon, av, alt == "ground")); n += 1
        print(f"  live trace: +{n} points")
    except Exception as ex:
        print(f"  live trace: none ({ex})")
    pts.sort(key=lambda x: x[0])
    dd, last = [], -1
    for p in pts:
        if p[0] - last >= 1: dd.append(p); last = p[0]
    return dd

def segment(pts):
    def airborne(p): return (not p[4]) and (p[3] is not None) and (p[3] > 300)
    GAP = 45 * 60
    legs = []; inflight = False; cur = None; last_ground = None
    for p in pts:
        if not inflight:
            if p[4]: last_ground = p
            if airborne(p):
                cur = {"dep_ts": p[0], "pts": [p], "maxalt": p[3] or 0,
                       "origin_pt": last_ground or p, "gap_end": False}
                inflight = True
        else:
            gap = p[0] - cur["pts"][-1][0]; cur["pts"].append(p)
            if p[3]: cur["maxalt"] = max(cur["maxalt"], p[3])
            if p[4]:
                cur["arr_ts"] = p[0]; cur["dest_pt"] = p; legs.append(cur)
                inflight = False; last_ground = p; cur = None; continue
            if gap > GAP:
                cur["arr_ts"] = cur["pts"][-2][0]; cur["dest_pt"] = cur["pts"][-2]; cur["gap_end"] = True
                legs.append(cur); inflight = False; last_ground = None; cur = None
                if p[4]: last_ground = p
    if inflight and cur:
        cur["arr_ts"] = cur["pts"][-1][0]; cur["dest_pt"] = cur["pts"][-1]; cur["gap_end"] = True; legs.append(cur)
    clean = []
    for lg in legs:
        dur = lg["arr_ts"] - lg["dep_ts"]; o = lg["origin_pt"]; de = lg["dest_pt"]
        if dur >= 360 and (hav(o[1], o[2], de[1], de[2]) >= 40 or lg["maxalt"] >= 8000):
            clean.append(lg)
    return clean

def downsample(pl, maxn=90):
    if len(pl) <= maxn: return [[round(p[1], 4), round(p[2], 4)] for p in pl]
    step = len(pl) / maxn; out = []; j = 0.0
    for _ in range(maxn): out.append(pl[int(j)]); j += step
    out.append(pl[-1]); return [[round(p[1], 4), round(p[2], 4)] for p in out]

def main():
    print("Loading airports…"); airports = load_airports()
    print("Loading traces…"); pts = load_points()
    print(f"{len(pts)} points"); clean = segment(pts)
    print(f"{len(clean)} legs")
    out = []
    for lg in clean:
        o = lg["origin_pt"]; de = lg["dest_pt"]
        oa = nearest(airports, o[1], o[2]); da = nearest(airports, de[1], de[2])
        out.append({"dep_ts": int(lg["dep_ts"]), "arr_ts": int(lg["arr_ts"]),
                    "origin": oa or {"name": "Unknown", "icao": None, "iata": None, "city": None, "lat": round(o[1], 3), "lon": round(o[2], 3), "approx": True},
                    "dest":   da or {"name": "Unknown", "icao": None, "iata": None, "city": None, "lat": round(de[1], 3), "lon": round(de[2], 3), "approx": True},
                    "o_ll": [round(o[1], 4), round(o[2], 4)], "d_ll": [round(de[1], 4), round(de[2], 4)],
                    "maxalt": int(lg["maxalt"]), "dist_km": round(hav(o[1], o[2], de[1], de[2]), 0),
                    "gap_end": lg["gap_end"], "path": downsample(lg["pts"], 90)})
    doc = {"reg": REG, "icao": ICAO, "type": "Gulfstream G650ER", "op": "Qatar Executive",
           "built": int(datetime.datetime.now(datetime.UTC).timestamp()),
           "first_ts": out[0]["dep_ts"] if out else None, "last_ts": out[-1]["arr_ts"] if out else None,
           "legs": out}
    os.makedirs("data", exist_ok=True)
    json.dump(doc, open("data/a7cgg.json", "w"), separators=(",", ":"))
    print(f"Wrote data/a7cgg.json — {len(out)} legs, {sum(l['dist_km'] for l in out):,.0f} km")

if __name__ == "__main__":
    main()
