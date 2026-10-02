"""The fixed-effects estimator against textbook OLS with dummy variables (synthetic data)."""
import numpy as np
import pandas as pd
import pytest
import statsmodels.formula.api as smf

from expiryvol import estimate as es


def synthetic(seed=1, n_weeks=120, effect=0.3):
    rng = np.random.default_rng(seed)
    rows = []
    for idx in ["a", "b", "c"]:
        for w in range(n_weeks):
            shock = rng.normal()
            for wd in range(5):
                treat = int(rng.random() < 0.2)
                y = 0.5 * shock + 0.1 * wd * (idx == "a") + effect * treat + rng.normal(scale=0.5)
                rows.append({"index": idx, "week": w, "wd": wd, "own": treat, "other": int(rng.random() < 0.3),
                             "y": y, "date": pd.Timestamp("2020-01-06") + pd.Timedelta(days=7 * w + wd)})
    return pd.DataFrame(rows)


# the reference model includes redundant dummies on purpose; statsmodels warns about that
@pytest.mark.filterwarnings("ignore:The design matrix is rank-deficient")
@pytest.mark.filterwarnings("ignore:invalid value encountered in sqrt:RuntimeWarning")
def test_matches_dummy_variable_ols():
    d = synthetic()
    r = es.fe_ols(d, "y", ["own", "other"], (("index", "wd"), ("index", "week")))
    d["iw"] = d["index"] + d["week"].astype(str)
    d["iwd"] = d["index"] + d["wd"].astype(str)
    ref = smf.ols("y ~ own + other + C(iw) + C(iwd)", data=d).fit(
        cov_type="cluster", cov_kwds={"groups": d["week"], "use_correction": False})
    assert np.allclose(r.params["own"], ref.params["own"], atol=1e-8)
    assert np.allclose(r.params["other"], ref.params["other"], atol=1e-8)
    # same clustered "sandwich"; ours adds the small-sample factor of reghdfe, which counts
    # only fixed effects that are not nested within clusters (here index x weekday: 15 - 1)
    n, G, k, k_fe = len(d), d["week"].nunique(), 2, 14
    c = G / (G - 1) * (n - 1) / (n - k - k_fe)
    assert np.isclose(r.se["own"], np.sqrt(c) * ref.bse["own"], rtol=1e-6)


def test_recovers_effect_and_null():
    d = synthetic(seed=3, effect=0.3)
    r = es.fe_ols(d, "y", ["own"], (("index", "wd"), ("index", "week")))
    assert abs(r.params["own"] - 0.3) < 4 * r.se["own"]
    d0 = synthetic(seed=4, effect=0.0)
    r0 = es.fe_ols(d0, "y", ["own"], (("index", "wd"), ("index", "week")))
    assert abs(r0.params["own"]) < 4 * r0.se["own"]


def test_absorbed_regressor_is_reported():
    d = synthetic()
    d["const_in_week"] = d["week"] % 2
    try:
        es.fe_ols(d, "y", ["own", "const_in_week"], (("index", "week"),))
        raise AssertionError("should have raised")
    except ValueError:
        pass
    r = es.fe_ols(d, "y", ["own", "const_in_week"], (("index", "week"),), drop_absorbed=True)
    assert list(r.params.index) == ["own"]


def test_driscoll_kraay_runs_and_is_positive():
    d = synthetic()
    r = es.fe_ols(d, "y", ["own"], (("index", "week"),), cov="dk")
    assert r.se["own"] > 0


def test_holm():
    p = pd.Series({"a": 0.01, "b": 0.04, "c": 0.03})
    adj = es.holm(p)
    assert np.isclose(adj["a"], 0.03) and np.isclose(adj["c"], 0.06) and np.isclose(adj["b"], 0.06)
