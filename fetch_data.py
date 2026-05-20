import json, datetime, time, os, urllib.request

FRED = os.environ["FRED_KEY"]

# ── YTD base levels (Jan 2 2026 closing prices) ───────────────────────────
YTD = {
    "^GSPC":  4793.0,
    "^IXIC":  16832.0,
    "^STOXX": 511.4,
    "^N225":  39894.0,
    "EEM":    38.50,
    "GC=F":   2625.0,
    "CL=F":   62.16,
}

def pct(a, b):
    if not b or b == 0: return 0.0
    return round((a - b) / b * 100, 2)

def sign(n): return 1 if n > 0 else (-1 if n < 0 else 0)
def bps(a, b): return round((a - b) * 100, 1)

def fmt_price(n, decimals=2):
    if n >= 10000: return f"{n:,.0f}"
    if n >= 1000:  return f"{n:,.2f}"
    return f"{n:,.{decimals}f}"

# ── yfinance via download ─────────────────────────────────────────────────
import yfinance as yf

def fetch_equity(symbol, name, unit, ccy):
    try:
        hist = yf.download(symbol, period="5d", interval="1d", progress=False, auto_adjust=True)
        if hist.empty or len(hist) < 2:
            raise ValueError("not enough data")
        close = float(hist["Close"].iloc[-1])
        prev  = float(hist["Close"].iloc[-2])
        daily = pct(close, prev)
        ytd   = pct(close, YTD[symbol])
        as_of = hist.index[-1].strftime("%-d %b %Y")
        return {
            "name": name, "unit": unit, "ccy": ccy,
            "close": fmt_price(close),
            "daily": f"{daily:+.2f}%",
            "ytd":   f"{ytd:+.1f}%",
            "dSign": sign(daily),
            "ySign": sign(ytd),
            "asOf":  as_of
        }
    except Exception as e:
        print(f"WARN {symbol}: {e}")
        return {
            "name": name, "unit": unit, "ccy": ccy,
            "close": "—", "daily": "—", "ytd": "—",
            "dSign": 0, "ySign": 0, "asOf": "—"
        }

# ── FRED yields ───────────────────────────────────────────────────────────
def fetch_fred(series, name, ytd_base):
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series}&sort_order=desc&limit=5"
           f"&api_key={FRED}&file_type=json")
    with urllib.request.urlopen(url, timeout=15) as r:
        obs = [o for o in json.loads(r.read())["observations"] if o["value"] != "."]
    cur  = float(obs[0]["value"])
    prev = float(obs[1]["value"])
    chg  = bps(cur, prev)
    ytd_chg = bps(cur, ytd_base)
    return {
        "name": name, "unit": "Yield %", "isBond": True,
        "close": f"{cur:.2f}%",
        "daily": f"{chg:+.1f} bps",
        "ytd":   f"{ytd_chg:+.1f} bps",
        "dSign": sign(chg),
        "ySign": sign(ytd_chg)
    }

# ── ECB BTP Italy yields ───────────────────────────────────────────────────
def fetch_ecb(maturity, name, ytd_base):
    url = (f"https://data-api.ecb.europa.eu/service/data/"
           f"YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_{maturity}"
           f"?format=jsondata&lastNObservations=2")
    with urllib.request.urlopen(url, timeout=15) as r:
        d = json.loads(r.read())
    vals = d["dataSets"][0]["series"]["0:0:0:0:0:0:0"]["observations"]
    keys = sorted(vals.keys(), key=int)
    cur  = float(vals[keys[-1]][0])
    prev = float(vals[keys[-2]][0])
    chg  = bps(cur, prev)
    ytd_chg = bps(cur, ytd_base)
    return {
        "name": name, "unit": "Yield %", "isBond": True,
        "close": f"{cur:.2f}%",
        "daily": f"{chg:+.1f} bps",
        "ytd":   f"{ytd_chg:+.1f} bps",
        "dSign": sign(chg),
        "ySign": sign(ytd_chg)
    }

# ── FETCH ALL ─────────────────────────────────────────────────────────────
equities = [
    fetch_equity("^GSPC",  "S&P 500",       "USD pts", "USD"),
    fetch_equity("^IXIC",  "Nasdaq",         "USD pts", "USD"),
    fetch_equity("^STOXX", "STOXX 600",      "EUR pts", "EUR"),
    fetch_equity("^N225",  "Nikkei 225",     "JPY pts", "JPY"),
    fetch_equity("EEM",    "MSCI EM",        "USD pts", "USD"),
]
commodities = [
    fetch_equity("GC=F",   "Gold",           "USD / oz",  "USD"),
    fetch_equity("CL=F",   "Crude Oil WTI",  "USD / bbl", "USD"),
]

bonds = []
for series, name, ytd_base in [
    ("TB1YR", "US Treasury 1Y",  4.64),
    ("GS10",  "US Treasury 10Y", 4.19),
]:
    try:
        bonds.append(fetch_fred(series, name, ytd_base))
        print(f"OK FRED {series}")
    except Exception as e:
        print(f"WARN FRED {series}: {e}")
        bonds.append({"name": name, "unit": "Yield %", "isBond": True,
                      "close": "—", "daily": "—", "ytd": "—", "dSign": 0, "ySign": 0})

for mat, name, ytd_base in [
    ("1Y",  "BTP Italy 1Y",  2.85),
    ("10Y", "BTP Italy 10Y", 3.50),
]:
    try:
        bonds.append(fetch_ecb(mat, name, ytd_base))
        print(f"OK ECB {mat}")
    except Exception as e:
        print(f"WARN ECB {mat}: {e}")
        bonds.append({"name": name, "unit": "Yield %", "isBond": True,
                      "close": "—", "daily": "—", "ytd": "—", "dSign": 0, "ySign": 0})

# use the most recent equity date as asOf
dates = [e["asOf"] for e in equities + commodities if e["asOf"] != "—"]
as_of = dates[0] if dates else datetime.datetime.utcnow().strftime("%-d %b %Y")

now = datetime.datetime.utcnow()
out = {
    "asOf": as_of,
    "updatedAt": now.strftime("%H:%M %d %b %Y UTC"),
    "sections": [
        {"label": "Equities",    "rows": equities},
        {"label": "Commodities", "rows": commodities},
        {"label": "Bond Yields", "rows": bonds},
    ]
}

with open("data.json", "w") as f:
    json.dump(out, f, indent=2)
print(f"✓ data.json written — asOf: {as_of}")
