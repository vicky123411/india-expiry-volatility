"""Estimation: fixed-effects regressions, event studies and placebo (randomization) tests.

Fixed effects are removed by alternating projections: the data are demeaned by each group
in turn until nothing changes. This is the method behind Stata's `reghdfe` and R's `fixest`,
written out here in a few lines so every step can be checked (tests/test_estimate.py).

Standard errors
* "cluster" (default): clustered by calendar week. Allows any correlation between the
  days and indices of the same week.
* "dk": Driscoll-Kraay. Allows correlation across indices on the same day and over the
  following `dk_lags` trading days.
* "robust": heteroskedasticity-robust (HC1), for reference only.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from . import expiries as ex

TREAT = ["own_weekly", "own_monthly", "other_major", "other_minor"]
MAIN_FE = (("index", "wd"), ("index", "week"))


# ------------------------------------------------------------------------ building blocks
def group_codes(df: pd.DataFrame, cols) -> np.ndarray:
    """Integer code (0, 1, 2, ...) for every combination of the values in `cols`."""
    cols = [cols] if isinstance(cols, str) else list(cols)
    codes = df.groupby(cols, sort=False, observed=True).ngroup().to_numpy()
    if (codes < 0).any():
        raise ValueError(f"missing values in fixed-effect columns {cols}")
    return codes


def demean(M, groups, tol: float = 1e-10, max_iter: int = 5000) -> np.ndarray:
    """Remove the fixed effects given by `groups` (list of integer code arrays) from every
    column of M by alternating projections."""
    M = np.array(M, dtype=float, copy=True)
    if M.ndim == 1:
        M = M[:, None]
    if not groups:
        return M
    counts = [np.bincount(g).astype(float) for g in groups]
    for _ in range(max_iter):
        biggest = 0.0
        for g, c in zip(groups, counts):
            for j in range(M.shape[1]):
                means = np.bincount(g, weights=M[:, j], minlength=len(c)) / c
                M[:, j] -= means[g]
                biggest = max(biggest, float(np.abs(means).max()))
        if biggest < tol or len(groups) == 1:
            break
    return M


def _nested(inner: np.ndarray, outer: np.ndarray) -> bool:
    """True if every level of `inner` lies within a single level of `outer`."""
    s = pd.DataFrame({"i": inner, "o": outer}).groupby("i")["o"].nunique()
    return bool((s <= 1).all())


@dataclass
class FEResult:
    params: pd.Series
    se: pd.Series
    df_t: float               # degrees of freedom for t-tests (np.inf = normal)
    nobs: int
    n_clusters: int | None
    cov: str
    r2_within: float
    resid: np.ndarray | None = None

    @property
    def tstat(self) -> pd.Series:
        return self.params / self.se

    @property
    def pvalue(self) -> pd.Series:
        t = self.tstat.abs()
        p = 2 * (stats.t.sf(t, self.df_t) if np.isfinite(self.df_t) else stats.norm.sf(t))
        return pd.Series(p, index=self.params.index)

    def ci(self, level: float = 0.95) -> pd.DataFrame:
        q = stats.t.ppf(0.5 + level / 2, self.df_t) if np.isfinite(self.df_t) else stats.norm.ppf(0.5 + level / 2)
        return pd.DataFrame({"lo": self.params - q * self.se, "hi": self.params + q * self.se})

    def table(self) -> pd.DataFrame:
        ci = self.ci()
        return pd.DataFrame({"coef": self.params, "se": self.se, "t": self.tstat, "p": self.pvalue,
                             "lo": ci["lo"], "hi": ci["hi"]})


def fe_ols(data: pd.DataFrame, y: str, x, fe=MAIN_FE, cov: str = "cluster", cluster="week",
           time_col: str = "date", dk_lags: int = 5, keep_resid: bool = False,
           drop_absorbed: bool = False) -> FEResult:
    """OLS of `y` on `x` with any number of fixed effects (each a column or tuple of columns).

    A regressor that the fixed effects explain completely raises an error, or is dropped
    when `drop_absorbed=True` (e.g. "small index expires" once date effects are included)."""
    x = [x] if isinstance(x, str) else list(x)
    fe = [f if isinstance(f, (tuple, list)) else (f,) for f in fe]
    cols = [y] + x + sorted({c for f in fe for c in f} | ({cluster} if isinstance(cluster, str) else set(cluster)) | {time_col})
    d = data[[c for c in dict.fromkeys(cols) if c in data.columns]].dropna().reset_index(drop=True)
    groups = [group_codes(d, f) for f in fe]
    Y = demean(d[y].to_numpy(dtype=float), groups)[:, 0]
    X = demean(d[x].to_numpy(dtype=float), groups)
    usable = np.abs(X).max(axis=0) > 1e-9           # regressors fully explained by the fixed effects
    if not usable.all():
        dropped = [c for c, u in zip(x, usable) if not u]
        if not drop_absorbed:
            raise ValueError(f"regressors absorbed by the fixed effects: {dropped}")
        x = [c for c, u in zip(x, usable) if u]
        X = X[:, usable]
    n, k = X.shape
    XtX_inv = np.linalg.inv(X.T @ X)
    b = XtX_inv @ (X.T @ Y)
    e = Y - X @ b
    scores = X * e[:, None]
    r2w = 1 - float(e @ e) / float(Y @ Y) if float(Y @ Y) > 0 else np.nan

    if cov == "cluster":
        cl = group_codes(d, cluster)
        G = int(cl.max()) + 1
        Sg = np.column_stack([np.bincount(cl, weights=scores[:, j], minlength=G) for j in range(k)])
        meat = Sg.T @ Sg
        # absorbed parameters count unless their groups sit inside a single cluster (as reghdfe)
        k_fe = sum(int(g.max()) + 1 for g in groups if not _nested(g, cl))
        k_fe = max(k_fe - (1 if k_fe else 0), 0)
        c = G / (G - 1) * (n - 1) / max(n - k - k_fe, 1)
        V = c * XtX_inv @ meat @ XtX_inv
        df_t, n_cl = G - 1, G
    elif cov == "dk":
        t_codes, t_levels = pd.factorize(d[time_col], sort=True)
        T = len(t_levels)
        h = np.column_stack([np.bincount(t_codes, weights=scores[:, j], minlength=T) for j in range(k)])
        S = h.T @ h
        for lag in range(1, dk_lags + 1):
            w = 1 - lag / (dk_lags + 1)
            G_l = h[lag:].T @ h[:-lag]
            S += w * (G_l + G_l.T)
        V = XtX_inv @ S @ XtX_inv * T / (T - 1)
        df_t, n_cl = np.inf, None
    elif cov == "robust":
        V = XtX_inv @ (scores.T @ scores) @ XtX_inv * n / (n - k)
        df_t, n_cl = np.inf, None
    else:
        raise ValueError(cov)
    se = np.sqrt(np.diag(V))
    return FEResult(pd.Series(b, index=x), pd.Series(se, index=x), df_t, n, n_cl, cov, r2w,
                    e if keep_resid else None)


def holm(pvalues: pd.Series) -> pd.Series:
    """Holm (1979) step-down adjustment of a set of p-values."""
    p = pvalues.sort_values()
    m = len(p)
    adj = np.maximum.accumulate([(m - i) * v for i, v in enumerate(p.to_numpy())])
    return pd.Series(np.minimum(adj, 1.0), index=p.index).reindex(pvalues.index)


def add_fe_columns(panel: pd.DataFrame) -> pd.DataFrame:
    """Extra columns used as fixed effects or clusters."""
    p = panel.copy()
    p["date_fe"] = pd.DatetimeIndex(p["date"]).strftime("%Y-%m-%d")
    p["post2017"] = (p["year"] >= 2017).astype(int)
    return p


# ------------------------------------------------------------------------ main table
def main_regressions(panel: pd.DataFrame, y: str = "lgk", cov: str = "cluster") -> pd.DataFrame:
    """Pooled and per-index estimates of the main specification (Section 5 of the plan)."""
    rows = []
    res = fe_ols(panel, y, TREAT, MAIN_FE, cov=cov)
    rows.append(res.table().assign(sample="pooled", n=res.nobs))
    for idx, sub in panel.groupby("index"):
        r = fe_ols(sub, y, TREAT, (("wd",), ("week",)), cov=cov)
        rows.append(r.table().assign(sample=idx, n=r.nobs))
    out = pd.concat(rows).rename_axis("term").reset_index()
    # Holm adjustment across the four indices, separately for each term
    per = out["sample"] != "pooled"
    out["p_holm"] = np.nan
    for term in TREAT:
        m = per & (out["term"] == term)
        out.loc[m, "p_holm"] = holm(out.loc[m, "p"]).to_numpy()
    return out


def robustness(panel: pd.DataFrame, y: str = "lgk") -> pd.DataFrame:
    """The pre-specified robustness checks of the pooled estimate (Section 6 of the plan)."""
    p = add_fe_columns(panel)
    specs = []
    specs.append(("Baseline", p, TREAT, MAIN_FE, "cluster"))
    specs.append(("+ weekday x year effects", p, TREAT, MAIN_FE + (("wd", "year"),), "cluster"))
    specs.append(("+ date effects (cross-index)", p, TREAT, MAIN_FE + (("date_fe",),), "cluster"))
    specs.append(("Driscoll-Kraay errors", p, TREAT, MAIN_FE, "dk"))
    specs.append(("Without 2020", p[p["year"] != 2020], TREAT, MAIN_FE, "cluster"))
    specs.append(("From 2017", p[p["year"] >= 2017], TREAT, MAIN_FE, "cluster"))
    lead = TREAT + ["own_before", "own_after"]
    specs.append(("+ day before / after own expiry", p, lead, MAIN_FE, "cluster"))
    rows = []
    for name, d, x, fe, cov in specs:
        r = fe_ols(d, y, x, fe, cov=cov)
        t = r.table().loc[["own_weekly", "own_monthly"]]
        for term, row in t.iterrows():
            rows.append({"spec": name, "term": term, **row.to_dict(), "n": r.nobs})
    # outcome relative to Midcap 50 (the index least exposed to large-cap options)
    rel = relative_to(panel, "midcap50", y)
    r = fe_ols(rel, y, TREAT, MAIN_FE)
    for term, row in r.table().loc[["own_weekly", "own_monthly"]].iterrows():
        rows.append({"spec": "Minus Midcap 50 on the same day", "term": term, **row.to_dict(), "n": r.nobs})
    hol = TREAT + ["pre_holiday", "post_holiday"]
    r = fe_ols(p, y, hol, MAIN_FE)
    for term, row in r.table().loc[["own_weekly", "own_monthly"]].iterrows():
        rows.append({"spec": "+ holiday controls", "term": term, **row.to_dict(), "n": r.nobs})
    # holiday-shifted expiries only: other own expiries are dropped from the sample. A shifted
    # expiry is always the session before a holiday, so pre-holiday days are controlled for.
    hs = p[(p["own"] == 0) | (p["shifted"] == 1)]
    r = fe_ols(hs, y, ["own", "other_major", "other_minor", "pre_holiday", "post_holiday"], MAIN_FE)
    row = r.table().loc["own"]
    rows.append({"spec": "Holiday-shifted expiries only (any own)", "term": "own", **row.to_dict(), "n": r.nobs})
    return pd.DataFrame(rows)


def relative_to(panel: pd.DataFrame, base: str, y: str) -> pd.DataFrame:
    """Outcome minus the same outcome of index `base` on the same day (base rows dropped)."""
    b = panel.loc[panel["index"] == base, ["date", y]].rename(columns={y: "_base"})
    out = panel[panel["index"] != base].merge(b, on="date", how="inner")
    out[y] = out[y] - out["_base"]
    return out.drop(columns="_base")


# ------------------------------------------------------------------------ event studies
def event_window(event: ex.Event, weeks: int = 26) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Window around an event, cut at the previous and the next calendar change of the same
    index's own options (so that each window contains exactly one change)."""
    d = pd.Timestamp(event.date)
    lo, hi = d - pd.Timedelta(weeks=weeks), d + pd.Timedelta(weeks=weeks) - pd.Timedelta(days=1)
    for c in ex.change_dates(ex.OWN_PRODUCT[event.index]):
        if c < d:
            lo = max(lo, c)
        elif c > d:
            hi = min(hi, c - pd.Timedelta(days=1))
    return lo, hi


def weekday_profile(panel: pd.DataFrame, index: str, lo, hi, y: str = "lgk") -> pd.DataFrame:
    """Average volatility of each weekday relative to the rest of its week (weeks with >= 4 sessions)."""
    s = panel[(panel["index"] == index) & (panel["date"] >= pd.Timestamp(lo)) & (panel["date"] <= pd.Timestamp(hi))].copy()
    size = s.groupby("week")[y].transform("size")
    s = s[size >= 4]
    s["dev"] = s[y] - s.groupby("week")[y].transform("mean")
    g = s.groupby("wd")["dev"]
    out = pd.DataFrame({"mean": g.mean(), "se": g.std() / np.sqrt(g.count()), "n": g.count()})
    out.index = [ex.WEEKDAY_NAMES[i] for i in out.index]
    return out


def event_did(panel: pd.DataFrame, event: ex.Event, y: str = "lgk", weeks: int = 26) -> pd.DataFrame:
    """Difference-in-differences for one event: change in the volatility of the weekday that
    gained (lost) an expiry, relative to the other weekdays, after vs. before the change.
    Also reports the effect of the actual expiry indicator estimated within the window."""
    lo, hi = event_window(event, weeks)
    s = panel[(panel["index"] == event.index) & (panel["date"] >= lo) & (panel["date"] <= hi)].copy()
    post = (s["date"] >= pd.Timestamp(event.date)).astype(int)
    x = []
    if event.gain:
        s["gain_post"] = s["wd"].isin(event.gain).astype(int) * post
        x.append("gain_post")
    if event.lose:
        s["lose_post"] = s["wd"].isin(event.lose).astype(int) * post
        x.append("lose_post")
    r = fe_ols(s, y, x, (("wd",), ("week",)))
    t = r.table()
    t["event"], t["index"], t["date"], t["n"] = event.name, event.index, event.date, r.nobs
    t["pre_days"] = int((post == 0).sum())
    t["post_days"] = int((post == 1).sum())
    return t.rename_axis("term").reset_index()


def stacked_events(panel: pd.DataFrame, events, y: str = "lgk", weeks: int = 26, controls=()) -> pd.DataFrame:
    """Average effect across events of a weekday gaining / losing an expiry (stacked design:
    each event keeps its own weekday and week effects; errors clustered by calendar week)."""
    parts = []
    for k, ev in enumerate(events):
        lo, hi = event_window(ev, weeks)
        s = panel[(panel["index"] == ev.index) & (panel["date"] >= lo) & (panel["date"] <= hi)].copy()
        post = (s["date"] >= pd.Timestamp(ev.date)).astype(int)
        s["gain_post"] = s["wd"].isin(ev.gain).astype(int) * post
        s["lose_post"] = s["wd"].isin(ev.lose).astype(int) * post
        s["ev"] = k
        parts.append(s)
    st = pd.concat(parts, ignore_index=True)
    r = fe_ols(st, y, ["gain_post", "lose_post"] + list(controls), (("ev", "wd"), ("ev", "week")), drop_absorbed=True)
    t = r.table().loc[["gain_post", "lose_post"]]
    t["n"] = r.nobs
    t["events"] = len(events)
    return t.rename_axis("term").reset_index()


def event_time(panel: pd.DataFrame, events, y: str = "lgk", weeks: int = 26, bin_weeks: int = 8) -> pd.DataFrame:
    """Stacked event-time profile: volatility of the gained-minus-lost weekday contrast in
    bins of `bin_weeks` weeks relative to the change (the bin just before is the reference)."""
    parts = []
    for k, ev in enumerate(events):
        lo, hi = event_window(ev, weeks)
        s = panel[(panel["index"] == ev.index) & (panel["date"] >= lo) & (panel["date"] <= hi)].copy()
        rel = (s["date"] - pd.Timestamp(ev.date)).dt.days // (7 * bin_weeks)
        s["bin"] = rel.astype(int)
        s["sign"] = np.where(s["wd"].isin(ev.gain), 1, np.where(s["wd"].isin(ev.lose), -1, 0))
        s["ev"] = k
        parts.append(s)
    st = pd.concat(parts, ignore_index=True)
    bins = sorted(b for b in st["bin"].unique() if b != -1)
    x = []
    for b in bins:
        col = f"b{b}"
        st[col] = (st["bin"] == b).astype(int) * st["sign"]
        x.append(col)
    # drop bins with too little data
    x = [c for c in x if (st[c] != 0).sum() >= 15]
    r = fe_ols(st, y, x, (("ev", "wd"), ("ev", "week")))
    t = r.table().rename_axis("term").reset_index()
    t["bin"] = t["term"].str[1:].astype(int)
    ref = pd.DataFrame({"term": ["b-1"], "coef": [0.0], "se": [0.0], "t": [np.nan], "p": [np.nan],
                        "lo": [0.0], "hi": [0.0], "bin": [-1]})
    return pd.concat([t, ref]).sort_values("bin").reset_index(drop=True)


# ------------------------------------------------------------------------ randomization inference
def placebo_distribution(panel: pd.DataFrame, trading_days, n_draws: int = 1000, seed: int = 7,
                         y: str = "lgk") -> pd.DataFrame:
    """Re-estimate the pooled main regression with placebo calendars (random weekdays, real dates).

    Returns one row per draw with the placebo coefficients of own_weekly and own_monthly.
    """
    rng = np.random.default_rng(seed)
    base = panel.drop(columns=[c for c in ["own", "own_weekly", "own_monthly", "other_major",
                                            "other_minor", "shifted"] if c in panel.columns])
    groups_cache = None
    out = []
    for draw in range(n_draws):
        rules = ex.placebo_rules(rng)
        table = ex.expiry_table(trading_days, rules=rules)
        flags = pd.concat([ex.expiry_flags(table, idx).assign(index=idx) for idx in panel["index"].unique()])
        flags = flags.rename_axis("date").reset_index()
        d = base.merge(flags, on=["date", "index"], how="left")
        try:
            r = fe_ols(d, y, TREAT, MAIN_FE)
            out.append({"draw": draw, **{f"b_{k}": v for k, v in r.params.items()}})
        except (ValueError, np.linalg.LinAlgError):
            continue
    return pd.DataFrame(out)


def ri_pvalue(actual: float, placebo: pd.Series) -> float:
    """Two-sided randomization p-value: share of placebo estimates at least as large in size."""
    placebo = placebo.dropna()
    return float((1 + (placebo.abs() >= abs(actual)).sum()) / (1 + len(placebo)))


# ------------------------------------------------------------------------ weekly totals (H6)
def has_weekly_options(index: str, days) -> np.ndarray:
    """1 if the index's own options had weekly contracts under the rule in force on each day."""
    days = pd.DatetimeIndex(days)
    out = np.zeros(len(days), dtype=int)
    for r in ex.PRODUCTS[ex.OWN_PRODUCT[index]]:
        m = (days >= pd.Timestamp(r.start)) & (days <= pd.Timestamp(r.end))
        out[m] = int(r.weekly is not None)
    return out


def weekly_totals(panel: pd.DataFrame, y_col: str = "rv") -> pd.DataFrame:
    """One row per index and week: log of the average daily variance in that week, and whether
    the index had weekly options. Weeks with fewer than 4 sessions are dropped."""
    p = panel.copy()
    p["weekly_regime"] = 0
    for idx in p["index"].unique():
        m = p["index"] == idx
        p.loc[m, "weekly_regime"] = has_weekly_options(idx, p.loc[m, "date"])
    w = p.groupby(["index", "week"]).agg(v=(y_col, "mean"), n=(y_col, "size"),
                                         weekly_regime=("weekly_regime", "max"),
                                         n_own=("own", "sum"), date=("date", "min")).reset_index()
    w = w[w["n"] >= 4].copy()
    w["lv"] = np.log(w["v"])
    return w


def weekly_total_test(panel: pd.DataFrame) -> pd.DataFrame:
    """Do weekly options raise an index's total weekly volatility? (index and week effects;
    identified by launches and removals of weekly contracts relative to the other indices)."""
    rows = []
    for y_col, label in [("rv", "close-to-close"), ("gk", "session (Garman-Klass)")]:
        w = weekly_totals(panel, y_col)
        r = fe_ols(w, "lv", ["weekly_regime"], (("index",), ("week",)), cluster="week", time_col="week")
        rows.append({"measure": label, **r.table().loc["weekly_regime"].to_dict(), "n": r.nobs})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------ effects by period (H7)
PERIODS = [("2014-01-01", "2018-12-31", "2014-18"),
           ("2019-01-01", "2023-12-31", "2019-23 (minute data: 2021-23)"),
           ("2024-01-01", "2024-11-19", "2024 to SEBI measures"),
           ("2024-11-20", "2025-07-02", "SEBI measures to interim order"),
           ("2025-07-03", "2026-07-31", "after interim order")]


def period_effects(panel: pd.DataFrame, y: str, periods=PERIODS, by_index: bool = False,
                   cross: bool = True) -> pd.DataFrame:
    """The expiry effect estimated separately in each period (pooled, or per index).

    Within a short period an index's expiry weekday hardly changes, so index x weekday
    effects would absorb almost all of the variation. With `cross=True` (default) the
    comparison is instead across indices on the same weekday: index x week effects plus
    weekday effects common to all indices in the period. Per-index estimates keep the
    within-index design (index x weekday is then just weekday)."""
    rows = []
    groups = panel.groupby("index") if by_index else [("pooled", panel)]
    for name, sub in groups:
        if name == "pooled":
            fe = (("index", "week"), ("wd",)) if cross else MAIN_FE
        else:
            fe = (("wd",), ("week",))
        for lo, hi, label in periods:
            s = sub[(sub["date"] >= lo) & (sub["date"] <= hi)]
            if len(s) < 50:
                continue
            x = [c for c in TREAT if s[c].nunique() > 1]
            try:
                r = fe_ols(s, y, x, fe)
            except (ValueError, np.linalg.LinAlgError):
                x = [c for c in x if c != "other_minor"]
                r = fe_ols(s, y, x, fe)
            t = r.table()
            for term in [c for c in ["own_weekly", "own_monthly", "other_major"] if c in t.index]:
                rows.append({"sample": name, "period": label, "from": lo, "to": hi, "term": term,
                             **t.loc[term].to_dict(), "n": r.nobs, "n_treated": int(s[term].sum())})
    return pd.DataFrame(rows)


def period_effects_by_index(panel: pd.DataFrame, y: str, periods=PERIODS) -> pd.DataFrame:
    """Each index's own-expiry effect in each period, compared with the other indices on the
    same weekday and week (index x week effects + common weekday effects). Unlike a within-index
    comparison, this does not need the index's expiry weekday to change within the period."""
    rows = []
    idx_list = sorted(panel["index"].unique())
    for lo, hi, label in periods:
        s = panel[(panel["date"] >= lo) & (panel["date"] <= hi)].copy()
        x = []
        for idx in idx_list:
            col = f"own_{idx}"
            s[col] = s["own"] * (s["index"] == idx)
            if s[col].sum() >= 5:
                x.append(col)
        x += [c for c in ["other_major"] if s[c].nunique() > 1]
        r = fe_ols(s, y, x, (("index", "week"), ("wd",)), drop_absorbed=True)
        t = r.table()
        for idx in idx_list:
            col = f"own_{idx}"
            if col in t.index:
                rows.append({"sample": idx, "period": label, "from": lo, "to": hi, "term": "own (any)",
                             **t.loc[col].to_dict(), "n": r.nobs, "n_treated": int(s[col].sum())})
    return pd.DataFrame(rows)
