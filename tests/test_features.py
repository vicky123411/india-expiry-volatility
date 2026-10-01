"""Volatility measures (toy bars) and the one-minute measures (synthetic minute data)."""
import numpy as np
import pandas as pd

from expiryvol.features import daily_measures, distance_to_grid, minute_day_measures, minute_segments


def test_garman_klass_by_hand():
    bars = pd.DataFrame({"Open": [100.0, 101.0], "High": [102.0, 103.0], "Low": [99.0, 100.0], "Close": [101.0, 102.0]},
                        index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    m = daily_measures(bars)
    h, l, o, c = np.log(103), np.log(100), np.log(101), np.log(102)
    gk = 1e4 * (0.5 * (h - l) ** 2 - (2 * np.log(2) - 1) * (c - o) ** 2)
    assert np.isclose(m["gk"].iloc[1], gk)
    assert np.isclose(m["on"].iloc[1], 1e4 * (np.log(101) - np.log(101)) ** 2)
    assert np.isclose(m["ret"].iloc[1], 100 * (np.log(102) - np.log(101)))


def test_distance_to_grid():
    assert np.allclose(distance_to_grid([25000, 25025, 25010], 50), [0.0, 0.5, 0.2])


def _minute_day(day, price_path):
    idx = pd.date_range(f"{day} 09:15", f"{day} 15:29", freq="1min")
    p = pd.Series(price_path(len(idx)), index=idx)
    return pd.DataFrame({"Open": p.shift(1).fillna(p.iloc[0]), "High": p, "Low": p, "Close": p, "day": pd.Timestamp(day)})


def test_minute_measures_constant_and_jump():
    flat = _minute_day("2024-01-02", lambda n: np.full(n, 100.0))
    m = minute_day_measures(flat)
    assert np.isclose(m["rv5"].iloc[0], 0) and np.isclose(m["rv_last"].iloc[0], 0)

    # a single 1% jump at 15:10 shows up in the last half hour only
    def path(n):
        x = np.full(n, 100.0)
        x[355:] = 101.0                     # 09:15 + 355 min = 15:10
        return x
    j = minute_day_measures(_minute_day("2024-01-03", path))
    assert np.isclose(j["rv_last"].iloc[0], 1e4 * np.log(1.01) ** 2)
    assert np.isclose(j["rv5"].iloc[0], 1e4 * np.log(1.01) ** 2)
    assert np.isclose(j["r_last"].iloc[0], 100 * np.log(1.01)) and np.isclose(j["r_rest"].iloc[0], 0)
    seg = minute_segments(_minute_day("2024-01-03", path), 15)
    hit = seg[seg["rv"] > 0]
    assert list(hit["start"]) == ["15:00"]
