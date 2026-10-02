"""Build the manuscript's tables (Markdown) from the result files in results/.

Every number in the tables comes from results/*.csv, so the manuscript can be rebuilt after
scripts/run_all.py without retyping anything.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from expiryvol import expiries as ex  # noqa: E402

RES = ROOT / "results"
OUT = Path(__file__).resolve().parent / "tables"
OUT.mkdir(exist_ok=True)
LABEL = {"pooled": "All", "nifty50": "Nifty 50", "banknifty": "Bank Nifty", "sensex": "Sensex", "midcap50": "Midcap 50"}
MINUS = "−"


def stars(p):
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.10 else ""


def num(x, d=3):
    s = f"{x:.{d}f}"
    return s.replace("-", MINUS) if x < 0 else s


def cell(coef, se, p, d=3):
    return f"{num(coef, d)}{stars(p)} ({se:.{d}f})"


def pct(b):
    return 100 * (np.exp(b) - 1)


def sep(widths, align):
    """Pipe-table separator whose dash counts set the relative column widths."""
    parts = []
    for w, a in zip(widths, align):
        d = "-" * max(3, w)
        parts.append(d[:-1] + ":" if a == "r" else d)
    return "|" + "|".join(parts) + "|"


CELL = re.compile(r"^(?P<c>.*?) \((?P<se>\d+\.\d+)\)(?P<tail>(\^a\^)?( \[\d+\])?)$")


def split_se(lines):
    """Put standard errors on their own row under the coefficients (finance-journal style)."""
    out = lines[:2]
    for line in lines[2:]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not any(CELL.match(c) for c in cells[1:]):
            out.append(line)
            continue
        top, bot = [cells[0]], [""]
        for c in cells[1:]:
            m = CELL.match(c)
            if m:
                top.append(m.group("c") + m.group("tail"))
                bot.append(f"({m.group('se')})")
            else:
                top.append(c)
                bot.append("")
        out.append("| " + " | ".join(top) + " |")
        out.append("| " + " | ".join(bot) + " |")
    return out


def write(name, text, widths=None, split=True):
    lines = text.strip().split("\n")
    if split:
        lines = split_se(lines)
    if widths:
        ncol = lines[0].count("|") - 1
        align = ["l"] + ["r" if c.endswith(":") else "l" for c in lines[1].strip("|").split("|")][1:]
        lines[1] = sep(widths, align)
    (OUT / f"{name}.md").write_text("\n".join(lines) + "\n")


def table_events_list():
    rows = ["| Index (option product) | Change | Effective | Weekday gaining an expiry | Weekday losing an expiry |",
            "|---|---|---|---|---|"]
    for e in ex.EVENTS:
        if not e.major:
            continue
        idx = LABEL[e.index]
        g = ", ".join(ex.WEEKDAY_NAMES[i] for i in e.gain) or "–"
        lo = ", ".join(ex.WEEKDAY_NAMES[i] for i in e.lose) or "–"
        shown = {"Sensex Fri to Tue": "01 Jan 2025"}.get(e.name, f"{pd.Timestamp(e.date):%d %b %Y}")
        rows.append(f"| {idx} | {e.name} | {shown} | {g} | {lo} |")
    write("t1_events", "\n".join(rows), [14, 30, 13, 12, 12])


def table_descriptives():
    d = pd.read_csv(RES / "descriptive_stats.csv").set_index("index")
    cols = ["nifty50", "banknifty", "sensex", "midcap50"]
    spec = [("*Daily data, Jan 2014 – Jul 2026*", None, None),
            ("Trading days", "days", "{:,.0f}"),
            ("Mean daily return (%)", "ret_mean", "{:.3f}"),
            ("Standard deviation of return (%)", "ret_sd", "{:.3f}"),
            ("Skewness", "ret_skew", "{:.2f}"),
            ("Kurtosis", "ret_kurt", "{:.2f}"),
            ("Mean log Garman–Klass variance", "lgk_mean", "{:.3f}"),
            ("  on own expiry days", "lgk_expiry", "{:.3f}"),
            ("  on other days", "lgk_other", "{:.3f}"),
            ("ADF statistic, log Garman–Klass variance", "adf_lgk", "{:.2f}"),
            ("*One-minute data, May 2021 (Sensex: Sep 2022) – Jul 2026*", None, None),
            ("Trading days", "min_days", "{:,.0f}"),
            ("Share of session variance in 15:00–15:30, own expiry days (median)", "last30_share_expiry", "{:.3f}"),
            ("  other days (median)", "last30_share_other", "{:.3f}"),
            ("ADF statistic, log 15:00–15:30 variance", "adf_lrv_last", "{:.2f}")]
    rows = ["| | Nifty 50 | Bank Nifty | Sensex | Midcap 50 |", "|---|---:|---:|---:|---:|"]
    for lab, col, fmt in spec:
        if col is None:
            rows.append(f"| {lab} | | | | |")
            continue
        vals = []
        for c in cols:
            v = d.loc[c, col] if col in d.columns else np.nan
            vals.append("–" if pd.isna(v) else fmt.format(v).replace("-", MINUS))
        rows.append(f"| {lab.replace('  ', '    ')} | " + " | ".join(vals) + " |")
    write("t2_descriptives", "\n".join(rows), [44, 11, 11, 11, 11])


def table_main():
    daily = pd.read_csv(RES / "main_lgk.csv")
    mins = pd.read_csv(RES / "minute_day_effects.csv")
    terms = [("own_weekly", "Own weekly expiry"), ("own_monthly", "Own monthly expiry"),
             ("other_major", "Another large index expires")]
    rows = ["| | All indices | Nifty 50 | Bank Nifty | Sensex | Midcap 50 |", "|---|---:|---:|---:|---:|---:|",
            "| ***Panel A: Whole session (daily range), 2014–2026*** | | | | | |"]
    for t, lab in terms:
        cells = []
        for s in ["pooled", "nifty50", "banknifty", "sensex", "midcap50"]:
            r = daily[(daily["sample"] == s) & (daily["term"] == t)].iloc[0]
            cells.append(cell(r.coef, r.se, r.p))
        rows.append(f"| {lab} | " + " | ".join(cells) + " |")
    nrow = [f"{int(daily[(daily['sample'] == s)]['n'].iloc[0]):,}" for s in ["pooled", "nifty50", "banknifty", "sensex", "midcap50"]]
    rows.append("| Observations | " + " | ".join(nrow) + " |")
    for outcome, title in [("lrv5", "Panel B: Whole session (5-min realized variance), 2021–2026"),
                           ("lrv_last", "Panel C: Settlement window 15:00–15:30, 2021–2026")]:
        rows.append(f"| ***{title}*** | | | | | |")
        for t, lab in terms:
            cells = []
            for s in ["pooled", "nifty50", "banknifty", "sensex"]:
                r = mins[(mins["outcome"] == outcome) & (mins["sample"] == s) & (mins["term"] == t)].iloc[0]
                cells.append(cell(r.coef, r.se, r.p))
            rows.append(f"| {lab} | " + " | ".join(cells) + " | – |")
        nrow = [f"{int(mins[(mins['outcome'] == outcome) & (mins['sample'] == s)]['n'].iloc[0]):,}" for s in ["pooled", "nifty50", "banknifty", "sensex"]]
        rows.append("| Observations | " + " | ".join(nrow) + " | – |")
    write("t3_main", "\n".join(rows), [32, 13, 13, 13, 13, 13])


def table_events():
    ev = pd.read_csv(RES / "event_did.csv")
    st = pd.read_csv(RES / "event_stacked.csv")
    rows = ["| Calendar change | Effective | Whole session: new weekday | Whole session: old weekday | 15:00–15:30: new weekday | 15:00–15:30: old weekday |",
            "|---|---|---:|---:|---:|---:|"]

    def get(name, outcome, term):
        r = ev[(ev["event"] == name) & (ev["outcome"] == outcome) & (ev["term"] == term)]
        return "–" if r.empty else cell(r.iloc[0].coef, r.iloc[0].se, r.iloc[0].p, 2)
    for e in ex.EVENTS:
        if not e.major:
            continue
        rows.append(f"| {e.name} | {pd.Timestamp(e.date):%b %Y} | {get(e.name, 'lgk', 'gain_post')} | {get(e.name, 'lgk', 'lose_post')} | "
                    f"{get(e.name, 'lrv_last', 'gain_post')} | {get(e.name, 'lrv_last', 'lose_post')} |")

    def sget(design, term):
        r = st[(st["design"] == design) & (st["term"] == term)].iloc[0]
        return cell(r.coef, r.se, r.p, 2)
    rows.append(f"| *Stacked, 8 changes (daily range)* | | {sget('8 major events, daily range', 'gain_post')} | {sget('8 major events, daily range', 'lose_post')} | | |")
    rows.append(f"| *Stacked, 6 changes with minute data* | | {sget('6 events, whole session (5-min RV)', 'gain_post')}^a^ | "
                f"{sget('6 events, whole session (5-min RV)', 'lose_post')}^a^ | {sget('6 events, last 30 minutes', 'gain_post')} | {sget('6 events, last 30 minutes', 'lose_post')} |")
    write("t4_events", "\n".join(rows), [26, 9, 13, 13, 13, 13])


def table_robust():
    rd = pd.read_csv(RES / "robustness_lgk.csv")
    rl = pd.read_csv(RES / "robustness_last30.csv")
    ri = pd.read_csv(RES / "randomization_inference.csv")
    specs = ["Baseline", "+ weekday x year effects", "+ date effects (cross-index)", "Driscoll-Kraay errors",
             "+ holiday controls", "+ day before / after own expiry", "Without 2020", "From 2017",
             "Minus Midcap 50 on the same day", "Last 15 minutes only (15:15-15:30)", "Just before the window (14:45-15:00)"]
    names = {"+ weekday x year effects": "+ weekday × year fixed effects", "+ date effects (cross-index)": "+ date fixed effects (comparison across indices)",
             "Driscoll-Kraay errors": "Driscoll–Kraay standard errors", "+ day before / after own expiry": "+ day before and after own expiry",
             "Minus Midcap 50 on the same day": "Outcome relative to Midcap 50 on the same day",
             "Last 15 minutes only (15:15-15:30)": "Last 15 minutes only (15:15–15:30)",
             "Just before the window (14:45-15:00)": "Quarter-hour before the window (14:45–15:00)"}
    rows = ["| Specification | Whole session: weekly | Whole session: monthly | 15:00–15:30: weekly | 15:00–15:30: monthly |",
            "|---|---:|---:|---:|---:|"]

    def g(df, spec, term):
        r = df[(df["spec"] == spec) & (df["term"] == term)]
        return "–" if r.empty else cell(r.iloc[0].coef, r.iloc[0].se, r.iloc[0].p)
    for s in specs:
        rows.append(f"| {names.get(s, s)} | {g(rd, s, 'own_weekly')} | {g(rd, s, 'own_monthly')} | {g(rl, s, 'own_weekly')} | {g(rl, s, 'own_monthly')} |")
    p = {(r.outcome, r.term): r.ri_p for r in ri.itertuples()}
    rows.append(f"| Randomization *p*-value, 1,000 placebo calendars | {p[('lgk', 'own_weekly')]:.3f} | {p[('lgk', 'own_monthly')]:.3f} | "
                f"{p[('lrv_last', 'own_weekly')]:.3f} | {p[('lrv_last', 'own_monthly')]:.3f} |")
    write("t5_robust", "\n".join(rows), [34, 14, 14, 14, 14])


# ------------------------------------------------------------------ supplementary tables
def supp_tables():
    rt = ex.rules_table()
    rows = ["| Product | From | Weekly | Monthly | Note |", "|---|---|---|---|---|"]
    for r in rt.itertuples():
        frm = r._2 if r._2 != "2000-01-01" else "before 2014"
        rows.append(f"| {r.product} | {frm} | {r.weekly} | {r.monthly} | {r.note} |")
    write("s1_rules", "\n".join(rows), [11, 11, 7, 9, 50])

    alt = pd.read_csv(RES / "alt_outcomes.csv")
    outs = list(dict.fromkeys(alt["outcome"]))
    rows = ["| | " + " | ".join(outs) + " |", "|---|" + "---:|" * len(outs)]
    for t, lab in [("own_weekly", "Own weekly expiry"), ("own_monthly", "Own monthly expiry"),
                   ("other_major", "Another large index expires"), ("other_minor", "Small index expires")]:
        rows.append(f"| {lab} | " + " | ".join(cell(*alt[(alt.outcome == o) & (alt.term == t)][["coef", "se", "p"]].iloc[0]) for o in outs) + " |")
    write("s2_alt", "\n".join(rows))

    g = pd.read_csv(RES / "pinning_grid.csv")
    rows = ["| Index | Strike step | Share near a strike: expiry days | Other days | Weekly expiry coefficient | Monthly expiry coefficient |",
            "|---|---:|---:|---:|---:|---:|"]
    for r in g.itertuples():
        from scipy.stats import norm
        pw, pm = 2 * norm.sf(abs(r.coef_weekly / r.se_weekly)), 2 * norm.sf(abs(r.coef_monthly / r.se_monthly))
        rows.append(f"| {LABEL[r.index]} | {r.step} | {r.share_expiry:.3f} | {r.share_other:.3f} | {cell(r.coef_weekly, r.se_weekly, pw)} | {cell(r.coef_monthly, r.se_monthly, pm)} |")
    m = pd.read_csv(RES / "pinning_maxoi.csv")
    rows2 = ["| Index | Expiry days | Mean move, expiry days (%) | Mean move, other days (%) | Difference, controlling for distance at open |",
             "|---|---:|---:|---:|---:|"]
    for r in m.itertuples():
        rows2.append(f"| {LABEL[r.index]} | {r.n_expiry} | {r.mean_move_expiry:.3f} | {r.mean_move_other:.3f} | {cell(r.coef, r.se, r.p)} |")
    write("s3_pinning", "\n".join(rows) + "\n\n" + "\n".join(rows2))

    rev = pd.read_csv(RES / "reversal.csv")
    rows = ["| Sample | Afternoon on morning × expiry | Last half hour on rest of day × expiry | Days |", "|---|---:|---:|---:|"]
    for s in ["pooled", "nifty50", "banknifty", "sensex", "banknifty 2023-01..2025-03"]:
        a = rev[(rev["sample"] == s) & (rev["term"] == "am_x_own")].iloc[0]
        b = rev[(rev["sample"] == s) & (rev["term"] == "rest_x_own")].iloc[0]
        lab = LABEL.get(s, "Bank Nifty, Jan 2023 – Mar 2025")
        rows.append(f"| {lab} | {cell(a.coef, a.se, a.p)} | {cell(b.coef, b.se, b.p)} | {int(a.n):,} |")
    write("s4_reversal", "\n".join(rows))

    pe = pd.read_csv(RES / "period_effects.csv")
    sub = pe[(pe["outcome"] == "lrv_last") & (pe["sample"] == "pooled")]
    rows = ["| Period | Own weekly | Own monthly | Another large index |", "|---|---:|---:|---:|"]
    for per in dict.fromkeys(sub["period"]):
        c = []
        for t in ["own_weekly", "own_monthly", "other_major"]:
            r = sub[(sub["period"] == per) & (sub["term"] == t)]
            c.append("–" if r.empty else cell(r.iloc[0].coef, r.iloc[0].se, r.iloc[0].p))
        rows.append(f"| {per} | " + " | ".join(c) + " |")
    byi = pe[(pe["outcome"] == "lrv_last") & (pe["term"] == "own (any)")]
    rows2 = ["| Period | Nifty 50 | Bank Nifty | Sensex |", "|---|---:|---:|---:|"]
    for per in dict.fromkeys(byi["period"]):
        c = []
        for s in ["nifty50", "banknifty", "sensex"]:
            r = byi[(byi["period"] == per) & (byi["sample"] == s)]
            c.append("–" if r.empty else cell(r.iloc[0].coef, r.iloc[0].se, r.iloc[0].p) + f" [{int(r.iloc[0].n_treated)}]")
        rows2.append(f"| {per} | " + " | ".join(c) + " |")
    write("s5_periods", "\n".join(rows) + "\n\n" + "\n".join(rows2))

    fc = pd.read_csv(RES / "forecast.csv")
    rows = ["| Index | Forecast days | QLIKE, HAR | QLIKE, HAR + calendar | Change (%) | Diebold–Mariano *p* |", "|---|---:|---:|---:|---:|---:|"]
    for r in fc[fc["subset"] == "all days"].itertuples():
        rows.append(f"| {LABEL[r.index]} | {r.n:,} | {r.qlike_base:.4f} | {r.qlike_alt:.4f} | {r.qlike_change_pct:+.1f} | {r.dm_p:.3f} |")
    write("s6_forecast", "\n".join(rows))

    cas = pd.read_csv(RES / "closing_auction_hourly.csv")
    rows = ["| | Own expiry | Another large index expires | Own expiry × after 3 Aug 2026 | Expiry days after |", "|---|---:|---:|---:|---:|"]
    for s in ["pooled", "nifty50", "banknifty", "sensex"]:
        t = cas[cas["sample"] == s].set_index("term")
        rows.append(f"| {LABEL[s]} | {cell(t.loc['own','coef'], t.loc['own','se'], t.loc['own','p'], 2)} | "
                    f"{cell(t.loc['other_major','coef'], t.loc['other_major','se'], t.loc['other_major','p'], 2)} | "
                    f"{cell(t.loc['own_x_post','coef'], t.loc['own_x_post','se'], t.loc['own_x_post','p'], 2)} | {int(t['post_expiries'].iloc[0])} |")
    write("s7_cas", "\n".join(rows))

    w = pd.read_csv(RES / "weekly_totals.csv")
    rows = ["| Measure | Weekly-options regime | *p* | Index-weeks |", "|---|---:|---:|---:|"]
    for r in w.itertuples():
        rows.append(f"| {r.measure} | {num(r.coef)} ({r.se:.3f}) | {r.p:.3f} | {int(r.n):,} |")
    write("s8_weekly", "\n".join(rows))

    a = pd.read_csv(RES / "option_activity_by_year.csv")
    rows = ["| Year | Nifty 50 | Bank Nifty |", "|---|---:|---:|"]
    for y in sorted(a["year"].unique()):
        n = a[(a["year"] == y) & (a["index"] == "nifty50")]["share_0dte_of_year"]
        b = a[(a["year"] == y) & (a["index"] == "banknifty")]["share_0dte_of_year"]
        rows.append(f"| {y} | {100*n.iloc[0]:.1f} | {100*b.iloc[0]:.1f} |")
    write("s9_activity", "\n".join(rows))


def extra_table():
    x = pd.read_csv(RES / "extra_checks.csv")
    rows = ["| Check | Outcome | Coefficient | *p* | Observations |", "|---|---|---:|---:|---:|"]
    names = {"gain_post": "weekday gaining an expiry", "lose_post": "weekday losing an expiry",
             "own_weekly": "own weekly expiry", "own_monthly": "own monthly expiry", "other_major": "another large index expires",
             "own": "own expiry (at average volume)", "own_x_volume": "own expiry × expiring-series contracts (1 s.d.)"}
    outc = {"lrv_last": "15:00–15:30, 1-min RV", "lrv5": "whole session, 5-min RV", "lrv5_last": "15:00–15:30, 5-min RV"}
    for r in x.itertuples():
        if r.check.startswith("mean share"):
            continue
        rows.append(f"| {r.check} — {names.get(r.term, r.term)} | {outc.get(r.outcome, r.outcome)} | {cell(r.coef, r.se, r.p)} | {r.p:.3f} | {int(r.n):,} |")
    write("s10_extra", "\n".join(rows), [52, 22, 13, 8, 10])
    sh = x[x["check"].str.startswith("mean share")]
    rows = ["| Index | Own expiry days | Other days |", "|---|---:|---:|"]
    for idx in ["nifty50", "banknifty", "sensex"]:
        a = sh[(sh["outcome"] == idx) & (sh["term"] == "own expiry days")]["coef"].iloc[0]
        b = sh[(sh["outcome"] == idx) & (sh["term"] == "other days")]["coef"].iloc[0]
        rows.append(f"| {LABEL[idx]} | {100*a:.1f} | {100*b:.1f} |")
    write("s11_share", "\n".join(rows))


if __name__ == "__main__":
    extra_table()
    table_events_list()
    table_descriptives()
    table_main()
    table_events()
    table_robust()
    supp_tables()
    print("tables written to", OUT)
