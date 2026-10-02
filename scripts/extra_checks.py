"""Additional checks requested in review (written to results/extra_checks.csv):

1. Stacked event study with a control for other large indices' expiries.
2. Settlement-window effect leaving out one index at a time.
3. Settlement-window variance from 5-minute returns (less sensitive to microstructure noise).
4. Dose-response: does the settlement-window effect grow with expiry-day option trading?
5. Mean (not only median) share of session variance in 15:00-15:30.

    python scripts/extra_checks.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from expiryvol import data, estimate as es, expiries as ex, mechanisms as me  # noqa: E402


def rv5_last(m: pd.DataFrame) -> pd.Series:
    """Realized variance of 5-minute returns from 15:00 to 15:30 (close of 14:59 bar to 15:29 close)."""
    lp = np.log(m["Close"])
    clock = m.index.strftime("%H:%M")
    keep = lp[(clock == "14:59") | ((clock >= "15:04") & (m.index.minute % 5 == 4))]
    r = keep.groupby(m.loc[keep.index, "day"]).diff()
    return (1e4 * r ** 2).groupby(m.loc[r.index, "day"]).sum()


def main():
    td = data.trading_days("2013-06-03", data.DATA_END)
    table = ex.expiry_table(td)
    mdays, _ = me.minute_panels(table, ROOT / "data", end=data.STUDY_END)
    rows = []

    major = [e for e in ex.EVENTS if e.major and e.index in me.MINUTE_INDICES and pd.Timestamp(e.date) >= pd.Timestamp("2021-12-01")]
    for y in ["lrv_last", "lrv5"]:
        for ctrl, lab in [((), "no control"), (("other_major",), "+ other large index expires")]:
            t = es.stacked_events(mdays, major, y, controls=ctrl)
            for _, r in t.iterrows():
                rows.append({"check": f"stacked events, {lab}", "outcome": y, "term": r["term"], **r[["coef", "se", "p"]].to_dict(), "n": r["n"]})

    for drop in me.MINUTE_INDICES:
        sub = mdays[mdays["index"] != drop]
        r = es.fe_ols(sub, "lrv_last", es.TREAT, es.MAIN_FE, drop_absorbed=True)
        for term in ["own_weekly", "own_monthly"]:
            rows.append({"check": f"leave out {drop}", "outcome": "lrv_last", "term": term, **r.table().loc[term, ["coef", "se", "p"]].to_dict(), "n": r.nobs})

    parts = []
    for idx in me.MINUTE_INDICES:
        m = data.load_minute(idx, ROOT / "data")
        m = m[m["day"] <= pd.Timestamp(data.STUDY_END)]
        parts.append(pd.DataFrame({"date": rv5_last(m).index, "rv5_last": rv5_last(m).to_numpy(), "index": idx}))
    d5 = mdays.merge(pd.concat(parts), on=["date", "index"], how="left")
    d5["lrv5_last"] = np.log(d5["rv5_last"] + me.FLOOR)
    r = es.fe_ols(d5, "lrv5_last", es.TREAT, es.MAIN_FE)
    for term in ["own_weekly", "own_monthly", "other_major"]:
        rows.append({"check": "settlement window from 5-minute returns", "outcome": "lrv5_last", "term": term,
                     **r.table().loc[term, ["coef", "se", "p"]].to_dict(), "n": r.nobs})

    # dose-response (Nifty 50 and Bank Nifty, which have option files)
    acts = []
    for idx in ["nifty50", "banknifty"]:
        a = me.option_activity(idx, table, td, ROOT / "data")
        acts.append(a[["date", "expiring", "index"]])
    acts = pd.concat(acts)
    dd = mdays[mdays["index"].isin(["nifty50", "banknifty"])].merge(acts, on=["date", "index"], how="left")
    dd = dd[dd["date"] <= pd.Timestamp("2026-06-29")]
    dd["lexp"] = np.where(dd["own"] == 1, np.log1p(dd["expiring"].fillna(0)), np.nan)
    mu = dd.groupby("index")["lexp"].transform("mean")
    sd = dd.groupby("index")["lexp"].transform("std")
    dd["own_x_volume"] = np.where(dd["own"] == 1, (dd["lexp"] - mu) / sd, 0.0)
    r = es.fe_ols(dd, "lrv_last", ["own", "own_x_volume", "other_major"], es.MAIN_FE)
    for term in ["own", "own_x_volume"]:
        rows.append({"check": "dose-response: own expiry x expiring-series contracts (std.)", "outcome": "lrv_last", "term": term,
                     **r.table().loc[term, ["coef", "se", "p"]].to_dict(), "n": r.nobs})

    share = mdays.assign(share=mdays["rv_last"] / mdays["rv5"])
    for idx, g in share.groupby("index"):
        rows.append({"check": "mean share of session variance in 15:00-15:30", "outcome": idx, "term": "own expiry days",
                     "coef": g.loc[g["own"] == 1, "share"].mean(), "se": np.nan, "p": np.nan, "n": int((g["own"] == 1).sum())})
        rows.append({"check": "mean share of session variance in 15:00-15:30", "outcome": idx, "term": "other days",
                     "coef": g.loc[g["own"] == 0, "share"].mean(), "se": np.nan, "p": np.nan, "n": int((g["own"] == 0).sum())})
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "results" / "extra_checks.csv", index=False)
    print(out.round(4).to_string())


if __name__ == "__main__":
    main()
