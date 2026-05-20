import json, datetime, os, urllib.request
import yfinance as yf
import pandas as pd
 
FRED = os.environ["FRED_KEY"]
 
def pct(a, b):
    if not b: return 0.0
    return round((a - b) / b * 100, 2)
 
def sign(n): return 1 if n > 0 else (-1 if n < 0 else 0)
def bps(a, b): return round((a - b) * 100, 1)
 
def fmt_price(n):
    if n >= 10000: return f"{n:,.0f}"
    return f"{n:,.2f}"
 
def get_hist(symbol, start, end):
    hist = yf.download(symbol, start=start, end=end,
                       interval="1d", progress=False, auto_adjust=True)
    if isinstance(hist.columns, pd.MultiIndex):
        hist.columns = hist.columns.get_level_values(0)
    return hist
 
def fetch_price(symbol, name, unit):
    try:
        # get last 14 days for daily change
        end   = datetime.date.today()
        start = end - datetime.timedelta(days=14)
        hist  = get_hist(symbol, start, end)
        if hist.empty or len(hist) < 2:
            raise ValueError("not enough rows")
 
        close = float(hist["Close"].iloc[-1])
        prev  = float(hist["Close"].iloc[-2])
        if close == 0: raise ValueError("zero price")
        daily = pct(close, prev)
        as_of = hist.index[-1].strftime("%-d %b %Y")
 
        # get Jan 2 2026 price for YTD
        ytd_hist = get_hist(symbol,
                            datetime.date(2026, 1, 2),
                            datetime.date(2026, 1, 10))
        if ytd_hist.empty:
            raise ValueError("no YTD base data")
        ytd_base = float(ytd_hist["Close"].iloc[0])
        ytd = pct(close, ytd_base)
 
        print(f"OK {symbol}: close={close:.2f} prev={prev:.2f} ytd_base={ytd_base:.2f} ytd={ytd:+.1f}%")
        return {
            "name": name, "unit": unit,
            "close": fmt_price(close),
            "daily": f"{daily:+.2f}%",
            "ytd":   f"{ytd:+.1f}%",
            "dSign": sign(daily), "ySign": sign(ytd),
            "asOf":  as_of
        }
    except Exception as e:
        print(f"WARN {symbol}: {e}")
        return {"name": name, "unit": unit,
                "close": "—", "daily": "—", "ytd": "—",
                "dSign": 0, "ySign": 0, "asOf": "—"}
 
def fetch_fx(symbol, name, unit):
    """FX rates — show as rate and daily change only, no YTD needed"""
    try:
        end   = datetime.date.today()
        start = end - datetime.timedelta(days=14)
        hist  = get_hist(symbol, start, end)
        if hist.empty or len(hist) < 2:
            raise ValueError("not enough rows")
        close = float(hist["Close"].iloc[-1])
        prev  = float(hist["Close"].iloc[-2])
        if close == 0: raise ValueError("zero")
        daily = pct(close, prev)
        as_of = hist.index[-1].strftime("%-d %b %Y")
 
        # YTD for FX
        ytd_hist = get_hist(symbol,
                            datetime.date(2026, 1, 2),
                            datetime.date(2026, 1, 10))
        ytd_base = float(ytd_hist["Close"].iloc[0]) if not ytd_hist.empty else close
        ytd = pct(close, ytd_base)
 
        print(f"OK {symbol}: {close:.4f} ({daily:+.2f}%)")
        return {
            "name": name, "unit": unit,
            "close": f"{close:.4f}",
            "daily": f"{daily:+.2f}%",
            "ytd":   f"{ytd:+.1f}%",
            "dSign": sign(daily), "ySign": sign(ytd),
            "asOf":  as_of
        }
    except Exception as e:
        print(f"WARN {symbol}: {e}")
        return {"name": name, "unit": unit,
                "close": "—", "daily": "—", "ytd": "—",
                "dSign": 0, "ySign": 0, "asOf": "—"}
 
def fetch_yield_yf(symbol, name, ytd_base_ref):
    try:
        end   = datetime.date.today()
        start = end - datetime.timedelta(days=14)
        hist  = get_hist(symbol, start, end)
        if hist.empty or len(hist) < 2:
            raise ValueError("not enough rows")
        cur  = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        if cur == 0: raise ValueError("zero yield")
        chg     = bps(cur, prev)
        ytd_chg = bps(cur, ytd_base_ref)
        as_of   = hist.index[-1].strftime("%-d %b %Y")
        print(f"OK {symbol}: {cur:.2f}% ({chg:+.1f} bps)")
        return {
            "name": name, "unit": "Yield %", "isBond": True,
            "close": f"{cur:.2f}%",
            "daily": f"{chg:+.1f} bps",
            "ytd":   f"{ytd_chg:+.1f} bps",
            "dSign": sign(chg), "ySign": sign(ytd_chg),
            "asOf":  as_of
        }
    except Exception as e:
        print(f"WARN {symbol}: {e}")
        return {"name": name, "unit": "Yield %", "isBond": True,
                "close": "—", "daily": "—", "ytd": "—",
                "dSign": 0, "ySign": 0, "asOf": "—"}
 
def fetch_fred(series, name, ytd_base):
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series}&sort_order=desc&limit=5"
           f"&api_key={FRED}&file_type=json")
    with urllib.request.urlopen(url, timeout=15) as r:
        obs = [o for o in json.loads(r.read())["observations"] if o["value"] != "."]
    cur  = float(obs[0]["value"])
    prev = float(obs[1]["value"])
    chg     = bps(cur, prev)
    ytd_chg = bps(cur, ytd_base)
    print(f"OK FRED {series}: {cur:.2f}%")
    return {
        "name": name, "unit": "Yield %", "isBond": True,
        "close": f"{cur:.2f}%",
        "daily": f"{chg:+.1f} bps",
        "ytd":   f"{ytd_chg:+.1f} bps",
        "dSign": sign(chg), "ySign": sign(ytd_chg)
    }
 
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
    chg     = bps(cur, prev)
    ytd_chg = bps(cur, ytd_base)
    print(f"OK ECB {maturity}: {cur:.2f}%")
    return {
        "name": name, "unit": "Yield %", "isBond": True,
        "close": f"{cur:.2f}%",
        "daily": f"{chg:+.1f} bps",
        "ytd":   f"{ytd_chg:+.1f} bps",
        "dSign": sign(chg), "ySign": sign(ytd_chg)
    }
 
# ── FETCH ALL ─────────────────────────────────────────────────────────────
print("=== Equities ===")
equities = [
    fetch_price("^GSPC",  "S&P 500",      "USD pts"),
    fetch_price("^IXIC",  "Nasdaq",        "USD pts"),
    fetch_price("^STOXX", "STOXX 600",     "EUR pts"),
    fetch_price("^N225",  "Nikkei 225",    "JPY pts"),
    fetch_price("EEM",    "MSCI EM",       "USD pts"),
]
 
print("=== Commodities ===")
commodities = [
    fetch_price("GC=F",  "Gold",          "USD / oz"),
    fetch_price("CL=F",  "Crude Oil WTI", "USD / bbl"),
]
 
print("=== FX ===")
fx = [
    fetch_fx("EURUSD=X", "EUR / USD", "Rate"),
    fetch_fx("JPYUSD=X", "JPY / USD", "Rate"),
]
 
print("=== Bond Yields ===")
bonds = []
 
# US 10Y — Yahoo ^TNX, fallback FRED DGS10
try:
    bonds.append(fetch_yield_yf("^TNX", "US Treasury 10Y", 4.19))
except:
    try:
        bonds.append(fetch_fred("DGS10", "US Treasury 10Y", 4.19))
    except Exception as e:
        print(f"US 10Y failed: {e}")
        bonds.append({"name":"US Treasury 10Y","unit":"Yield %","isBond":True,
                      "close":"—","daily":"—","ytd":"—","dSign":0,"ySign":0})
 
# US 1Y — Yahoo ^IRX, fallback FRED DGS1
try:
    bonds.append(fetch_yield_yf("^IRX", "US Treasury 1Y", 4.64))
except:
    try:
        bonds.append(fetch_fred("DGS1", "US Treasury 1Y", 4.64))
    except Exception as e:
        print(f"US 1Y failed: {e}")
        bonds.append({"name":"US Treasury 1Y","unit":"Yield %","isBond":True,
                      "close":"—","daily":"—","ytd":"—","dSign":0,"ySign":0})
 
# ECB yields
for mat, name, ytd_base in [
    ("1Y",  "ECB 1Y Yield",  2.85),
    ("10Y", "ECB 10Y Yield", 3.50),
]:
    try:
        bonds.append(fetch_ecb(mat, name, ytd_base))
    except Exception as e:
        print(f"WARN ECB {mat}: {e}")
        bonds.append({"name": name, "unit": "Yield %", "isBond": True,
                      "close": "—", "daily": "—", "ytd": "—",
                      "dSign": 0, "ySign": 0})
 
# ── WRITE data.json ────────────────────────────────────────────────────────
dates = [e["asOf"] for e in equities + commodities if e.get("asOf","—") != "—"]
as_of = dates[0] if dates else datetime.datetime.utcnow().strftime("%-d %b %Y")
now   = datetime.datetime.utcnow()
 
out = {
    "asOf": as_of,
    "updatedAt": now.strftime("%H:%M %d %b %Y UTC"),
    "sections": [
        {"label": "Equities",    "rows": equities},
        {"label": "Commodities", "rows": commodities},
        {"label": "FX",          "rows": fx},
        {"label": "Bond Yields", "rows": bonds},
    ]
}
with open("data.json", "w") as f:
    json.dump(out, f, indent=2)
print(f"\n✓ data.json written — asOf: {as_of}")
