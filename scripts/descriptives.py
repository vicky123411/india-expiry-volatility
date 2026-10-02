"""Descriptive statistics for the manuscript (Table 2): returns and volatility measures by index,
with augmented Dickey-Fuller tests. Writes results/descriptive_stats.csv and
paper/tables/descriptives.tex.

    python scripts/descriptives.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import adfuller

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from expiryvol import data, expiries as ex, mechanisms as me  # noqa: E402
from expiryvol.features import build_panel  # noqa: E402

LABEL = {"nifty50": "Nifty 50", "banknifty": "Bank Nifty", "sensex": "Sensex", "midcap50": "Midcap 50"}


def main():
    prices, _ = data.load_all_daily(ROOT / "data")
    td = data.trading_days("2013-06-03", data.DATA_END)
    table = ex.expiry_table(td)
    panel = build_panel(prices, table, data.INDICES, data.STUDY_START, data.STUDY_END)
    mdays, _ = me.minute_panels(table, ROOT / "data", end=data.STUDY_END)
    rows = []
    for idx in data.INDICES:
        p = panel[panel["index"] == idx].sort_values("date")
        r = p["ret"].dropna()
        row = {"index": idx, "days": len(p), "ret_mean": r.mean(), "ret_sd": r.std(),
               "ret_skew": stats.skew(r), "ret_kurt": stats.kurtosis(r, fisher=False),
               "lgk_mean": p["lgk"].mean(), "lgk_sd": p["lgk"].std(),
               "adf_lgk": adfuller(p["lgk"].dropna(), autolag="AIC")[0],
               "adf_lgk_p": adfuller(p["lgk"].dropna(), autolag="AIC")[1],
               "lgk_expiry": p.loc[p["own"] == 1, "lgk"].mean(), "lgk_other": p.loc[p["own"] == 0, "lgk"].mean()}
        m = mdays[mdays["index"] == idx]
        if len(m):
            share = m["rv_last"] / m["rv5"]
            row.update({"min_days": len(m),
                        "last30_share_expiry": share[m["own"] == 1].median(),
                        "last30_share_other": share[m["own"] == 0].median(),
                        "lrv_last_mean": m["lrv_last"].mean(),
                        "adf_lrv_last": adfuller(m.sort_values("date")["lrv_last"], autolag="AIC")[0],
                        "adf_lrv_last_p": adfuller(m.sort_values("date")["lrv_last"], autolag="AIC")[1]})
        rows.append(row)
    d = pd.DataFrame(rows)
    d.to_csv(ROOT / "results" / "descriptive_stats.csv", index=False)

    def f(v, fmt):
        return "--" if pd.isna(v) else format(v, fmt)
    lines = ["\\begin{tabular}{lrrrr}", "\\toprule",
             " & " + " & ".join(LABEL[i] for i in data.INDICES) + " \\\\", "\\midrule",
             "\\multicolumn{5}{l}{\\emph{Daily data, Jan 2014 -- Jul 2026}} \\\\"]
    spec = [("Trading days", "days", "d"), ("Mean daily return (\\%)", "ret_mean", ".3f"),
            ("Std.\\ dev.\\ of return (\\%)", "ret_sd", ".3f"), ("Skewness", "ret_skew", ".2f"),
            ("Kurtosis", "ret_kurt", ".2f"), ("Mean log GK variance", "lgk_mean", ".3f"),
            ("Std.\\ dev.\\ log GK variance", "lgk_sd", ".3f"),
            ("\\quad on own expiry days (mean)", "lgk_expiry", ".3f"), ("\\quad on other days (mean)", "lgk_other", ".3f"),
            ("ADF statistic, log GK", "adf_lgk", ".2f")]
    for lab, col, fmt in spec:
        lines.append(lab + " & " + " & ".join(f(r[col], fmt) for _, r in d.iterrows()) + " \\\\")
    lines.append("\\midrule")
    lines.append("\\multicolumn{5}{l}{\\emph{One-minute data, 2021 -- Jul 2026}} \\\\")
    spec2 = [("Trading days", "min_days", ".0f"),
             ("Last-30-min share of session variance, own expiry days (median)", "last30_share_expiry", ".3f"),
             ("\\quad other days (median)", "last30_share_other", ".3f"),
             ("ADF statistic, log last-30-min variance", "adf_lrv_last", ".2f")]
    for lab, col, fmt in spec2:
        lines.append(lab + " & " + " & ".join(f(r.get(col, np.nan), fmt) for _, r in d.iterrows()) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    (ROOT / "paper" / "tables" / "descriptives.tex").write_text("\n".join(lines))
    print(d.round(3).T.to_string())


if __name__ == "__main__":
    main()
