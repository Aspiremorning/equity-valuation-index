# Equity Valuation Index Dashboard — PMS AIF LEAPS™

A self-contained, auto-updating valuation dashboard for Indian equities, published on
GitHub Pages and rebuilt daily from a Google Sheet.

**Composite EVI** = equal-weighted average of 11 prime factors, each expressed as a
direction-adjusted percentile rank against its full daily history (Mar 2003 →).
Bands: 0–20 Deep Value · 20–40 Value · 40–60 Fair Value · 60–80 Expensive ·
80–100 Extreme Expensive.

| # | Factor | Direction |
|---|--------|-----------|
| 1 | P/E Ratio (Nifty 50) | high = expensive |
| 2 | P/B Ratio (Nifty 50) | high = expensive |
| 3 | Market Cap to GDP — ₹ terms | high = expensive |
| 4 | Market Cap to GDP — $ terms | high = expensive |
| 5 | Earnings Yield | high = **cheap** (inverted) |
| 6 | India 10Y G-Sec Yield | high = expensive |
| 7 | BEER Ratio (10Y ÷ EY) | high = expensive |
| 8 | 91-Day T-Bill Yield | high = expensive |
| 9 | PREITY Ratio (P/E × 91-Day) | high = expensive |
| 10 | Yield Gap (10Y − EY) | high = expensive |
| 11 | India 10Y − US 10Y Spread | high = expensive |

Plus: EPS levels and 1Y/3Y/5Y/7Y EPS CAGR for Nifty 50, Midcap 150, Smallcap 250.

---

## One-time setup (≈10 minutes)

### 1. Google Sheet (your daily data home)
1. Create a Google Sheet and paste in the **EVI 2025** sheet from your workbook —
   same columns A–AB, same order, header in row 1. (Or import `data/evi_data.csv`,
   which is an exact extract.)
2. **File → Share → Publish to web** → select that sheet tab → format **CSV** → Publish.
3. Copy the published URL. It looks like:
   `https://docs.google.com/spreadsheets/d/e/2PACX-.../pub?gid=0&single=true&output=csv`

### 2. GitHub repository
1. Create repo (e.g. `equity-valuation-index`), push these files to `main`.
2. **Settings → Pages** → Source: *Deploy from a branch* → Branch `main`, folder `/docs`.
3. **Settings → Secrets and variables → Actions → Variables** → New variable:
   - Name: `SHEET_CSV_URL`
   - Value: the published CSV URL from step 1.3
4. **Settings → Actions → General** → Workflow permissions → *Read and write*.

Done. The site is live at `https://<username>.github.io/equity-valuation-index/`.

---

## Daily workflow (≈1 minute)

1. Open the Google Sheet (phone or laptop) and **add one row** — today's date and
   the same values you already maintain in Excel.
2. That's it. The GitHub Action runs every weekday at **6:00 PM IST**, pulls the
   sheet, recomputes the EVI, and republishes the page.

Want it refreshed *immediately*? GitHub → **Actions → Build EVI Dashboard →
Run workflow**. Or run `./update.sh` locally.

---

## Yearly maintenance

`data/gdp.csv` holds calendar-year GDP used for both Market-Cap-to-GDP series:

- `gdp_usd_bn` — nominal GDP in US$ billion (IMF / your DataSheet values).
- `gdp_inr_lakh_cr` — optional. If filled (MoSPI nominal GDP, ₹ Lakh Cr), the
  ₹-terms ratio uses it directly; if blank, ₹ GDP is derived as $GDP × that
  year's average USD/INR from your own data.

**2025 and 2026 are estimates — please verify and overwrite.** Add the new year's
row each January.

> Note: the ₹/$ MCap-GDP here is *year-matched* (each observation divided by its
> own year's GDP), unlike the workbook's fixed CY2024 anchor — so current readings
> (~107–110%) sit below the workbook's ~123%. The year-matched series is the
> analytically correct one for percentile ranking across 23 years.

## Repo layout

```
data/evi_data.csv      # seed extract of EVI 2025 sheet (fallback data source)
data/gdp.csv           # year-wise GDP table (edit yearly)
scripts/build.py       # computation + render engine
scripts/template.html  # dashboard design template
docs/index.html        # generated site (do not edit by hand)
.github/workflows/build.yml  # daily auto-build
update.sh              # manual rebuild
```

---

*Published by PMS AIF LEAPS™ for educational and informational purposes only.
Observation-only analytics — no investment advice, recommendations, ratings or
target prices. Past performance is not indicative of future results.*
