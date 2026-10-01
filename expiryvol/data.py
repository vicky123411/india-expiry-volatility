"""Download, cache and clean the price data.

Three free sources are used (none is stored in this repository; the first run downloads them
into `data/`):

1. Yahoo Finance daily bars (Open/High/Low/Close) for the four indices, India VIX and two
   US series. Same source and download code as paper 1. Yahoo's terms don't allow
   redistributing the prices, so they are not committed.
2. One-minute index bars for Nifty 50, Bank Nifty and Sensex (May 2021 - Jul 2026) from the
   Hugging Face dataset `thetrademarkk/india-index-options-1m` (licence CC BY-NC 4.0).
   Used for the intraday analysis. Checked against Yahoo's daily bars in notebook 1.
3. NSE F&O end-of-day contract files ("bhavcopy") for Nifty and Bank Nifty options,
   as collected in the Hugging Face dataset `rissin/nse-options-intraday` (folder
   `historical_daily`). Used to check the expiry calendar and to measure how much
   option trading happens on expiry days.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from .holidays import COVERAGE, HOLIDAYS, MUHURAT

TICKERS = {
    "nifty50": "^NSEI",        # Nifty 50 (NSE)
    "banknifty": "^NSEBANK",   # Nifty Bank (NSE)
    "sensex": "^BSESN",        # S&P BSE Sensex (BSE)
    "midcap50": "^NSEMDCP50",  # Nifty Midcap 50 (NSE): comparison index
    "indiavix": "^INDIAVIX",   # India VIX
    "sp500": "^GSPC",          # S&P 500 (for the forecasting test, as in paper 1)
    "usvix": "^VIX",           # CBOE VIX
}
INDICES = ("nifty50", "banknifty", "sensex", "midcap50")
LABELS = {"nifty50": "Nifty 50", "banknifty": "Bank Nifty", "sensex": "Sensex", "midcap50": "Midcap 50"}
COLUMNS = ["Open", "High", "Low", "Close"]

DOWNLOAD_START = "2013-06-01"   # half a year of history before the study starts (for lagged inputs)
STUDY_START = "2014-01-01"
STUDY_END = "2026-07-31"        # main sample ends before the closing auction session (3 Aug 2026)
DATA_END = "2026-09-30"         # downloads stop here, so a fresh download reproduces the results

HF_BASE = "https://huggingface.co/datasets"
MINUTE_SOURCE = ("thetrademarkk/india-index-options-1m", "index/{symbol}.parquet")
OPTIONS_SOURCE = ("rissin/nse-options-intraday", "historical_daily/{symbol}/{symbol}_{year}.parquet")
MINUTE_SYMBOL = {"nifty50": "NIFTY", "banknifty": "BANKNIFTY", "sensex": "SENSEX"}


# ------------------------------------------------------------------------ trading calendar
def trading_days(start: str = COVERAGE[0], end: str = COVERAGE[1], strict: bool = False) -> pd.DatetimeIndex:
    """Days on which NSE and BSE held a normal session: weekdays minus holidays and Muhurat days.

    The holiday list covers 2014-01-01 to 2026-09-30. Outside that period only weekends are
    removed; with `strict=True` a request outside the period raises an error instead.
    """
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    if strict and (lo < pd.Timestamp(COVERAGE[0]) or hi > pd.Timestamp(COVERAGE[1])):
        raise ValueError(f"the holiday list covers {COVERAGE[0]} to {COVERAGE[1]} only")
    days = pd.bdate_range(lo, hi)
    closed = pd.DatetimeIndex(pd.to_datetime(list(HOLIDAYS) + list(MUHURAT)))
    return days.difference(closed)


# ------------------------------------------------------------------------ Yahoo daily bars
def download_daily(ticker: str, start: str = DOWNLOAD_START, end: str = DATA_END,
                   retries: int = 4, pause: float = 15.0) -> pd.DataFrame:
    """Download daily Open/High/Low/Close from Yahoo Finance, retrying if Yahoo is busy."""
    import yfinance as yf

    stop = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")   # yfinance's end is exclusive
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            df = yf.download(ticker, start=start, end=stop, progress=False, auto_adjust=False, threads=False)
            if isinstance(df.columns, pd.MultiIndex):    # newer yfinance versions return two header rows
                df.columns = df.columns.get_level_values(0)
            df = df[COLUMNS]
            if len(df):
                df.index = pd.to_datetime(df.index)
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                df.index = df.index.normalize()
                df.index.name = "Date"
                return df.dropna()
            last_error = RuntimeError("no rows returned")
        except Exception as exc:   # network errors, rate limits
            last_error = exc
        if attempt < retries:
            time.sleep(pause * attempt)
    raise RuntimeError(f"Could not download {ticker} from Yahoo Finance: {last_error}")


def load_daily(name: str, data_dir: str | Path = "data", refresh: bool = False) -> pd.DataFrame:
    """Raw daily bars of one series from `data/<name>.csv`, downloading them first if needed."""
    path = Path(data_dir) / f"{name}.csv"
    if refresh or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        download_daily(TICKERS[name]).to_csv(path)
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df[COLUMNS]


def clean_daily(raw: pd.DataFrame, us_market: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep only normal Indian trading sessions with usable bars.

    Drops (and reports) rows that are: not normal sessions (weekends such as Budget-day
    Saturdays, Diwali Muhurat evening sessions); incomplete; or "stale" (High equal to Low,
    i.e. no price movement recorded). Returns (clean bars, dropped rows with a reason).
    US series (`us_market=True`) only lose incomplete rows.
    """
    df = raw.copy()
    df.index = pd.to_datetime(df.index).normalize()
    df = df[~df.index.duplicated(keep="last")]
    reason = pd.Series("", index=df.index, dtype=object)
    reason[df[COLUMNS].isna().any(axis=1)] = "missing value"
    if not us_market:
        normal = trading_days(df.index.min().strftime("%Y-%m-%d"), df.index.max().strftime("%Y-%m-%d"))
        reason[(reason == "") & ~df.index.isin(normal)] = "not a normal session"
        stale = (df["High"] <= df["Low"]) | (df["Open"] <= 0)
        reason[(reason == "") & stale] = "stale bar"
        bad_ohlc = (df["Open"] > df["High"] * 1.0001) | (df["Open"] < df["Low"] * 0.9999) | \
                   (df["Close"] > df["High"] * 1.0001) | (df["Close"] < df["Low"] * 0.9999)
        reason[(reason == "") & bad_ohlc] = "inconsistent bar"
    dropped = pd.DataFrame({"reason": reason[reason != ""]})
    return df[reason == ""], dropped


def load_all_daily(data_dir: str | Path = "data", refresh: bool = False,
                   names=tuple(TICKERS)) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Clean daily bars for every series, plus a log of every dropped row."""
    out, logs = {}, []
    for name in names:
        clean, dropped = clean_daily(load_daily(name, data_dir, refresh), us_market=name in ("sp500", "usvix"))
        out[name] = clean
        if len(dropped):
            logs.append(dropped.assign(series=name))
    log = pd.concat(logs).rename_axis("date").reset_index() if logs else pd.DataFrame(columns=["date", "reason", "series"])
    return out, log


# ------------------------------------------------------------------------ Hugging Face files
def _hf_download(repo: str, path: str, target: Path, refresh: bool = False) -> Path:
    if target.exists() and not refresh:
        return target
    import urllib.request

    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"{HF_BASE}/{repo}/resolve/main/{path}"
    last_error = None
    for attempt in range(1, 5):
        try:
            tmp = target.with_suffix(target.suffix + ".part")
            with urllib.request.urlopen(url, timeout=300) as resp, open(tmp, "wb") as fh:
                fh.write(resp.read())
            tmp.replace(target)
            return target
        except Exception as exc:
            last_error = exc
            time.sleep(5 * attempt)
    raise RuntimeError(f"Could not download {url}: {last_error}")


def load_minute(index: str, data_dir: str | Path = "data", refresh: bool = False,
                min_bars: int = 360) -> pd.DataFrame:
    """One-minute bars of the regular session (09:15-15:29) for one index.

    Keeps normal trading days with at least `min_bars` one-minute bars (drops partial days).
    Index: timestamp (India time, no time zone); columns Open/High/Low/Close and `day`.
    """
    symbol = MINUTE_SYMBOL[index]
    repo, pattern = MINUTE_SOURCE
    path = _hf_download(repo, pattern.format(symbol=symbol), Path(data_dir) / "minute" / f"{symbol}.parquet", refresh)
    m = pd.read_parquet(path, columns=["timestamp", "open", "high", "low", "close"])
    ts = pd.to_datetime(m["timestamp"])
    ts = ts.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None) if ts.dt.tz is not None else ts
    m = m.assign(timestamp=ts).drop_duplicates("timestamp").set_index("timestamp").sort_index()
    m.columns = COLUMNS
    clock = m.index.strftime("%H:%M")
    m = m[(clock >= "09:15") & (clock <= "15:29")].copy()
    m["day"] = m.index.normalize()
    normal = trading_days(m["day"].min().strftime("%Y-%m-%d"), m["day"].max().strftime("%Y-%m-%d"))
    m = m[m["day"].isin(normal)]
    counts = m.groupby("day").size()
    full = counts.index[counts >= min_bars]
    return m[m["day"].isin(full)]


def load_options_eod(symbol: str, years, data_dir: str | Path = "data", refresh: bool = False,
                     columns=("date", "expiry", "strike", "option_type", "close", "volume", "oi")) -> pd.DataFrame:
    """End-of-day option contract data (NSE bhavcopy) for NIFTY or BANKNIFTY, selected years."""
    repo, pattern = OPTIONS_SOURCE
    parts = []
    for year in years:
        rel = pattern.format(symbol=symbol, year=year)
        path = _hf_download(repo, rel, Path(data_dir) / "options" / f"{symbol}_{year}.parquet", refresh)
        parts.append(pd.read_parquet(path, columns=list(columns)))
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["expiry"] = pd.to_datetime(df["expiry"]).dt.normalize()
    return df


def observed_expiry_days(options: pd.DataFrame, max_shift_days: int = 6) -> pd.DatetimeIndex:
    """Expiry days seen in the contract files: for each series (expiry label), its expiry day.

    Normally a series trades on its labelled expiry date. When that date is a holiday, the
    series expires on the previous trading day but NSE's files keep the original label, so
    the expiry day is then the last date on which the series traded (if it is at most
    `max_shift_days` before the label). Labels whose date is missing from the files for
    another reason (gaps in the files) are left out.
    """
    file_days = set(options["date"].unique())
    last_file_day = options["date"].max()
    last = options.groupby("expiry")["date"].max()
    same_day = sorted(label for label, last_day in last.items() if last_day == label)
    out = list(same_day)
    for label, last_day in last.items():
        if last_day == label or label in file_days or label > last_file_day:
            continue
        if pd.Timestamp(label).weekday() >= 5 or not 0 < (label - last_day).days <= max_shift_days:
            continue
        # sometimes NSE relabels the series to its actual expiry day instead: then that
        # same-day expiry lies between the last trade under the old label and the label
        if any(last_day < d < label for d in same_day):
            continue
        out.append(last_day)
    return pd.DatetimeIndex(sorted(set(out)))


def summarize_dropped(log: pd.DataFrame) -> pd.DataFrame:
    """Count of dropped daily rows by series and reason (for the data appendix)."""
    if log.empty:
        return pd.DataFrame()
    return log.pivot_table(index="series", columns="reason", values="date", aggfunc="count", fill_value=0)


def as_index(values) -> np.ndarray:
    return np.asarray(values)
