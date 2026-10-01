"""Mechanism tests: when in the day expiry matters, pinning to strikes, intraday reversals,
and how much option trading happens on expiry days.

Uses the one-minute index bars (Nifty 50, Bank Nifty: May 2021 - Jul 2026; Sensex: Sep 2022 -
Jul 2026) and NSE's end-of-day option files (Nifty and Bank Nifty, 2014 - Jun 2026).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import expiries as ex
from .data import load_minute, load_options_eod
from .estimate import MAIN_FE, TREAT, fe_ols
from .features import distance_to_grid, minute_day_measures, minute_segments

MINUTE_INDICES = ("nifty50", "banknifty", "sensex")
OPTION_SYMBOL = {"nifty50": "NIFTY", "banknifty": "BANKNIFTY"}
STRIKE_STEPS = {"nifty50": (50, 100), "banknifty": (100, 500), "sensex": (100, 500)}
FLOOR = 1e-4   # added to realized variances (in %^2) before taking logs; protects quiet 15-minute slots


def _calendar_columns(df: pd.DataFrame) -> pd.DataFrame:
    days = pd.DatetimeIndex(df["date"])
    df["wd"] = days.weekday
    iso = days.isocalendar()
    df["week"] = (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()
    df["year"] = days.year
    return df


def minute_panels(table: pd.DataFrame, data_dir="data", end: str = "2026-07-31",
                  slot_minutes: int = 15) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily measures and per-slot realized variances from one-minute bars, with expiry flags.

    Returns (days, slots): one row per (index, day), and one row per (index, day, slot).
    """
    days_parts, slot_parts = [], []
    for index in MINUTE_INDICES:
        m = load_minute(index, data_dir)
        m = m[m["day"] <= pd.Timestamp(end)]
        flags = ex.expiry_flags(table, index)
        d = minute_day_measures(m).join(flags, how="inner")
        d["index"] = index
        days_parts.append(d.rename_axis("date").reset_index())
        s = minute_segments(m, slot_minutes).merge(flags, left_on="date", right_index=True, how="inner")
        s["index"] = index
        slot_parts.append(s)
    days = _calendar_columns(pd.concat(days_parts, ignore_index=True))
    days["lrv5"] = np.log(days["rv5"] + FLOOR)
    days["lrv_last"] = np.log(days["rv_last"] + FLOOR)
    slots = _calendar_columns(pd.concat(slot_parts, ignore_index=True))
    slots["lrv"] = np.log(slots["rv"] + FLOOR)
    return days, slots


def slot_effects(slots: pd.DataFrame) -> pd.DataFrame:
    """Expiry effect on log realized variance in each slot of the session (pooled over indices),
    with the main specification's fixed effects estimated separately for each slot."""
    rows = []
    for start, s in slots.groupby("start"):
        r = fe_ols(s, "lrv", TREAT, MAIN_FE)
        t = r.table()
        for term in ["own_weekly", "own_monthly", "other_major"]:
            rows.append({"start": start, "term": term, **t.loc[term].to_dict(), "n": r.nobs})
    return pd.DataFrame(rows)


def day_effects(days: pd.DataFrame, outcomes=("lrv5", "lrv_last")) -> pd.DataFrame:
    """Main specification on minute-based daily outcomes (pooled and per index)."""
    rows = []
    for y in outcomes:
        r = fe_ols(days, y, TREAT, MAIN_FE)
        rows.append(r.table().assign(outcome=y, sample="pooled", n=r.nobs))
        for idx, sub in days.groupby("index"):
            r = fe_ols(sub, y, TREAT, (("wd",), ("week",)))
            rows.append(r.table().assign(outcome=y, sample=idx, n=r.nobs))
    return pd.concat(rows).rename_axis("term").reset_index()


# ------------------------------------------------------------------------ reversals
def reversal_tests(days: pd.DataFrame) -> pd.DataFrame:
    """Does the afternoon undo the morning more on expiry days?

    r_pm = a + b r_am + c (r_am x own) + d own + fixed effects. A negative c means stronger
    reversal on expiry days. Also the "last half hour" test of intraday momentum:
    r_last = a + b r_rest + c (r_rest x own) + ...
    """
    d = days.copy()
    d["am_x_own"] = d["r_am"] * d["own"]
    d["rest_x_own"] = d["r_rest"] * d["own"]
    rows = []
    samples = {"pooled": d}
    for idx in MINUTE_INDICES:
        samples[idx] = d[d["index"] == idx]
    # the period covered by SEBI's interim order (Bank Nifty, Jan 2023 - Mar 2025)
    samples["banknifty 2023-01..2025-03"] = d[(d["index"] == "banknifty") & (d["date"] >= "2023-01-01") & (d["date"] <= "2025-03-31")]
    for name, s in samples.items():
        fe = MAIN_FE if name == "pooled" else (("wd",), ("week",))
        r = fe_ols(s, "r_pm", ["r_am", "am_x_own", "own"], fe)
        rows.append(r.table().assign(test="afternoon on morning", sample=name, n=r.nobs))
        r = fe_ols(s, "r_last", ["r_rest", "rest_x_own", "own"], fe)
        rows.append(r.table().assign(test="last half hour on rest of day", sample=name, n=r.nobs))
    return pd.concat(rows).rename_axis("term").reset_index()


# ------------------------------------------------------------------------ pinning
def grid_pinning(panel: pd.DataFrame, band: float = 0.1) -> pd.DataFrame:
    """Share of official closes within `band` x step of a strike (multiple of the step).

    With no pinning the share is about 2 x band (0.2), whatever the day. The regression
    version uses the main specification's fixed effects (linear probability model).
    """
    rows = []
    for index, steps in STRIKE_STEPS.items():
        s = panel[panel["index"] == index].copy()
        for step in steps:
            s["near"] = (distance_to_grid(s["close"], step) < band).astype(float)
            r = fe_ols(s, "near", TREAT, (("wd",), ("week",)))
            t = r.table().loc["own"] if "own" in r.params else r.table().loc["own_weekly"]
            rows.append({"index": index, "step": step,
                         "share_expiry": s.loc[s["own"] == 1, "near"].mean(),
                         "share_other": s.loc[s["own"] == 0, "near"].mean(),
                         "n_expiry": int(s["own"].sum()),
                         "coef_weekly": r.params["own_weekly"], "se_weekly": r.se["own_weekly"],
                         "coef_monthly": r.params["own_monthly"], "se_monthly": r.se["own_monthly"]})
    return pd.DataFrame(rows)


def max_oi_strikes(index: str, table: pd.DataFrame, trading_days, data_dir="data",
                   years=range(2014, 2027)) -> pd.DataFrame:
    """For every trading day t: the strike with the most open interest (calls + puts) in the
    series with the nearest expiry, measured at the close of the previous trading day.

    Columns: date, expiry (that series' expiry day), kstar, days_to_expiry (sessions).
    """
    symbol = OPTION_SYMBOL[index]
    opt = load_options_eod(symbol, years, data_dir, columns=("date", "expiry", "strike", "option_type", "oi"))
    days = pd.DatetimeIndex(sorted(pd.to_datetime(trading_days)))
    exp = ex.expiry_dates(symbol, days)
    # the exchange's label of a series is its scheduled date; map labels to actual expiry days
    label_to_day = {**dict(zip(exp["scheduled"], exp["date"])),
                    **{d: d for d in exp["date"]}}      # NSE sometimes relabels a series to its actual day
    opt = opt[opt["expiry"].isin(label_to_day.keys())].copy()
    opt["exp_day"] = opt["expiry"].map(label_to_day)
    oi = opt.groupby(["date", "exp_day", "strike"], as_index=False)["oi"].sum()
    rows = []
    file_days = pd.DatetimeIndex(sorted(oi["date"].unique()))
    by_date = dict(tuple(oi.groupby("date")))
    exp_days = pd.DatetimeIndex(sorted(exp["date"]))
    for t in days[(days >= file_days.min()) & (days <= file_days.max())]:
        pos = days.searchsorted(t) - 1
        if pos < 0:
            continue
        prev = days[pos]
        if prev not in by_date:
            continue
        nxt = exp_days[exp_days.searchsorted(t)] if exp_days.searchsorted(t) < len(exp_days) else None
        if nxt is None:
            continue
        g = by_date[prev]
        g = g[g["exp_day"] == nxt]
        if g.empty or g["oi"].sum() <= 0:
            continue
        k = g.loc[g["oi"].idxmax(), "strike"]
        dte = int(days.searchsorted(nxt) - days.searchsorted(t))
        rows.append({"date": t, "expiry": nxt, "kstar": float(k), "days_to_expiry": dte})
    return pd.DataFrame(rows)


def pin_moves(prices: pd.DataFrame, strikes: pd.DataFrame) -> pd.DataFrame:
    """Distance (in %) of the open and of the close from the max-OI strike, and the change.

    `move` < 0 means the index ended the day closer to the strike than it opened.
    """
    p = prices[["Open", "Close"]].copy()
    p.index = pd.DatetimeIndex(p.index).normalize()
    d = strikes.merge(p, left_on="date", right_index=True, how="inner")
    d["dist_open"] = 100 * np.abs(np.log(d["Open"] / d["kstar"]))
    d["dist_close"] = 100 * np.abs(np.log(d["Close"] / d["kstar"]))
    d["move"] = d["dist_close"] - d["dist_open"]
    return d


def pin_tests(moves: pd.DataFrame) -> pd.DataFrame:
    """Expiry day (0 sessions to expiry) vs. other days: change in distance to the max-OI strike,
    controlling for the distance at the open (far-away opens tend to drift either way)."""
    d = moves.copy()
    d["expiry_day"] = (d["days_to_expiry"] == 0).astype(int)
    d["dist_open_x"] = d["dist_open"]
    _ = _calendar_columns(d)
    rows = []
    for name, s in d.groupby("index"):
        r = fe_ols(s, "move", ["expiry_day", "dist_open_x"], (("wd",), ("year",)))
        t = r.table().loc["expiry_day"]
        rows.append({"index": name, "coef": t["coef"], "se": t["se"], "p": t["p"],
                     "mean_move_expiry": s.loc[s.expiry_day == 1, "move"].mean(),
                     "mean_move_other": s.loc[s.expiry_day == 0, "move"].mean(),
                     "mean_close_dist_expiry": s.loc[s.expiry_day == 1, "dist_close"].mean(),
                     "mean_close_dist_other": s.loc[s.expiry_day == 0, "dist_close"].mean(),
                     "share_closer_expiry": (s.loc[s.expiry_day == 1, "move"] < 0).mean(),
                     "share_closer_other": (s.loc[s.expiry_day == 0, "move"] < 0).mean(),
                     "n_expiry": int(s["expiry_day"].sum()), "n": r.nobs})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------ option activity
def option_activity(index: str, table: pd.DataFrame, trading_days, data_dir="data",
                    years=range(2014, 2027)) -> pd.DataFrame:
    """Per trading day: option contracts traded in total and in the series expiring that day."""
    symbol = OPTION_SYMBOL[index]
    opt = load_options_eod(symbol, years, data_dir, columns=("date", "expiry", "volume"))
    days = pd.DatetimeIndex(sorted(pd.to_datetime(trading_days)))
    exp = ex.expiry_dates(symbol, days)
    label_to_day = {**dict(zip(exp["scheduled"], exp["date"])),
                    **{d: d for d in exp["date"]}}      # NSE sometimes relabels a series to its actual day
    opt["exp_day"] = opt["expiry"].map(label_to_day)
    tot = opt.groupby("date")["volume"].sum()
    same = opt[opt["exp_day"] == opt["date"]].groupby("date")["volume"].sum()
    out = pd.DataFrame({"total": tot, "expiring": same.reindex(tot.index).fillna(0.0)})
    out["share_expiring"] = out["expiring"] / out["total"]
    out["index"] = index
    return out.rename_axis("date").reset_index()


# ------------------------------------------------------------------------ closing auction (early look)
def load_hourly(index: str, data_dir="data", refresh: bool = False) -> pd.DataFrame:
    """Hourly Yahoo bars (only the last 730 days are available from Yahoo), cached in data/."""
    from pathlib import Path

    from .data import TICKERS
    path = Path(data_dir) / f"hourly_{index}.csv"
    if refresh or not path.exists():
        import yfinance as yf
        start = (pd.Timestamp.today() - pd.Timedelta(days=729)).strftime("%Y-%m-%d")
        h = yf.download(TICKERS[index], start=start, end="2026-10-01", interval="60m",
                        progress=False, auto_adjust=False, threads=False)
        if isinstance(h.columns, pd.MultiIndex):
            h.columns = h.columns.get_level_values(0)
        h = h[["Open", "High", "Low", "Close"]].dropna()
        h.index = pd.to_datetime(h.index)
        if h.index.tz is not None:
            h.index = h.index.tz_convert("Asia/Kolkata").tz_localize(None)
        h.to_csv(path)
    h = pd.read_csv(path, index_col=0)
    h.index = pd.to_datetime(h.index)
    return h


def closing_auction_look(table: pd.DataFrame, data_dir="data", cas_date: str = "2026-08-03") -> pd.DataFrame:
    """Expiry effect on the range of the last hourly bar (15:15-15:30) before and after the
    closing auction session started. Only about two months of data after the change: an
    early look with little statistical power."""
    rows = []
    for index in MINUTE_INDICES:
        h = load_hourly(index, data_dir)
        last = h[h.index.strftime("%H:%M") == "15:15"].copy()
        last.index = last.index.normalize()
        d = pd.DataFrame({"lp": np.log(1e4 * np.log(last["High"] / last["Low"]) ** 2 + FLOOR)}, index=last.index)
        d = d.join(ex.expiry_flags(table, index), how="inner")
        d["index"] = index
        rows.append(d)
    d = pd.concat(rows).rename_axis("date").reset_index()
    d = _calendar_columns(d)
    d["post"] = (d["date"] >= pd.Timestamp(cas_date)).astype(int)
    d["own_x_post"] = d["own"] * d["post"]
    d["other_x_post"] = d["other_major"] * d["post"]
    out = []
    r = fe_ols(d, "lp", ["own", "other_major", "own_x_post", "other_x_post"], MAIN_FE)
    out.append(r.table().assign(sample="pooled", n=r.nobs, post_days=int(d["post"].sum()),
                                post_expiries=int((d["own"] * d["post"]).sum())))
    for idx, s in d.groupby("index"):
        r = fe_ols(s, "lp", ["own", "other_major", "own_x_post"], (("wd",), ("week",)))
        out.append(r.table().assign(sample=idx, n=r.nobs, post_days=int(s["post"].sum()),
                                    post_expiries=int((s["own"] * s["post"]).sum())))
    return pd.concat(out).rename_axis("term").reset_index()
