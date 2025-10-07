import yfinance as yf
import time
import json
import warnings
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

# ---------- Configuration ----------
TZ = ZoneInfo("Europe/Vilnius")
CACHE_FILE = Path("ath_cache.json")
warnings.filterwarnings("ignore", category=UserWarning)

# ANSI colors for terminal output
RED   = "\033[91m"
GRAY  = "\033[90m"
GREEN = "\033[92m"
RESET = "\033[0m"

# Regex to strip ANSI codes for email-safe text
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

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

def get_change(ticker, days):
    t = yf.Ticker(ticker)
    hist = t.history(period=f"{days+5}d", interval="1d")["Close"].dropna()
    if len(hist) < 2:
        return None
    now = hist.iloc[-1]
    past = hist.iloc[-min(days, len(hist)-1)]
    return (now / past - 1) * 100

def get_ytd_change(ticker):
    t = yf.Ticker(ticker)
    start = datetime(datetime.now().year, 1, 1)
    hist = t.history(start=start, interval="1d")["Close"].dropna()
    if len(hist) < 2:
        return None
    return (hist.iloc[-1] / hist.iloc[0] - 1) * 100

# ---------- Formatting ----------
def colorize(value):
    if value is None:
        return "N/A"
    color = GRAY if abs(value) < 0.005 else (GREEN if value > 0 else RED)
    sign = "+" if value >= 0 else ""
    return f"{color}{sign}{value:.2f}%{RESET}"

def plain(value):
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"

# ---------- Main ----------
def main():
    now_str = datetime.now(TZ).strftime("%Y-%m-%d %H:%M %Z")
    print(f"{now_str} update\n")

    tickers = [
        ("NASDAQ-100", "^NDX"),
        ("S&P 500", "^GSPC"),
        ("Bitcoin", "BTC-USD")
    ]

    cache = load_cache()
    text_lines = [f"{now_str} update\n"]

    for name, ticker in tickers:
        try:
            ath = get_cached_ath(ticker, cache)
            current = get_current_price(ticker)
            if current > ath:
                ath = current
                cache[ticker] = {"ath": ath, "updated": datetime.now(TZ).isoformat()}
                save_cache(cache)
            from_ath = (current / ath - 1) * 100

            data = {
                "1d": get_change(ticker, 1),
                "1w": get_change(ticker, 7),
                "1m": get_change(ticker, 30),
                "3m": get_change(ticker, 90),
                "6m": get_change(ticker, 180),
                "1y": get_change(ticker, 365),
                "ytd": get_ytd_change(ticker),
            }

            print(f"{name}:")
            print(f"  Current: ${current:,.2f} | ATH: ${ath:,.2f} | From ATH: {colorize(from_ath)}")
            print(f"  24h diff: {colorize(data['1d'])} | 1 week: {colorize(data['1w'])} | 1 month: {colorize(data['1m'])}")
            print(f"  3 months: {colorize(data['3m'])} | 6 months: {colorize(data['6m'])} | 1 year: {colorize(data['1y'])} | YTD: {colorize(data['ytd'])}\n")

            # Plain version (no color codes)
            text_lines.append(f"{name}:")
            text_lines.append(f"  Current: ${current:,.2f} | ATH: ${ath:,.2f} | From ATH: {plain(from_ath)}")
            text_lines.append(f"  24h diff: {plain(data['1d'])} | 1 week: {plain(data['1w'])} | 1 month: {plain(data['1m'])}")
            text_lines.append(f"  3 months: {plain(data['3m'])} | 6 months: {plain(data['6m'])} | 1 year: {plain(data['1y'])} | YTD: {plain(data['ytd'])}\n")

        except Exception as e:
            text_lines.append(f"{name}: Error - {e}")

    # Write colorless version for email
    output_text = "\n".join(text_lines)
    # Strip any accidental ANSI codes
    clean_text = ANSI_ESCAPE.sub("", output_text)
    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(clean_text)

if __name__ == "__main__":
    main()
