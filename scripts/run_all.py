"""Reproduce every number, table and figure of the paper.

    python scripts/run_all.py            # full run (about 10 minutes; placebo tests are the slow part)
    python scripts/run_all.py --quick    # 50 placebo calendars instead of 1,000 (for a fast check)

Reads data from data/ (downloading anything missing on the first run) and writes:
    results/*.csv           every estimate, one file per analysis
    results/key_numbers.json   the numbers quoted in the paper and README
    figures/*.png|pdf       the figures
    paper/tables/*.tex      the LaTeX tables
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from expiryvol import data, estimate as es, expiries as ex, forecast as fc, mechanisms as me, plots  # noqa: E402
from expiryvol.features import build_panel  # noqa: E402

RES, FIG, TAB = ROOT / "results", ROOT / "figures", ROOT / "paper" / "tables"
DATA = ROOT / "data"
BIN_WEEKS = 8


def log(msg: str, t0=[time.time()]):  # noqa: B006
    print(f"[{time.time() - t0[0]:6.0f}s] {msg}", flush=True)


def stars(p: float) -> str:
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.10 else ""


def cell(coef: float, se: float, p: float) -> tuple[str, str]:
    return f"{coef:.3f}{stars(p)}", f"({se:.3f})"


# ------------------------------------------------------------------------ LaTeX helpers
def write_tex(name: str, body: str):
    (TAB / f"{name}.tex").write_text(body)


def coef_table(frames: dict, terms: dict, note_n: dict | None = None) -> str:
    """Columns = models (dict name -> FE table with index term), rows = terms."""
    cols = list(frames)
    lines = ["\\begin{tabular}{l" + "c" * len(cols) + "}", "\\toprule",
             " & " + " & ".join(cols) + " \\\\", "\\midrule"]
    for term, label in terms.items():
        top, bot = [label], [""]
        for c in cols:
            t = frames[c]
            if term in t.index:
                a, b = cell(t.loc[term, "coef"], t.loc[term, "se"], t.loc[term, "p"])
            else:
                a, b = "", ""
            top.append(a)
            bot.append(b)
        lines += [" & ".join(top) + " \\\\", " & ".join(bot) + " \\\\"]
    if note_n:
        lines += ["\\midrule", "Observations & " + " & ".join(f"{note_n[c]:,}" for c in cols) + " \\\\"]
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines)


TERMS = {"own_weekly": "Own weekly expiry", "own_monthly": "Own monthly expiry",
         "other_major": "Other large index expires", "other_minor": "Small index expires"}


def main(n_placebo: int):
    for d in (RES, FIG, TAB):
        d.mkdir(parents=True, exist_ok=True)
    K: dict = {}

    # ------------------------------------------------------------------ data
    log("loading data")
    prices, dropped = data.load_all_daily(DATA)
    dropped.to_csv(RES / "data_dropped_rows.csv", index=False)
    td = data.trading_days("2013-06-03", data.DATA_END)
    table = ex.expiry_table(td)
    panel = build_panel(prices, table, data.INDICES, data.STUDY_START, data.STUDY_END)
    panel.to_parquet(RES / "panel.parquet") if False else None  # (not saved: contains Yahoo prices)

    # calendar check against NSE contract files and the Sensex option files
    rows = []
    for sym in ["NIFTY", "BANKNIFTY"]:
        opt = data.load_options_eod(sym, range(2014, 2027), DATA, columns=("date", "expiry"))
        obs = data.observed_expiry_days(opt)
        fdays = pd.DatetimeIndex(sorted(opt["date"].unique()))
        c = ex.compare_with_actual(sym, obs, td, "2014-01-01", str(fdays.max().date()))
        missing = c[~c["date"].isin(fdays)]
        c = c[c["date"].isin(fdays)]
        rows.append({"product": sym, "source": "NSE bhavcopy", "from": "2014-01-01", "to": str(fdays.max().date()),
                     "expiry_days_rule": int(c["rule"].sum()), "expiry_days_files": int(c["actual"].sum()),
                     "mismatches": int((c["rule"] != c["actual"]).sum()),
                     "rule_days_not_in_files": ", ".join(str(d.date()) for d in missing["date"])})
        pd.Series(obs).to_csv(ROOT / "tests" / "data" / f"observed_expiries_{sym}.csv", index=False, header=["date"])
    sx = pd.to_datetime(pd.read_csv(ROOT / "tests" / "data" / "hf_option_files_SENSEX.csv")["expiry"])
    rule = set(ex.expiry_dates("SENSEX", td, str(sx.min().date()), str(sx.max().date()))["date"])
    rows.append({"product": "SENSEX", "source": "1-minute option files (expiry dates)", "from": str(sx.min().date()),
                 "to": str(sx.max().date()), "expiry_days_rule": len(rule), "expiry_days_files": len(set(sx)),
                 "mismatches": len(set(sx) - rule),
                 "rule_days_not_in_files": ", ".join(str(d.date()) for d in sorted(rule - set(sx)))})
    cal = pd.DataFrame(rows)
    cal.to_csv(RES / "calendar_check.csv", index=False)
    K["calendar"] = cal.to_dict("records")

    # rules table (Table 1)
    rt = ex.rules_table()
    rt.to_csv(RES / "expiry_rules.csv", index=False)
    lines = ["\\begin{tabular}{llllp{6.2cm}}", "\\toprule", "Product & From & Weekly & Monthly & Note \\\\", "\\midrule"]
    for _, r in rt.iterrows():
        if r["product"] in ("FINNIFTY", "MIDCPNIFTY", "BANKEX") and False:
            continue
        frm = r["from"] if r["from"] != "2000-01-01" else "before 2014"
        note = r["note"].replace("&", "\\&")
        lines.append(f"{r['product']} & {frm} & {r['weekly']} & {r['monthly']} & {note} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    write_tex("rules", "\n".join(lines))

    # sample summary
    summ = panel.groupby("index").agg(days=("date", "size"), first=("date", "min"), last=("date", "max"),
                                      weekly_expiries=("own_weekly", "sum"), monthly_expiries=("own_monthly", "sum"),
                                      other_major_days=("other_major", "sum"),
                                      ann_vol=("rv", lambda v: np.sqrt(252 * v.mean())))
    summ.to_csv(RES / "sample_summary.csv")
    K["sample"] = {"days": int(len(panel)), "per_index": summ["days"].to_dict(),
                   "own_expiry_days": int(panel["own"].sum())}
    lines = ["\\begin{tabular}{lrrrrr}", "\\toprule",
             "Index & Days & Weekly exp. & Monthly exp. & Other large exp. & Ann. vol. (\\%) \\\\", "\\midrule"]
    for idx in data.INDICES:
        r = summ.loc[idx]
        lines.append(f"{plots.LABEL[idx]} & {r['days']:,} & {r['weekly_expiries']} & {r['monthly_expiries']} & {r['other_major_days']:,} & {r['ann_vol']:.1f} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    write_tex("sample", "\n".join(lines))

    # ------------------------------------------------------------------ whole-session results
    log("main regressions")
    main_tab = es.main_regressions(panel, "lgk")
    main_tab.to_csv(RES / "main_lgk.csv", index=False)
    alt = []
    for y, lab in [("lgk", "Garman-Klass"), ("lpark", "Parkinson"), ("lrs", "Rogers-Satchell"),
                   ("loc", "open-to-close return"), ("lrv", "close-to-close (incl. overnight)"),
                   ("lon", "overnight gap")]:
        r = es.fe_ols(panel, y, es.TREAT, es.MAIN_FE)
        alt.append(r.table().assign(outcome=lab, n=r.nobs).rename_axis("term").reset_index())
    alt = pd.concat(alt)
    alt.to_csv(RES / "alt_outcomes.csv", index=False)
    rob = es.robustness(panel, "lgk")
    rob.to_csv(RES / "robustness_lgk.csv", index=False)

    frames, ns = {}, {}
    for s in ["pooled", "nifty50", "banknifty", "sensex", "midcap50"]:
        t = main_tab[main_tab["sample"] == s].set_index("term")
        frames[plots.LABEL[s]] = t
        ns[plots.LABEL[s]] = int(t["n"].iloc[0])
    write_tex("main_lgk", coef_table(frames, TERMS, ns))
    pooled = main_tab[main_tab["sample"] == "pooled"].set_index("term")
    K["daily"] = {t: {k: float(pooled.loc[t, k]) for k in ["coef", "se", "p", "lo", "hi"]} for t in es.TREAT}
    K["daily_per_index"] = {s: {t: {k: float(v) for k, v in main_tab[(main_tab["sample"] == s) & (main_tab["term"] == t)]
                                    [["coef", "se", "p", "p_holm"]].iloc[0].items()} for t in ["own_weekly", "own_monthly"]}
                            for s in data.INDICES}

    # ------------------------------------------------------------------ minute data
    log("minute data")
    mdays, slots = me.minute_panels(table, DATA, end=data.STUDY_END)
    hol = panel[["date", "index", "pre_holiday", "post_holiday", "shifted"]]
    mdays = mdays.drop(columns=["shifted"]).merge(hol, on=["date", "index"], how="left")
    mdays["own_before"] = 0
    mdays["own_after"] = 0
    for idx in me.MINUTE_INDICES:
        f = ex.expiry_flags(table, idx)
        b, a = f["own"].shift(-1).fillna(0), f["own"].shift(1).fillna(0)
        m = mdays["index"] == idx
        mdays.loc[m, "own_before"] = b.reindex(mdays.loc[m, "date"]).to_numpy()
        mdays.loc[m, "own_after"] = a.reindex(mdays.loc[m, "date"]).to_numpy()
    K["minute_sample"] = {"days": int(len(mdays)), "per_index": mdays.groupby("index").size().to_dict(),
                          "first": {i: str(g["date"].min().date()) for i, g in mdays.groupby("index")},
                          "last": str(mdays["date"].max().date())}
    # agreement of minute data with Yahoo daily bars
    agree = []
    for idx in me.MINUTE_INDICES:
        m = data.load_minute(idx, DATA)
        g = m.groupby("day")
        d = pd.DataFrame({"high": g["High"].max(), "low": g["Low"].min()})
        y = prices[idx][["High", "Low"]]
        j = d.join(y, how="inner")
        agree.append({"index": idx, "days": len(j),
                      "corr_log_range": float(np.corrcoef(np.log(np.log(j.high / j.low)), np.log(np.log(j.High / j.Low)))[0, 1])})
    pd.DataFrame(agree).to_csv(RES / "minute_vs_daily.csv", index=False)
    K["minute_agreement"] = agree

    mday = me.day_effects(mdays, ("lrv5", "lrv_last"))
    mday.to_csv(RES / "minute_day_effects.csv", index=False)
    slot_tab = me.slot_effects(slots)
    slot_tab.to_csv(RES / "slot_effects.csv", index=False)

    frames, ns = {}, {}
    for y, ylab in [("lrv5", "Whole session"), ("lrv_last", "Last 30 min")]:
        for s in ["pooled", "nifty50", "banknifty", "sensex"]:
            t = mday[(mday["outcome"] == y) & (mday["sample"] == s)].set_index("term")
            key = f"{ylab}: {plots.LABEL[s]}"
            frames[key], ns[key] = t, int(t["n"].iloc[0])
    lab_short = {k: k.split(": ")[1] for k in frames}
    tex = coef_table(frames, {k: v for k, v in TERMS.items() if k != "other_minor"}, ns)
    tex = tex.replace(" & " + " & ".join(frames) + " \\\\",
                      " & \\multicolumn{4}{c}{Whole session (5-min realized variance)} & \\multicolumn{4}{c}{Last 30 minutes (15:00--15:30)} \\\\\n"
                      "\\cmidrule(lr){2-5}\\cmidrule(lr){6-9}\n & " + " & ".join(lab_short.values()) + " \\\\")
    write_tex("minute_main", tex)
    pl = mday[mday["sample"] == "pooled"].set_index(["outcome", "term"])
    K["minute"] = {f"{o}:{t}": {k: float(pl.loc[(o, t), k]) for k in ["coef", "se", "p", "lo", "hi"]}
                   for o in ["lrv5", "lrv_last"] for t in ["own_weekly", "own_monthly", "other_major"]}
    K["minute_per_index"] = {f"{s}:{o}:{t}": {k: float(v) for k, v in mday[(mday["sample"] == s) & (mday["outcome"] == o) & (mday["term"] == t)][["coef", "se", "p"]].iloc[0].items()}
                             for s in me.MINUTE_INDICES for o in ["lrv5", "lrv_last"] for t in ["own_weekly", "own_monthly", "other_major"]}

    # robustness of the settlement-window result
    log("robustness of last-30-minute effect")
    rows = []
    md = es.add_fe_columns(mdays)
    specs = [("Baseline", md, es.TREAT, es.MAIN_FE, "cluster"),
             ("+ weekday x year effects", md, es.TREAT, es.MAIN_FE + (("wd", "year"),), "cluster"),
             ("+ date effects (cross-index)", md, es.TREAT, es.MAIN_FE + (("date_fe",),), "cluster"),
             ("Driscoll-Kraay errors", md, es.TREAT, es.MAIN_FE, "dk"),
             ("+ holiday controls", md, es.TREAT + ["pre_holiday", "post_holiday"], es.MAIN_FE, "cluster"),
             ("+ day before / after own expiry", md, es.TREAT + ["own_before", "own_after"], es.MAIN_FE, "cluster")]
    for name, d, x, fe, cov in specs:
        r = es.fe_ols(d, "lrv_last", x, fe, cov=cov, drop_absorbed=True)
        for term, row in r.table().loc[["own_weekly", "own_monthly"]].iterrows():
            rows.append({"spec": name, "term": term, **row.to_dict(), "n": r.nobs})
    # the last 15 minutes and the 30 minutes before the window, from the slot data
    for start, lab in [("15:15", "Last 15 minutes only (15:15-15:30)"), ("15:00", "15:00-15:15 only"),
                       ("14:45", "Just before the window (14:45-15:00)")]:
        t = slot_tab[(slot_tab["start"] == start)].set_index("term")
        for term in ["own_weekly", "own_monthly"]:
            rows.append({"spec": lab, "term": term, **t.loc[term, ["coef", "se", "t", "p", "lo", "hi", "n"]].to_dict()})
    rob_last = pd.DataFrame(rows)
    rob_last.to_csv(RES / "robustness_last30.csv", index=False)

    # ------------------------------------------------------------------ natural experiments
    log("event studies")
    major = [e for e in ex.EVENTS if e.major]
    minute_events = [e for e in major if e.index in me.MINUTE_INDICES and pd.Timestamp(e.date) >= pd.Timestamp("2021-12-01")]
    ev_rows = []
    for e in ex.EVENTS:
        t = es.event_did(panel, e, "lgk").assign(outcome="lgk")
        ev_rows.append(t)
        if e in minute_events:
            ev_rows.append(es.event_did(mdays, e, "lrv_last").assign(outcome="lrv_last"))
            ev_rows.append(es.event_did(mdays, e, "lrv5").assign(outcome="lrv5"))
    ev = pd.concat(ev_rows, ignore_index=True)
    ev.to_csv(RES / "event_did.csv", index=False)
    st = pd.concat([es.stacked_events(panel, major, "lgk").assign(outcome="lgk", design="8 major events, daily range"),
                    es.stacked_events(panel, minute_events, "lgk").assign(outcome="lgk", design="6 events with minute data, daily range"),
                    es.stacked_events(mdays, minute_events, "lrv5").assign(outcome="lrv5", design="6 events, whole session (5-min RV)"),
                    es.stacked_events(mdays, minute_events, "lrv_last").assign(outcome="lrv_last", design="6 events, last 30 minutes")])
    st.to_csv(RES / "event_stacked.csv", index=False)
    K["stacked"] = {f"{r.design}:{r.term}": {"coef": r.coef, "se": r.se, "p": r.p} for r in st.itertuples()}
    et_last = es.event_time(mdays, minute_events, "lrv_last", bin_weeks=BIN_WEEKS)
    et_day = es.event_time(mdays, minute_events, "lrv5", bin_weeks=BIN_WEEKS)
    et_last.assign(outcome="lrv_last").pipe(lambda a: pd.concat([a, et_day.assign(outcome="lrv5")])).to_csv(RES / "event_time.csv", index=False)
    plots.fig_event_time(et_last, et_day, BIN_WEEKS, str(FIG / "fig5_event_time"))

    # event table (Table 5)
    lines = ["\\begin{tabular}{llcccc}", "\\toprule",
             " & & \\multicolumn{2}{c}{Whole session} & \\multicolumn{2}{c}{Last 30 minutes} \\\\",
             "\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}",
             "Change & Date & New weekday & Old weekday & New weekday & Old weekday \\\\", "\\midrule"]
    for e in ex.EVENTS:
        def get(outcome, term):
            r = ev[(ev["event"] == e.name) & (ev["outcome"] == outcome) & (ev["term"] == term)]
            if r.empty:
                return ""
            r = r.iloc[0]
            return f"{r.coef:.2f}{stars(r.p)} ({r.se:.2f})"
        name = e.name + ("$^\\dagger$" if not e.major else "")
        lines.append(f"{name} & {e.date} & {get('lgk', 'gain_post')} & {get('lgk', 'lose_post')} & "
                     f"{get('lrv_last', 'gain_post')} & {get('lrv_last', 'lose_post')} \\\\")
    lines.append("\\midrule")
    for design, outcome, label in [("8 major events, daily range", "lgk", "Stacked, 8 major changes"),
                                   ("6 events, last 30 minutes", "lrv_last", "Stacked, 6 changes with minute data")]:
        r = st[st["design"] == design].set_index("term")
        g = f"{r.loc['gain_post', 'coef']:.2f}{stars(r.loc['gain_post', 'p'])} ({r.loc['gain_post', 'se']:.2f})"
        lo = f"{r.loc['lose_post', 'coef']:.2f}{stars(r.loc['lose_post', 'p'])} ({r.loc['lose_post', 'se']:.2f})"
        if outcome == "lgk":
            lines.append(f"{label} & & {g} & {lo} & & \\\\")
        else:
            lines.append(f"{label} & & & & {g} & {lo} \\\\")
    r = st[st["design"] == "6 events, whole session (5-min RV)"].set_index("term")
    lines.append(f"Stacked, same 6 changes, 5-min RV & & {r.loc['gain_post', 'coef']:.2f}{stars(r.loc['gain_post', 'p'])} ({r.loc['gain_post', 'se']:.2f}) & "
                 f"{r.loc['lose_post', 'coef']:.2f}{stars(r.loc['lose_post', 'p'])} ({r.loc['lose_post', 'se']:.2f}) & & \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    write_tex("events", "\n".join(lines))

    # weekday profiles (Figure 2 and appendix figure)
    prof_day, prof_last = {}, {}
    for e in major:
        lo, hi = es.event_window(e)
        before = (lo, pd.Timestamp(e.date) - pd.Timedelta(days=1))
        after = (pd.Timestamp(e.date), hi)
        prof_day[e.name] = {"event": e, "before": es.weekday_profile(panel, e.index, *before, "lgk"),
                            "after": es.weekday_profile(panel, e.index, *after, "lgk")}
        if e in minute_events:
            prof_last[e.name] = {"event": e, "before": es.weekday_profile(mdays, e.index, *before, "lrv_last"),
                                 "after": es.weekday_profile(mdays, e.index, *after, "lrv_last")}
    plots.fig_moving(prof_last, str(FIG / "fig2_moving_close"), "Settlement-window variance\nvs rest of week (%)")
    plots.fig_moving(prof_day, str(FIG / "figA1_moving_day"), "Daily-range variance vs\nrest of week (%)")
    pr = []
    for name, p in {**{("day", k): v for k, v in prof_day.items()}, **{("last30", k): v for k, v in prof_last.items()}}.items():
        for when in ["before", "after"]:
            pr.append(p[when].assign(measure=name[0], event=name[1], when=when).rename_axis("weekday").reset_index())
    pd.concat(pr).to_csv(RES / "weekday_profiles.csv", index=False)

    # ------------------------------------------------------------------ main figure, intraday
    plots.fig_main(main_tab, mday[mday["outcome"] == "lrv_last"], str(FIG / "fig3_main"))
    plots.fig_intraday(slot_tab, str(FIG / "fig4_intraday"))

    # ------------------------------------------------------------------ periods / regulation
    log("periods")
    per_day = es.period_effects(panel, "lgk")
    per_last = es.period_effects(mdays, "lrv_last", periods=es.PERIODS[1:])
    per_last_idx = es.period_effects_by_index(mdays, "lrv_last", periods=es.PERIODS[1:])
    pd.concat([per_day.assign(outcome="lgk"), per_last.assign(outcome="lrv_last"),
               per_last_idx.assign(outcome="lrv_last")]).to_csv(RES / "period_effects.csv", index=False)
    plots.fig_periods(per_last_idx, str(FIG / "fig6_periods"))
    K["periods_last30"] = {f"{r.period}:{r.term}": {"coef": r.coef, "se": r.se, "p": r.p} for r in per_last.itertuples()}
    K["periods_last30_by_index"] = {f"{r.sample}:{r.period}": {"coef": r.coef, "se": r.se, "p": r.p, "n_expiry": r.n_treated}
                                    for r in per_last_idx.itertuples()}
    lines = ["\\begin{tabular}{lcccccc}", "\\toprule",
             " & \\multicolumn{3}{c}{Whole session (daily range)} & \\multicolumn{3}{c}{Last 30 minutes} \\\\",
             "\\cmidrule(lr){2-4}\\cmidrule(lr){5-7}",
             "Period & Own weekly & Own monthly & Other large & Own weekly & Own monthly & Other large \\\\", "\\midrule"]
    for lo_, hi_, label in es.PERIODS:
        parts = [f"{label} ({lo_[:7]} to {hi_[:7]})"]
        for tab in (per_day, per_last):
            for term in ["own_weekly", "own_monthly", "other_major"]:
                r = tab[(tab["period"] == label) & (tab["term"] == term)]
                parts.append("--" if r.empty else f"{r.iloc[0].coef:.2f}{stars(r.iloc[0].p)} ({r.iloc[0].se:.2f})")
        lines.append(" & ".join(parts) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    write_tex("periods", "\n".join(lines))

    # ------------------------------------------------------------------ randomization inference
    log(f"placebo calendars ({n_placebo})")
    pl_day = es.placebo_distribution(panel, td, n_draws=n_placebo, seed=7, y="lgk")
    pl_last = es.placebo_distribution(mdays, td, n_draws=n_placebo, seed=11, y="lrv_last")
    pl_day.assign(outcome="lgk").pipe(lambda a: pd.concat([a, pl_last.assign(outcome="lrv_last")])).to_csv(RES / "placebo_draws.csv", index=False)
    ri = []
    for outcome, pl, actual in [("lgk", pl_day, pooled), ("lrv_last", pl_last, mday[(mday["outcome"] == "lrv_last") & (mday["sample"] == "pooled")].set_index("term"))]:
        for term in ["own_weekly", "own_monthly"]:
            ri.append({"outcome": outcome, "term": term, "actual": float(actual.loc[term, "coef"]),
                       "placebo_mean": float(pl[f"b_{term}"].mean()), "placebo_sd": float(pl[f"b_{term}"].std()),
                       "ri_p": es.ri_pvalue(actual.loc[term, "coef"], pl[f"b_{term}"]), "draws": int(len(pl))})
    ri = pd.DataFrame(ri)
    ri.to_csv(RES / "randomization_inference.csv", index=False)
    K["ri"] = ri.to_dict("records")
    plots.fig_placebo(pl_last["b_own_weekly"], float(ri.iloc[2]["actual"]), str(FIG / "figA2_placebo_last30"),
                      "Weekly-expiry effect on settlement-window variance")

    # robustness table (Table 6): whole session and last 30 min
    def rob_cells(df, spec, term):
        r = df[(df["spec"] == spec) & (df["term"] == term)]
        return "" if r.empty else f"{r.iloc[0].coef:.3f}{stars(r.iloc[0].p)} ({r.iloc[0].se:.3f})"
    lines = ["\\begin{tabular}{lcccc}", "\\toprule",
             " & \\multicolumn{2}{c}{Whole session (daily range)} & \\multicolumn{2}{c}{Last 30 minutes} \\\\",
             "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}", "Specification & Weekly & Monthly & Weekly & Monthly \\\\", "\\midrule"]
    specs_all = list(dict.fromkeys(list(rob["spec"]) + list(rob_last["spec"])))
    for spec in specs_all:
        if spec.startswith("Holiday-shifted"):
            continue
        spec_tex = spec.replace(" x ", " $\\times$ ")
        lines.append(f"{spec_tex} & {rob_cells(rob, spec, 'own_weekly')} & {rob_cells(rob, spec, 'own_monthly')} & "
                     f"{rob_cells(rob_last, spec, 'own_weekly')} & {rob_cells(rob_last, spec, 'own_monthly')} \\\\")
    hs = rob[rob["spec"].str.startswith("Holiday-shifted")].iloc[0]
    lines.append(f"Holiday-shifted expiries only (any own expiry) & \\multicolumn{{2}}{{c}}{{{hs.coef:.3f}{stars(hs.p)} ({hs.se:.3f})}} & & \\\\")
    lines.append("\\midrule")
    lines.append("Placebo-calendar $p$-value (" + f"{int(ri.iloc[0].draws):,}" + " draws) & " +
                 " & ".join(f"{r.ri_p:.3f}" for r in ri.itertuples()) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    write_tex("robustness", "\n".join(lines))

    # ------------------------------------------------------------------ pinning, reversal, activity
    log("pinning, reversals, option activity")
    grid = me.grid_pinning(panel)
    grid.to_csv(RES / "pinning_grid.csv", index=False)
    moves = []
    for idx in ["nifty50", "banknifty"]:
        k = me.max_oi_strikes(idx, table, td, DATA)
        moves.append(me.pin_moves(prices[idx].loc[data.STUDY_START:data.STUDY_END], k).assign(index=idx))
    moves = pd.concat(moves)
    pin = me.pin_tests(moves)
    pin.to_csv(RES / "pinning_maxoi.csv", index=False)
    rev = me.reversal_tests(mdays)
    rev.to_csv(RES / "reversal.csv", index=False)
    K["reversal_bn_alleged"] = rev[(rev["sample"] == "banknifty 2023-01..2025-03") & (rev["term"].isin(["rest_x_own", "am_x_own"]))][["term", "coef", "se", "p"]].to_dict("records")
    acts = []
    for idx in ["nifty50", "banknifty"]:
        a = me.option_activity(idx, table, td, DATA)
        a["expiry_day"] = a["date"].isin(ex.expiry_dates(me.OPTION_SYMBOL[idx], td)["date"])
        acts.append(a)
    acts = pd.concat(acts)
    acts["year"] = acts["date"].dt.year
    acts = acts[acts["year"] <= 2025]           # 2026 is a part year
    g = acts.groupby(["index", "year"])
    act_y = pd.DataFrame({
        # share of the whole year's option contracts that were traded on an expiry day in the
        # series expiring that day ("zero days to expiry")
        "share_0dte_of_year": g.apply(lambda x: x.loc[x["expiry_day"], "expiring"].sum() / x["total"].sum()),
        # on expiry days, share of that day's contracts in the expiring series
        "share_expiring_on_expiry_days": g.apply(lambda x: x.loc[x["expiry_day"], "expiring"].sum() / x.loc[x["expiry_day"], "total"].sum()),
        "expiry_days": g["expiry_day"].sum()}).reset_index()
    act_y.to_csv(RES / "option_activity_by_year.csv", index=False)
    plots.fig_activity(act_y, str(FIG / "fig1_activity"))
    K["activity"] = {f"{r.index}:{r.year}": r.share_0dte_of_year for r in act_y.itertuples()}

    lines = ["\\begin{tabular}{llcccc}", "\\toprule",
             "Index & Strike step & Share near a strike: expiry & other days & Weekly coef. & Monthly coef. \\\\", "\\midrule"]
    for r in grid.itertuples():
        lines.append(f"{plots.LABEL[r.index]} & {r.step} & {r.share_expiry:.3f} & {r.share_other:.3f} & "
                     f"{r.coef_weekly:.3f} ({r.se_weekly:.3f}) & {r.coef_monthly:.3f} ({r.se_monthly:.3f}) \\\\")
    lines.append("\\midrule")
    lines.append("\\multicolumn{6}{l}{\\emph{Move toward the strike with the most open interest (previous close), \\% of index level}} \\\\")
    lines.append("Index & & Expiry days & Other days & \\multicolumn{2}{c}{Difference, controlling for distance at open} \\\\")
    for r in pin.itertuples():
        lines.append(f"{plots.LABEL[r.index]} & & {r.mean_move_expiry:.3f} & {r.mean_move_other:.3f} & \\multicolumn{{2}}{{c}}{{{r.coef:.3f} ({r.se:.3f})}} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    write_tex("pinning", "\n".join(lines))

    # ------------------------------------------------------------------ weekly totals (H6)
    log("weekly totals")
    wt = es.weekly_total_test(panel)
    w = es.weekly_totals(panel, "rv")
    w["t"] = (w["date"] - pd.Timestamp("2020-01-01")).dt.days / 365.25
    trend_cols = []
    for idx in sorted(w["index"].unique())[1:]:
        w[f"tr_{idx}"] = (w["index"] == idx) * w["t"]
        trend_cols.append(f"tr_{idx}")
    r = es.fe_ols(w, "lv", ["weekly_regime"] + trend_cols, (("index",), ("week",)), time_col="week")
    wt = pd.concat([wt, pd.DataFrame([{"measure": "close-to-close, + index-specific trends",
                                       **r.table().loc["weekly_regime"].to_dict(), "n": r.nobs}])])
    wt.to_csv(RES / "weekly_totals.csv", index=False)
    K["weekly_totals"] = wt.to_dict("records")

    # ------------------------------------------------------------------ forecasting (H8)
    log("forecasting")
    fres = []
    for idx in data.INDICES:
        F = fc.forecast_frame(panel, idx)
        preds = fc.walk_forward(F, {"HAR": fc.HAR_COLS, "HAR + expiry calendar": fc.HAR_COLS + fc.EXPIRY_COLS}, "2018-01-01")
        preds["own_next"] = (F.loc[preds.index, "own_weekly_next"] + F.loc[preds.index, "own_monthly_next"]).to_numpy()
        for subset, v in fc.evaluate(preds, "HAR", "HAR + expiry calendar").items():
            fres.append({"index": idx, "subset": subset, **v})
    fres = pd.DataFrame(fres)
    fres.to_csv(RES / "forecast.csv", index=False)
    K["forecast"] = fres.to_dict("records")
    lines = ["\\begin{tabular}{lrrrrr}", "\\toprule",
             "Index & Days & QLIKE, HAR & QLIKE, + calendar & Change (\\%) & DM $p$ \\\\", "\\midrule"]
    for r in fres[fres["subset"] == "all days"].itertuples():
        lines.append(f"{plots.LABEL[r.index]} & {r.n:,} & {r.qlike_base:.4f} & {r.qlike_alt:.4f} & {r.qlike_change_pct:+.1f} & {r.dm_p:.3f} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    write_tex("forecast", "\n".join(lines))

    # ------------------------------------------------------------------ closing auction, early look
    log("closing auction (hourly bars)")
    try:
        cas = me.closing_auction_look(table, DATA)
        cas.to_csv(RES / "closing_auction_hourly.csv", index=False)
        K["closing_auction"] = cas.to_dict("records")
    except Exception as exc:  # hourly history on Yahoo only reaches back 730 days
        log(f"closing auction look skipped: {exc}")

    (RES / "key_numbers.json").write_text(json.dumps(K, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    log("done")


def extra_tables():
    """Appendix tables built from the saved result files (alternative outcomes, closing auction)."""
    alt = pd.read_csv(RES / "alt_outcomes.csv")
    outs = list(dict.fromkeys(alt["outcome"]))
    lines = ["\\begin{tabular}{l" + "c" * len(outs) + "}", "\\toprule",
             " & " + " & ".join(o.replace("close-to-close (incl. overnight)", "close-to-close").replace("open-to-close return", "open-to-close") for o in outs) + " \\\\", "\\midrule"]
    for term, label in TERMS.items():
        top, bot = [label], [""]
        for o in outs:
            r = alt[(alt["outcome"] == o) & (alt["term"] == term)].iloc[0]
            a, b = cell(r.coef, r.se, r.p)
            top.append(a)
            bot.append(b)
        lines += [" & ".join(top) + " \\\\", " & ".join(bot) + " \\\\"]
    lines += ["\\bottomrule", "\\end{tabular}"]
    write_tex("alt_outcomes", "\n".join(lines))
    cas_path = RES / "closing_auction_hourly.csv"
    if cas_path.exists():
        cas = pd.read_csv(cas_path)
        lines = ["\\begin{tabular}{lcccc}", "\\toprule",
                 " & Own expiry & Other large expires & Own expiry $\\times$ after 3 Aug 2026 & Expiry days after \\\\", "\\midrule"]
        for samp in ["pooled", "nifty50", "banknifty", "sensex"]:
            t = cas[cas["sample"] == samp].set_index("term")
            row = [plots.LABEL[samp]]
            for term in ["own", "other_major", "own_x_post"]:
                row.append(f"{t.loc[term, 'coef']:.2f}{stars(t.loc[term, 'p'])} ({t.loc[term, 'se']:.2f})")
            row.append(str(int(t["post_expiries"].iloc[0])))
            lines.append(" & ".join(row) + " \\\\")
        lines += ["\\bottomrule", "\\end{tabular}"]
        write_tex("closing_auction", "\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="50 placebo calendars instead of 1,000")
    ap.add_argument("--tables-only", action="store_true", help="only rebuild the appendix tables from results/")
    args = ap.parse_args()
    if not args.tables_only:
        main(50 if args.quick else 1000)
    extra_tables()
