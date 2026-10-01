"""The walk-forward forecast never trains on answers it could not yet know."""
import numpy as np
import pandas as pd

from expiryvol import forecast as fc


def frame(n=400, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2017-01-02", periods=n)
    rv = np.exp(rng.normal(size=n))
    f = pd.DataFrame(index=days)
    f["rv_d"] = rv
    f["rv_w"] = pd.Series(rv, index=days).rolling(5, min_periods=1).mean()
    f["rv_m"] = pd.Series(rv, index=days).rolling(22, min_periods=1).mean()
    f["gap_next"] = 1.0
    f["own_weekly_next"] = (days.weekday == 3).astype(int)
    f["own_monthly_next"] = 0                       # never varies: must be left out of the fit
    f["other_major_next"] = (days.weekday == 3).astype(int)   # repeats own_weekly_next exactly
    f["target"] = pd.Series(rv, index=days).shift(-1)
    f["target_day"] = pd.Series(days, index=days).shift(-1)
    return f.dropna()


def test_walk_forward_no_lookahead_and_rank_handling():
    F = frame()
    preds = fc.walk_forward(F, {"HAR": fc.HAR_COLS, "HAR+cal": fc.HAR_COLS + fc.EXPIRY_COLS}, "2017-09-01", refit_every=22)
    assert preds[["HAR", "HAR+cal"]].notna().all().all()
    m = fc.HAR(fc.HAR_COLS + fc.EXPIRY_COLS).fit(F)
    assert "own_monthly_next" not in m.used_ and "other_major_next" not in m.used_


def test_qlike_zero_at_truth():
    assert np.isclose(fc.qlike([2.0], [2.0])[0], 0.0)
    assert fc.qlike([2.0], [1.0])[0] > fc.qlike([2.0], [4.0])[0]   # under-forecasting costs more
