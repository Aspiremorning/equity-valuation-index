#!/usr/bin/env python3
"""
EVI Dashboard build engine — PMS AIF LEAPS(TM)
Reads the EVI 2025 daily dataset (Google Sheet CSV export or local CSV),
computes the 11-factor Equity Valuation Index, EPS growth analytics,
and renders a self-contained docs/index.html for GitHub Pages.

Data source resolution order:
  1. env SHEET_CSV_URL  (published Google Sheet CSV export URL)
  2. data/evi_data.csv  (local fallback / seed)
"""
import os, sys, json, csv, io, math, urllib.request
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_CSV = os.path.join(ROOT, "data", "evi_data.csv")
TEMPLATE = os.path.join(ROOT, "scripts", "template.html")
OUT_HTML = os.path.join(ROOT, "docs", "index.html")

# Canonical column order = columns A..AB of the "EVI 2025" sheet
COLS = ["sno","date","mcap_inr_cr","mcap_usd","usdinr","mcap_usd_tn","mcap_gdp",
        "beer","n50_ey","n50_eps","in10y","nifty50","pb","yield_gap","n50_pe",
        "us10y","in_us_spread","dxy","preity","tbill91","mid150","mid_pe",
        "mid_eps","mid_ey","small250","small_pe","small_eps","small_ey"]

NUMERIC = COLS[2:]

# ---- 11 prime factors: key, label, unit, direction (+1: high = expensive, -1: high = cheap)
# NOTE: Market Cap to GDP (both ₹ and $ rows) reads the sheet's own `mcap_gdp` column (col 7)
# directly — no recomputation. Because a MCap/GDP ratio is currency-neutral, both rows show
# the same maintained figure.
FACTORS = [
    ("n50_pe",        "P/E Ratio — Nifty 50",                "x",   +1),
    ("pb",            "P/B Ratio — Nifty 50",                "x",   +1),
    ("mcapgdp_inr",   "Market Cap to GDP",                   "%",   +1),
    ("n50_ey",        "Earnings Yield — Nifty 50",           "%",   -1),
    ("in10y",         "India 10-Year G-Sec Yield",           "%",   +1),
    ("beer",          "BEER Ratio (10Y ÷ Earnings Yield)",   "x",   +1),
    ("tbill91",       "91-Day T-Bill Yield",                 "%",   +1),
    ("preity",        "PREITY Ratio (P/E × 91-Day)",         "",    +1),
    ("yield_gap",     "Yield Gap (10Y − Earnings Yield)",    "pp",  +1),
    ("in_us_spread",  "India 10Y − US 10Y Spread",           "pp",  -1),
]

BANDS = [
    (0, 20,  "Deep Value",        "#1F6B4E"),
    (20, 40, "Value",             "#5C9A6F"),
    (40, 60, "Fair Value",        "#C8A24B"),
    (60, 80, "Expensive",         "#C2622E"),
    (80, 101,"Extreme Expensive", "#962B25"),
]

def parse_date(s):
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d-%b-%Y",
                "%Y-%m-%d %H:%M:%S", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unparseable date: {s!r}")

def to_float(v):
    if v is None: return None
    s = str(v).replace(",", "").replace("₹", "").strip()
    if s in ("", "-", "#N/A", "N/A", "NA", "#DIV/0!", "#REF!", "#VALUE!"): return None
    try: return float(s)
    except ValueError: return None

def load_rows():
    url = os.environ.get("SHEET_CSV_URL", "").strip()
    if url:
        print(f"Fetching Google Sheet: {url[:80]}...")
        with urllib.request.urlopen(url, timeout=60) as r:
            text = r.read().decode("utf-8-sig")
    else:
        print(f"Reading local CSV: {DATA_CSV}")
        with open(DATA_CSV, encoding="utf-8-sig") as f:
            text = f.read()
    reader = csv.reader(io.StringIO(text))
    raw = list(reader)
    start = 0
    for i, row in enumerate(raw[:5]):
        if any("date" in str(c).lower() for c in row):
            start = i + 1
            break
    rows = []
    for row in raw[start:]:
        if len(row) < 20 or not str(row[1]).strip():
            continue
        try:
            d = parse_date(row[1])
        except ValueError:
            continue
        rec = {"date": d}
        for j, key in enumerate(COLS[2:], start=2):
            rec[key] = to_float(row[j]) if j < len(row) else None
        rows.append(rec)
    rows.sort(key=lambda r: r["date"])
    dedup = {}
    for r in rows: dedup[r["date"]] = r
    rows = [dedup[k] for k in sorted(dedup)]
    ffill_cols = [c for c in NUMERIC if c not in ("yield_gap", "in_us_spread")]
    prev = {}
    for r in rows:
        for c in NUMERIC:
            v = r[c]
            bad = v is None or (c in ffill_cols and v == 0 and c not in
                  ("mid150","mid_pe","mid_eps","mid_ey","small250","small_pe","small_eps","small_ey"))
            if bad and c in prev:
                r[c] = prev[c]
            elif v is not None:
                prev[c] = v
    return rows

def percentile_ranks(values):
    pairs = sorted((v, i) for i, v in enumerate(values))
    n = len(values)
    out = [0.0] * n
    k = 0
    while k < n:
        j = k
        while j + 1 < n and pairs[j + 1][0] == pairs[k][0]:
            j += 1
        avg_rank = (k + j) / 2.0
        pct = 100.0 * avg_rank / (n - 1) if n > 1 else 50.0
        for m in range(k, j + 1):
            out[pairs[m][1]] = pct
        k = j + 1
    return out

def band_of(score):
    for lo, hi, name, color in BANDS:
        if lo <= score < hi:
            return name, color
    return BANDS[-1][2], BANDS[-1][3]

def cagr(latest, past, years):
    if not latest or not past or past <= 0 or latest <= 0:
        return None
    return (latest / past) ** (1.0 / years) - 1.0

def nearest_on_or_before(rows, target):
    lo, hi, best = 0, len(rows) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if rows[mid]["date"] <= target:
            best = mid; lo = mid + 1
        else:
            hi = mid - 1
    return best

def main():
    rows = load_rows()
    n = len(rows)
    print(f"{n} daily observations | {rows[0]['date']:%d-%b-%Y} → {rows[-1]['date']:%d-%b-%Y}")

    # ---- Market Cap to GDP: read the sheet's own `mcap_gdp` column (col 7) directly.
    #      Both ₹ and $ rows use this single maintained figure (ratio is currency-neutral).
    for r in rows:
        r["mcapgdp_inr"] = r["mcap_gdp"]

    # ---- Composite EVI: equal-weighted direction-adjusted percentile ranks
    pct = {}
    for key, label, unit, direction in FACTORS:
        vals = [r[key] for r in rows]
        ranks = percentile_ranks(vals)
        if direction < 0:
            ranks = [100.0 - x for x in ranks]
        pct[key] = ranks
    evi = [sum(pct[k][i] for k, *_ in FACTORS) / len(FACTORS) for i in range(n)]
    evi_pct = percentile_ranks(evi)

    evi_smooth = []
    for i in range(n):
        w = evi[max(0, i - 29):i + 1]
        evi_smooth.append(sum(w) / len(w))

    latest = rows[-1]
    cur_evi = evi[-1]
    cur_band, cur_color = band_of(cur_evi)
    evi_30d_ago = evi[max(0, n - 31)]

    band_share = {b[2]: 0 for b in BANDS}
    for v in evi:
        band_share[band_of(v)[0]] += 1
    band_share = {k: round(100.0 * v / n, 1) for k, v in band_share.items()}

    factor_meta = []
    for key, label, unit, direction in FACTORS:
        vals = [r[key] for r in rows if r[key] is not None]
        cur = latest[key]
        sv = sorted(vals)
        med = sv[len(sv)//2]
        factor_meta.append({
            "key": key, "label": label, "unit": unit,
            "direction": "high = expensive" if direction > 0 else "high = cheap",
            "current": round(cur, 2),
            "median": round(med, 2),
            "min": round(sv[0], 2), "max": round(sv[-1], 2),
            "pctl": round(pct[key][-1], 1),
        })

    # ======== Broad Market EVI: Large (Nifty 50) + Mid (150) + Small (250) ========
    # Base 10 factors reuse their full-history percentiles (pct[]). Midcap 150 PE and
    # Smallcap 250 PE are added, each ranked over its OWN reliable history from 31-Mar-2021.
    RELIABLE = datetime(2021, 3, 31)
    bstart = next((i for i, r in enumerate(rows) if r["date"] >= RELIABLE), None)

    def subset_pct(key):
        out = [None] * n
        idxs = [i for i in range(bstart, n) if rows[i][key] is not None and rows[i][key] > 0]
        vals = [rows[i][key] for i in idxs]
        pr = percentile_ranks(vals)
        for j, i in enumerate(idxs):
            out[i] = pr[j]
        return out

    mid_pct = subset_pct("mid_pe")
    small_pct = subset_pct("small_pe")
    base_keys = [k for k, *_ in FACTORS]  # the 10 large-cap/macro factors (already direction-adjusted)

    broad = [None] * n
    for i in range(bstart, n):
        comps = [pct[k][i] for k in base_keys]
        if mid_pct[i] is not None: comps.append(mid_pct[i])
        if small_pct[i] is not None: comps.append(small_pct[i])
        broad[i] = sum(comps) / len(comps)

    bvals = [broad[i] for i in range(bstart, n) if broad[i] is not None]
    cur_broad = broad[-1]
    broad_band, broad_color = band_of(cur_broad)
    broad_30 = broad[max(bstart, n - 31)]
    below = sum(1 for x in bvals if x < cur_broad); eq = sum(1 for x in bvals if x == cur_broad)
    broad_pctl = 100.0 * (below + eq / 2.0) / len(bvals)

    # decimated series + 30d smooth over the broad window
    broad_full_sm = []
    for i in range(bstart, n):
        w = [broad[j] for j in range(max(bstart, i - 29), i + 1) if broad[j] is not None]
        broad_full_sm.append(sum(w) / len(w))
    broad_series = [[rows[i]["date"].strftime("%Y-%m-%d"), round(broad[i], 2)]
                    for k, i in enumerate(range(bstart, n)) if k % 3 == 0 or i == n - 1]
    broad_smooth = [[rows[bstart + k]["date"].strftime("%Y-%m-%d"), round(v, 2)]
                    for k, v in enumerate(broad_full_sm) if k % 3 == 0 or k == len(broad_full_sm) - 1]

    # segment valuation snapshot (PE + its own-history percentile)
    seg = []
    for name, key, p in [("Nifty 50", "n50_pe", pct["n50_pe"][-1]),
                         ("Nifty Midcap 150", "mid_pe", mid_pct[-1]),
                         ("Nifty Smallcap 250", "small_pe", small_pct[-1])]:
        bn, _ = band_of(p)
        seg.append({"name": name, "pe": round(latest[key], 2), "pctl": round(p, 1), "band": bn})

    broad_payload = {
        "score": round(cur_broad, 1), "band": broad_band, "color": broad_color,
        "pctl": round(broad_pctl, 1), "delta30": round(cur_broad - broad_30, 1),
        "n_obs": len(bvals), "start": rows[bstart]["date"].strftime("%b %Y"),
        "large_score": round(cur_evi, 1),
        "series": broad_series, "smooth": broad_smooth, "segments": seg,
    }

    # ======== Pillar-Weighted EVI: 4 equal pillars, de-duplicated, whole market ========
    # Removes equal-weight multicollinearity AND broadens to the full cap spectrum. Each of
    # four themes gets 1/4, regardless of how many sub-metrics sit inside. Earnings Yield
    # (the exact reciprocal of P/E) is dropped as a pure duplicate. Base factors use their
    # direction-adjusted full-history percentiles (pct[]); the SMID pillar uses Midcap 150 and
    # Smallcap 250 P/E ranked over their reliable window (from 31-Mar-2021), so the composite
    # exists from that date onward.
    LABELS = {k: lbl for k, lbl, u, d in FACTORS}
    LABELS["mid_pe"] = "Midcap 150 P/E"
    LABELS["small_pe"] = "Smallcap 250 P/E"
    pct_lookup = dict(pct)
    pct_lookup["mid_pe"] = mid_pct
    pct_lookup["small_pe"] = small_pct
    PILLARS = [
        ("Absolute Valuation",     ["n50_pe", "pb", "mcapgdp_inr"]),
        ("Equity vs Bonds",        ["yield_gap", "beer", "preity"]),
        ("Rate Environment",       ["in10y", "tbill91", "in_us_spread"]),
        ("Market Breadth (SMID)",  ["mid_pe", "small_pe"]),
    ]
    pillar_vals = {}
    for pname, keys in PILLARS:
        arr = [None] * n
        for i in range(n):
            vs = [pct_lookup[k][i] for k in keys if pct_lookup[k][i] is not None]
            if len(vs) == len(keys):
                arr[i] = sum(vs) / len(vs)
        pillar_vals[pname] = arr
    pillar_evi = [None] * n
    for i in range(n):
        ps = [pillar_vals[p][i] for p, _ in PILLARS]
        if all(x is not None for x in ps):
            pillar_evi[i] = sum(ps) / len(ps)
    pstart = next((i for i in range(n) if pillar_evi[i] is not None), 0)

    cur_pillar = pillar_evi[-1]
    pillar_band, pillar_color = band_of(cur_pillar)
    pillar_30 = next((pillar_evi[j] for j in range(n - 31, n) if pillar_evi[j] is not None), cur_pillar)
    pvals = [pillar_evi[i] for i in range(pstart, n) if pillar_evi[i] is not None]
    below = sum(1 for x in pvals if x < cur_pillar); eq = sum(1 for x in pvals if x == cur_pillar)
    pillar_own = 100.0 * (below + eq / 2.0) / len(pvals)

    pillar_full_sm = []
    for i in range(pstart, n):
        w = [pillar_evi[j] for j in range(max(pstart, i - 29), i + 1) if pillar_evi[j] is not None]
        pillar_full_sm.append(sum(w) / len(w))

    pillar_detail = []
    for pname, keys in PILLARS:
        pv = pillar_vals[pname][-1]
        pb_band, _ = band_of(pv)
        pillar_detail.append({
            "name": pname, "score": round(pv, 1), "band": pb_band,
            "members": [{"label": LABELS[k], "pctl": round(pct_lookup[k][-1], 1)} for k in keys],
        })

    pillar_payload = {
        "score": round(cur_pillar, 1), "band": pillar_band, "color": pillar_color,
        "pctl": round(pillar_own, 1), "delta30": round(cur_pillar - pillar_30, 1),
        "equal_score": round(cur_evi, 1), "start": rows[pstart]["date"].strftime("%b %Y"),
        "n_obs": len(pvals),
        "pillars": pillar_detail,
        "series": [[rows[i]["date"].strftime("%Y-%m-%d"), round(pillar_evi[i], 2)]
                   for k, i in enumerate(range(pstart, n)) if k % 3 == 0 or i == n - 1],
        "smooth": [[rows[pstart + k]["date"].strftime("%Y-%m-%d"), round(v, 2)]
                   for k, v in enumerate(pillar_full_sm) if k % 3 == 0 or k == len(pillar_full_sm) - 1],
    }

    eps_defs = [("n50_eps", "Nifty 50"), ("mid_eps", "Nifty Midcap 150"), ("small_eps", "Nifty Smallcap 250")]
    eps_growth = []
    for key, name in eps_defs:
        latest_eps = latest[key]
        g = {"index": name, "latest": round(latest_eps, 1) if latest_eps else None}
        for yrs in (1, 3, 5, 7):
            idx = nearest_on_or_before(rows, latest["date"] - timedelta(days=int(365.25 * yrs)))
            past = rows[idx][key] if idx is not None else None
            c = cagr(latest_eps, past, yrs)
            g[f"y{yrs}"] = round(c * 100, 2) if c is not None else None
        eps_growth.append(g)

    def series(key, dec=5, start=0):
        pts = []
        for i in range(start, n):
            if (i - start) % dec == 0 or i == n - 1:
                v = rows[i][key]
                if v is not None:
                    pts.append([rows[i]["date"].strftime("%Y-%m-%d"), round(v, 3)])
        return pts

    mid_start = next((i for i, r in enumerate(rows) if (r["mid_eps"] or 0) > 0), 0)

    payload = {
        "asof": latest["date"].strftime("%d %b %Y"),
        "built": datetime.now().strftime("%d %b %Y, %H:%M UTC"),
        "n_obs": n,
        "span": f"{rows[0]['date']:%b %Y} – {rows[-1]['date']:%b %Y}",
        "evi": {
            "score": round(cur_evi, 1),
            "band": cur_band, "color": cur_color,
            "delta30": round(cur_evi - evi_30d_ago, 1),
            "pctl": round(evi_pct[-1], 1),
            "band_share": band_share,
            "series": [[rows[i]["date"].strftime("%Y-%m-%d"), round(evi[i], 2)]
                       for i in range(n) if i % 5 == 0 or i == n - 1],
            "smooth": [[rows[i]["date"].strftime("%Y-%m-%d"), round(evi_smooth[i], 2)]
                       for i in range(n) if i % 5 == 0 or i == n - 1],
        },
        "ribbon": [round(evi[i], 1) for i in range(0, n, max(1, n // 900))],
        "snapshot": {
            "nifty": latest["nifty50"], "pe": latest["n50_pe"], "pb": latest["pb"],
            "mcap_tn": round(latest["mcap_usd_tn"], 2), "in10y": latest["in10y"],
            "mid_pe": latest["mid_pe"], "small_pe": latest["small_pe"],
        },
        "factors": factor_meta,
        "factor_series": {key: series(key) for key, *_ in FACTORS},
        "eps_series": {
            "n50_eps": series("n50_eps"),
            "mid_eps": series("mid_eps", start=mid_start),
            "small_eps": series("small_eps", start=mid_start),
        },
        "eps_growth": eps_growth,
        "broad": broad_payload,
        "pillar": pillar_payload,
        "bands": [{"lo": b[0], "hi": min(b[1], 100), "name": b[2], "color": b[3]} for b in BANDS],
    }

    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    vendor = os.path.join(ROOT, "scripts", "vendor")
    with open(os.path.join(vendor, "chart.umd.js"), encoding="utf-8") as f:
        html = html.replace("/*__CHARTJS__*/", f.read())
    with open(os.path.join(vendor, "chartjs-adapter.min.js"), encoding="utf-8") as f:
        html = html.replace("/*__ADAPTER__*/", f.read())
    html = html.replace("/*__DATA__*/null", json.dumps(payload, separators=(",", ":")))
    os.makedirs(os.path.dirname(OUT_HTML), exist_ok=True)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Large-cap EVI = {cur_evi:.1f}  →  {cur_band}")
    for fm in factor_meta:
        print(f"  {fm['label']:<42} {fm['current']:>10}   pctl {fm['pctl']:>5}")
    print(f"Broad Market EVI = {cur_broad:.1f}  →  {broad_band}  (from {broad_payload['start']}, {len(bvals)} obs)")
    for s in seg:
        print(f"  {s['name']:<22} PE {s['pe']:>7}   pctl {s['pctl']:>5}  {s['band']}")
    print(f"Pillar-Weighted EVI = {cur_pillar:.1f}  →  {pillar_band}")
    for p in pillar_detail:
        print(f"  {p['name']:<20} {p['score']:>5}  {p['band']}")
    print(f"Wrote {OUT_HTML} ({os.path.getsize(OUT_HTML)//1024} KB)")

if __name__ == "__main__":
    main()
