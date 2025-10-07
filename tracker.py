import yfinance as yf
import time
import json
import warnings
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from tabulate import tabulate

# ---------- Configuration ----------
TZ = ZoneInfo("Europe/Vilnius")
CACHE_FILE = Path("ath_cache.json")
warnings.filterwarnings("ignore", category=UserWarning)

# ---------- Cache Helpers ----------
def load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass

# ---------- Data Retrieval ----------
def get_cached_ath(ticker, cache):
    now = datetime.now(TZ)
    entry = cache.get(ticker)
    if entry:
        try:
            last_update = datetime.fromisoformat(entry["updated"])
            if (now - last_update).days < 7 and "ath" in entry:
                return float(entry["ath"])
        except Exception:
            pass

    t = yf.Ticker(ticker)
    hist_all = t.history(period="max")["Close"].dropna()
    hist_intraday = t.history(period="5d", interval="1m")
    intraday_high = hist_intraday["High"].max() if not hist_intraday.empty else None

    if hist_all.empty and intraday_high is None:
        raise RuntimeError(f"Could not refresh ATH for {ticker}")

    ath = float(max(hist_all.max(), intraday_high or 0))
    cache[ticker] = {"ath": ath, "updated": now.isoformat()}
    save_cache(cache)
    return ath

def get_current_price(ticker):
    t = yf.Ticker(ticker)
    for _ in range(2):
        intraday = t.history(period="1d", interval="1m")["Close"].dropna()
        if not intraday.empty:
            return float(intraday.iloc[-1])
        time.sleep(2)
    daily = t.history(period="5d", interval="1d")["Close"].dropna()
    if daily.empty:
        raise RuntimeError(f"No price data for {ticker}")
    return float(daily.iloc[-1])

def get_change_percent(ticker, days):
    t = yf.Ticker(ticker)
    hist = t.history(period=f"{max(days+5, 10)}d", interval="1d")["Close"].dropna()
    if len(hist) < 2:
        return None
    now_price = hist.iloc[-1]
    past_price = hist.iloc[-min(days, len(hist)-1)]
    return (now_price / past_price - 1.0) * 100.0

def get_ytd_change(ticker):
    t = yf.Ticker(ticker)
    start_of_year = datetime(datetime.now().year, 1, 1)
    hist = t.history(start=start_of_year, interval="1d")["Close"].dropna()
    if hist.empty:
        return None
    return (hist.iloc[-1] / hist.iloc[0] - 1.0) * 100.0

# ---------- Formatting ----------
def fmt(value):
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"

# ---------- Main ----------
def main():
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M %Z")
    print(f"\n{now} update\n")

    cache = load_cache()
    tickers = [
        ("NASDAQ-100", "^NDX"),
        ("S&P 500", "^GSPC"),
        ("Bitcoin", "BTC-USD")
    ]

    for name, ticker in tickers:
        try:
            ath = get_cached_ath(ticker, cache)
            current = get_current_price(ticker)
            if current > ath:
                ath = current
                cache[ticker] = {"ath": ath, "updated": datetime.now(TZ).isoformat()}
                save_cache(cache)

            pct_from_ath = (current / ath - 1.0) * 100.0

            # Performance changes
            change_1d = get_change_percent(ticker, 1)
            change_1w = get_change_percent(ticker, 7)
            change_1m = get_change_percent(ticker, 30)
            change_3m = get_change_percent(ticker, 90)
            change_6m = get_change_percent(ticker, 180)
            change_1y = get_change_percent(ticker, 365)
            change_ytd = get_ytd_change(ticker)

            table = [
                ["Current", f"${current:,.2f}"],
                ["ATH", f"${ath:,.2f}"],
                ["From ATH", fmt(pct_from_ath)],
                ["24h diff", fmt(change_1d)],
                ["1 week", fmt(change_1w)],
                ["1 month", fmt(change_1m)],
                ["3 months", fmt(change_3m)],
                ["6 months", fmt(change_6m)],
                ["1 year", fmt(change_1y)],
                ["YTD", fmt(change_ytd)],
            ]

            print(f"{name}:\n{tabulate(table, headers=['Metric', 'Value'], tablefmt='plain')}\n")

        except Exception as e:
            print(f"{name}: Error - {e}\n")

if __name__ == "__main__":
    main()
