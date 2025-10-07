import yfinance as yf
import time
import json
import warnings
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

# ---------- Configuration ----------
TZ = ZoneInfo("Europe/Vilnius")
CACHE_FILE = Path("ath_cache.json")
warnings.filterwarnings("ignore", category=UserWarning)

# ANSI colors for console output
RED = "\033[91m"
GRAY = "\033[90m"
GREEN = "\033[92m"
RESET = "\033[0m"

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
    """Return cached ATH if fresh (<7 days), else refresh from Yahoo Finance."""
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
    ath = float(max(hist_all.max() if not hist_all.empty else 0,
                    intraday_high if intraday_high else 0))

    cache[ticker] = {"ath": ath, "updated": now.isoformat()}
    save_cache(cache)
    return ath

def get_current_price(ticker):
    """Return current (latest 1-minute) price, fallback to last daily close."""
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

def get_24h_change_live(ticker, current_price):
    """Return 24h change using current live price vs. last daily close."""
    t = yf.Ticker(ticker)
    hist = t.history(period="2d", interval="1d")["Close"].dropna()
    if len(hist) < 1:
        return None
    last_close = hist.iloc[-1]
    return (current_price / last_close - 1.0) * 100.0

def get_change_percent(ticker, days):
    """Calculate percentage change over given number of days."""
    t = yf.Ticker(ticker)
    hist = t.history(period=f"{max(days+5, 10)}d", interval="1d")["Close"].dropna()
    if len(hist) < 2:
        return None
    now_price = hist.iloc[-1]
    past_price = hist.iloc[-min(days, len(hist)-1)]
    return (now_price / past_price - 1.0) * 100.0

def get_ytd_change(ticker):
    """Change since the first trading day of the current year."""
    t = yf.Ticker(ticker)
    start_of_year = datetime(datetime.now().year, 1, 1)
    hist = t.history(start=start_of_year, interval="1d")["Close"].dropna()
    if hist.empty:
        return None
    first_price = hist.iloc[0]
    last_price = hist.iloc[-1]
    return (last_price / first_price - 1.0) * 100.0

# ---------- Formatting ----------
def colorize_change(value):
    """Return colored string for console % change."""
    if value is None:
        return "N/A"
    if abs(value) < 0.005:
        color = GRAY
    elif value > 0:
        color = GREEN
    else:
        color = RED
    sign = "+" if value >= 0 else ""
    return f"{color}{sign}{value:.2f}%{RESET}"

def html_colorize(value):
    """Return colored HTML span for % change."""
    if value is None:
        return "N/A"
    color = "#888" if abs(value) < 0.005 else ("#0b0" if value > 0 else "#d00")
    sign = "+" if value >= 0 else ""
    return f"<span style='color:{color};'>{sign}{value:.2f}%</span>"

# ---------- Main ----------
def main():
    now_lt = datetime.now(TZ).strftime("%Y-%m-%d %H:%M %Z")
    print(f"{now_lt} update\n\n")

    cache = load_cache()
    tickers = [
        ("NASDAQ-100", "^NDX"),
        ("S&P 500", "^GSPC"),
        ("Bitcoin", "BTC-USD")
    ]

    rows = []
    html_output = f"<h2 style='font-family:sans-serif;'>Daily Index Update — {now_lt}</h2>\n"
    html_output += "<div style='font-family:monospace; line-height:1.5;'>\n"

    for name, ticker in tickers:
        try:
            ath = get_cached_ath(ticker, cache)
            current = get_current_price(ticker)
            if current > ath:
                print(f"(New intraday ATH detected for {name} — updating cache.)")
                ath = current
                cache[ticker] = {"ath": ath, "updated": datetime.now(TZ).isoformat()}
                save_cache(cache)

            pct_from_ath = (current / ath - 1.0) * 100.0

            # Performance changes
            change_1d = get_24h_change_live(ticker, current)
            change_1w = get_change_percent(ticker, 7)
            change_1m = get_change_percent(ticker, 30)
            change_3m = get_change_percent(ticker, 90)
            change_6m = get_change_percent(ticker, 180)
            change_1y = get_change_percent(ticker, 365)
            change_ytd = get_ytd_change(ticker)

            # Store everything
            rows.append({
                "name": name,
                "current": current,
                "ath": ath,
                "from_ath": pct_from_ath,
                "c1d": change_1d,
                "c1w": change_1w,
                "c1m": change_1m,
                "c3m": change_3m,
                "c6m": change_6m,
                "c1y": change_1y,
                "cytd": change_ytd
            })

        except Exception as e:
            rows.append({"name": name, "error": str(e)})

    current_width = max(len(f"${r['current']:,.2f}") for r in rows if "error" not in r)
    ath_width = max(len(f"${r['ath']:,.2f}") for r in rows if "error" not in r)

    for r in rows:
        print(f"{r['name']}:")
        if "error" in r:
            print(f"  Error: {r['error']}\n")
            html_output += f"<b>{r['name']}:</b><br>Error: {r['error']}<br><br>\n"
            continue

        val = r["from_ath"]
        if abs(val) < 0.005:
            color = GRAY
        elif val < 0:
            color = RED
        else:
            color = GREEN
        sign = "+" if val >= 0 else ""
        from_ath_colored = f"{color}{sign}{val:.2f}%{RESET}"

        # Console print
        print(
            f"  Current: ${r['current']:,.2f} |  "
            f"ATH: ${r['ath']:,.2f} |  "
            f"From ATH: {from_ath_colored}"
        )
        print(
            f"  24h diff: {colorize_change(r['c1d'])}   |  "
            f"1 week: {colorize_change(r['c1w'])}   |  "
            f"1 month: {colorize_change(r['c1m'])}"
        )
        print(
            f"  3 months: {colorize_change(r['c3m'])}   |  "
            f"6 months: {colorize_change(r['c6m'])}   |  "
            f"1 year: {colorize_change(r['c1y'])}   |  "
            f"YTD: {colorize_change(r['cytd'])}\n"
        )

        # HTML version
        html_output += (
            f"<b>{r['name']}:</b><br>"
            f"Current: ${r['current']:,.2f} | ATH: ${r['ath']:,.2f} | From ATH: {html_colorize(val)}<br>"
            f"24h diff: {html_colorize(r['c1d'])} | 1 week: {html_colorize(r['c1w'])} | 1 month: {html_colorize(r['c1m'])}<br>"
            f"3 months: {html_colorize(r['c3m'])} | 6 months: {html_colorize(r['c6m'])} | "
            f"1 year: {html_colorize(r['c1y'])} | YTD: {html_colorize(r['cytd'])}<br><br>\n"
        )

    html_output += "</div>\n"

    # Write HTML report for GitHub email step
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html_output)

    print("\nHTML report written to report.html\n")


if __name__ == "__main__":
    main()
