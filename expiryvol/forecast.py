"""Does knowing the expiry calendar improve next-day volatility forecasts? (Link to paper 1.)

Same set-up as paper 1 (vicky123411/nifty-volatility-ml-vs-econometrics):
* target: the next trading day's close-to-close variance = overnight gap squared + Garman-Klass;
* HAR model (Corsi, 2009), log-linear, fitted with the Gamma loss that matches QLIKE;
* walk-forward test on an expanding window, re-fitted every 22 trading days;
* QLIKE and MSE scores, Diebold-Mariano tests with Newey-West errors.

The expiry calendar is published in advance, so tomorrow's expiry indicators are known
today and can be used as inputs without any look-ahead.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tools.sm_exceptions import DomainWarning

warnings.filterwarnings("ignore", category=DomainWarning)

HAR_COLS = ["rv_d", "rv_w", "rv_m", "gap_next"]
EXPIRY_COLS = ["own_weekly_next", "own_monthly_next", "other_major_next"]
LOG_INPUTS = {"rv_d", "rv_w", "rv_m", "gap_next"}


def forecast_frame(panel: pd.DataFrame, index: str) -> pd.DataFrame:
    """One row per trading day t of one index: HAR inputs known at t's close, tomorrow's
    expiry indicators, and `target` = tomorrow's variance."""
    s = panel[panel["index"] == index].set_index("date").sort_index()
    f = pd.DataFrame(index=s.index)
    rv = s["rv"]
    f["rv_d"] = rv
    f["rv_w"] = rv.rolling(5).mean()
    f["rv_m"] = rv.rolling(22).mean()
    f["gap_next"] = s["next_gap"].astype(float)          # calendar days to the next session
    for col in ["own_weekly", "own_monthly", "other_major"]:
        f[f"{col}_next"] = s[col].shift(-1)
    f["target"] = rv.shift(-1)
    f["target_day"] = pd.Series(s.index, index=s.index).shift(-1)
    return f.dropna()


def _X(df: pd.DataFrame, cols) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    for c in cols:
        X[c] = np.log(df[c]) if c in LOG_INPUTS else df[c].astype(float)
    return sm.add_constant(X, has_constant="add")


class HAR:
    """HAR fitted with the Gamma / log-link loss (minimizes the same thing as QLIKE)."""

    def __init__(self, cols):
        self.cols = list(cols)

    def fit(self, train: pd.DataFrame) -> "HAR":
        # an indicator that never varies in the training data (e.g. Sensex expiries before
        # its options were relaunched) cannot be estimated: leave it out of this fit
        # an indicator that never varies, or that repeats other inputs exactly, in the training
        # data (e.g. Bank Nifty and Nifty monthly expiries before 2019) cannot be estimated
        # separately: leave it out of this fit
        self.used_, base = [], np.ones((len(train), 1))
        for c in self.cols:
            trial = np.column_stack([base, _X(train, [c])[c].to_numpy()])
            if np.linalg.matrix_rank(trial) > base.shape[1]:
                self.used_.append(c)
                base = trial
        X, y = _X(train, self.used_), train["target"]
        start = np.linalg.lstsq(X.to_numpy(), np.log(y.to_numpy()), rcond=None)[0]
        fam = sm.families.Gamma(link=sm.families.links.Log())
        self.res_ = sm.GLM(y, X, family=fam).fit(start_params=start, maxiter=200)
        return self

    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.res_.predict(_X(rows, self.used_)), dtype=float)


def qlike(actual, forecast) -> np.ndarray:
    r = np.asarray(actual, dtype=float) / np.asarray(forecast, dtype=float)
    return r - np.log(r) - 1


def dm_test(loss_a, loss_b) -> tuple[float, float]:
    """Diebold-Mariano with Newey-West errors; negative t means A has the smaller loss."""
    diff = np.asarray(loss_a, dtype=float) - np.asarray(loss_b, dtype=float)
    diff = diff[np.isfinite(diff)]
    lags = int(np.floor(4 * (len(diff) / 100) ** (2 / 9)))
    reg = sm.OLS(diff, np.ones(len(diff))).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return float(reg.tvalues[0]), float(reg.pvalues[0])


def walk_forward(frame: pd.DataFrame, models: dict, test_start: str, refit_every: int = 22) -> pd.DataFrame:
    """Expanding-window walk-forward test. Each block of `refit_every` days is forecast by
    models trained only on rows whose target day is before the block's first forecast origin."""
    first = int(np.searchsorted(frame.index, pd.Timestamp(test_start)))
    out = pd.DataFrame(index=frame.index[first:])
    out["actual"] = frame["target"].iloc[first:]
    out["target_day"] = frame["target_day"].iloc[first:]
    for name in models:
        out[name] = np.nan
    for start in range(first, len(frame), refit_every):
        block = frame.iloc[start:start + refit_every]
        # training rows: their answer (target day) must be known by the block's first origin
        train = frame[frame["target_day"] <= block.index[0]]
        assert train.index.max() < block.index[0]
        for name, cols in models.items():
            out.loc[block.index, name] = HAR(cols).fit(train).predict(block)
    return out


def evaluate(preds: pd.DataFrame, base: str, alt: str) -> dict:
    """Scores of two models and the DM test of alt vs base, on all days and on expiry days."""
    a = preds["actual"].to_numpy()
    res = {}
    for subset, mask in [("all days", np.ones(len(preds), bool)),
                         ("own expiry next day", preds["own_next"].to_numpy() == 1)]:
        qb, qa = qlike(a[mask], preds[base].to_numpy()[mask]), qlike(a[mask], preds[alt].to_numpy()[mask])
        mb = (a[mask] - preds[base].to_numpy()[mask]) ** 2
        ma = (a[mask] - preds[alt].to_numpy()[mask]) ** 2
        t, p = dm_test(qa, qb)
        tm, pm = dm_test(ma, mb)
        res[subset] = {"n": int(mask.sum()), "qlike_base": qb.mean(), "qlike_alt": qa.mean(),
                       "qlike_change_pct": 100 * (qa.mean() / qb.mean() - 1), "dm_t": t, "dm_p": p,
                       "mse_change_pct": 100 * (ma.mean() / mb.mean() - 1), "dm_t_mse": tm, "dm_p_mse": pm}
    return res
