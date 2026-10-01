"""Volatility measures and the analysis panel.

All variances are in %^2 (a daily variance of 1.0 means a typical move of about 1%).

Daily measures from Open (O), High (H), Low (L) and previous Close (Cp):
    gk    Garman-Klass (1980) variance of the trading session, 09:15-15:30:
          0.5 (ln H - ln L)^2 - (2 ln 2 - 1)(ln C - ln O)^2
    park  Parkinson (1980) range variance: (ln H - ln L)^2 / (4 ln 2)
    rs    Rogers-Satchell (1991) variance (robust to a drift during the day)
    oc    squared open-to-close return
    on    squared overnight gap (ln O - ln Cp)^2
    rv    on + gk: the whole day's variance, close to close (paper 1's target)
The main outcome is log(gk): logs turn the very skewed variance into a near-normal number,
and a change of 0.10 in log variance is a change of about 10% in variance (5% in volatility).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .expiries import expiry_flags

GK_C = 2 * np.log(2) - 1
ON_FLOOR = 0.0025   # added before taking logs of the overnight gap, which is sometimes exactly 0


def daily_measures(ohlc: pd.DataFrame) -> pd.DataFrame:
    """Daily return and volatility measures (in % units) from clean daily bars."""
    o, h, l, c = (np.log(ohlc[col]) for col in ["Open", "High", "Low", "Close"])
    cp = c.shift(1)
    out = pd.DataFrame(index=ohlc.index)
    out["close"] = ohlc["Close"]
    out["open"] = ohlc["Open"]
    out["ret"] = 100 * (c - cp)
    out["ret_on"] = 100 * (o - cp)            # overnight gap
    out["ret_oc"] = 100 * (c - o)             # during the session
    out["gk"] = 1e4 * (0.5 * (h - l) ** 2 - GK_C * (c - o) ** 2)
    out["park"] = 1e4 * (h - l) ** 2 / (4 * np.log(2))
    out["rs"] = 1e4 * ((h - c) * (h - o) + (l - c) * (l - o))
    out["oc"] = 1e4 * (c - o) ** 2
    out["on"] = 1e4 * (o - cp) ** 2
    out["rv"] = out["on"] + out["gk"]
    out["range"] = 100 * (h - l)
    return out


def log_measures(m: pd.DataFrame) -> pd.DataFrame:
    """Log versions of the variance measures (the regression outcomes)."""
    out = pd.DataFrame(index=m.index)
    out["lgk"] = np.log(m["gk"])
    out["lpark"] = np.log(m["park"])
    out["lrs"] = np.log(m["rs"].clip(lower=1e-6))
    out["loc"] = np.log(m["oc"] + ON_FLOOR)
    out["lon"] = np.log(m["on"] + ON_FLOOR)
    out["lrv"] = np.log(m["rv"])
    out["labs"] = np.log(np.abs(m["ret"]) + 0.05)
    return out


def har_controls(lv: pd.Series) -> pd.DataFrame:
    """Recent volatility of the same index (known before the day starts):
    yesterday's, last week's and last month's average log variance."""
    out = pd.DataFrame(index=lv.index)
    out["h_d"] = lv.shift(1)
    out["h_w"] = lv.shift(1).rolling(5, min_periods=4).mean()
    out["h_m"] = lv.shift(1).rolling(22, min_periods=18).mean()
    return out


def build_panel(prices: dict[str, pd.DataFrame], table: pd.DataFrame, indices,
                start: str, end: str) -> pd.DataFrame:
    """Long table: one row per (index, trading day) with outcomes, expiry flags and controls.

    `table` is expiries.expiry_table(...) on the full trading calendar.
    """
    rows = []
    for index in indices:
        m = daily_measures(prices[index])
        lm = log_measures(m)
        frame = pd.concat([m, lm, har_controls(lm["lgk"])], axis=1)
        full = expiry_flags(table, index)
        # the day before / after an own expiry, on the exchange calendar
        full["own_before"] = full["own"].shift(-1).fillna(0).astype(int)
        full["own_after"] = full["own"].shift(1).fillna(0).astype(int)
        flags = full.reindex(frame.index)
        frame = frame.join(flags)
        frame["index"] = index
        rows.append(frame.loc[start:end])
    panel = pd.concat(rows).rename_axis("date").reset_index()
    panel = panel.dropna(subset=["lgk", "own"])
    days = pd.DatetimeIndex(panel["date"])
    panel["wd"] = days.weekday
    iso = days.isocalendar()
    panel["week"] = (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()
    panel["month"] = days.to_period("M").astype(str)
    panel["year"] = days.year
    # sessions since the previous trading day (1 normally, 3 after a weekend, more after holidays)
    cal = pd.Series(table.index, index=table.index)
    gap = (cal - cal.shift(1)).dt.days
    panel["gap_days"] = gap.reindex(days).to_numpy()
    nxt = (cal.shift(-1) - cal).dt.days
    panel["next_gap"] = nxt.reindex(days).to_numpy()
    # the session before / after an exchange holiday (weekends don't count)
    panel["pre_holiday"] = (panel["next_gap"] > np.where(panel["wd"] == 4, 3, 1)).astype(int)
    panel["post_holiday"] = (panel["gap_days"] > np.where(panel["wd"] == 0, 3, 1)).astype(int)
    return panel.reset_index(drop=True)


# ------------------------------------------------------------------------ one-minute data
def minute_day_measures(m: pd.DataFrame, step: int = 5) -> pd.DataFrame:
    """Per-day measures from one-minute bars of the regular session.

    rv5      realized variance from `step`-minute returns, 09:15-15:29 (in %^2)
    r_am     return 09:15 -> 12:30 (open of the first bar to close of the 12:29 bar), %
    r_pm     return 12:30 -> 15:29, %
    r_rest   return 09:15 -> 15:00, %   (used for the intraday-momentum test)
    r_last   return 15:00 -> 15:29, %   (the last half hour)
    rv_last  realized variance of the last half hour from one-minute returns
    """
    px = m["Close"]
    day = m["day"]
    lp = np.log(px)
    out = {}
    for d, g in lp.groupby(day):
        clock = g.index.strftime("%H:%M")
        first_open = np.log(m.loc[g.index[0], "Open"])
        grid = g[(g.index.minute % step == (step - 1) % step)]                  # closes of :14, :19, ... bars
        grid = pd.concat([pd.Series([first_open], index=[g.index[0] - pd.Timedelta(minutes=1)]), grid])
        r = np.diff(grid.to_numpy())
        at = lambda hm: g[clock <= hm].iloc[-1] if (clock <= hm).any() else np.nan   # noqa: E731
        p1230, p1500, close = at("12:29"), at("14:59"), g.iloc[-1]
        last = g[clock >= "14:59"]
        out[d] = {"rv5": 1e4 * np.sum(r ** 2),
                  "r_am": 100 * (p1230 - first_open), "r_pm": 100 * (close - p1230),
                  "r_rest": 100 * (p1500 - first_open), "r_last": 100 * (close - p1500),
                  "rv_last": 1e4 * np.sum(np.diff(last.to_numpy()) ** 2)}
    return pd.DataFrame.from_dict(out, orient="index").rename_axis("date")


def minute_segments(m: pd.DataFrame, minutes: int = 15) -> pd.DataFrame:
    """Realized variance (from one-minute returns) in each `minutes`-long slice of the session.

    Returns a long table: date, segment start time (e.g. "15:15"), rv (in %^2).
    """
    lp = np.log(m["Close"])
    r = lp.groupby(m["day"]).diff()                       # one-minute returns within the day
    first = np.log(m["Close"]) - np.log(m["Open"])        # the first bar's own move
    r = r.fillna(first)
    start = m.index.normalize() + pd.Timedelta(hours=9, minutes=15)
    slot = ((m.index - start).total_seconds() // (60 * minutes)).astype(int)
    df = pd.DataFrame({"date": m["day"].to_numpy(), "slot": slot.to_numpy(), "r2": (1e4 * r ** 2).to_numpy()})
    seg = df.groupby(["date", "slot"], as_index=False)["r2"].sum().rename(columns={"r2": "rv"})
    seg["start"] = [(pd.Timestamp("09:15") + pd.Timedelta(minutes=minutes * s)).strftime("%H:%M") for s in seg["slot"]]
    return seg


def distance_to_grid(level, step: float) -> np.ndarray:
    """Distance of an index level to the nearest multiple of `step`, as a share of `step`
    (0 = exactly on a strike, 0.5 = halfway between two strikes)."""
    x = np.asarray(level, dtype=float) / step
    return np.abs(x - np.round(x))
