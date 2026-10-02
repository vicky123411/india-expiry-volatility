"""The expiry calendar: rules, holiday shifts, placebo calendars and agreement with exchange files."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from expiryvol import expiries as ex
from expiryvol.data import trading_days

DATA = Path(__file__).parent / "data"
TD = trading_days("2013-06-03", "2026-09-30")


def test_weekly_and_monthly_on_known_dates():
    e = ex.expiry_dates("NIFTY", TD, "2019-02-01", "2019-03-31").set_index("date")
    assert pd.Timestamp("2019-02-14") in e.index            # first weekly Nifty expiry
    assert e.loc["2019-02-28", "kind"] == "monthly"          # last Thursday of February
    assert pd.Timestamp("2019-02-07") not in e.index         # before weekly options


def test_holiday_moves_expiry_to_previous_trading_day():
    # 29 Jun 2023 (Thursday) was a holiday: Nifty's monthly expiry moved to Wednesday 28 Jun
    e = ex.expiry_dates("NIFTY", TD, "2023-06-20", "2023-06-30").set_index("date")
    assert e.loc["2023-06-28", "shifted"]
    assert pd.Timestamp("2023-06-29") not in e.index


def test_no_weekly_in_monthly_week_when_weekdays_differ():
    # Bank Nifty, Sep 2023: weekly on Wednesday, monthly on the last Thursday (28 Sep)
    e = ex.expiry_dates("BANKNIFTY", TD, "2023-09-01", "2023-09-30")
    assert list(e["date"].dt.strftime("%m-%d")) == ["09-06", "09-13", "09-20", "09-28"]


def test_calendar_switches():
    nifty = ex.expiry_dates("NIFTY", TD, "2025-08-20", "2025-09-12")["date"].dt.strftime("%m-%d %a").tolist()
    assert nifty == ["08-21 Thu", "08-28 Thu", "09-02 Tue", "09-09 Tue"]
    sensex = ex.expiry_dates("SENSEX", TD, "2024-12-20", "2025-01-15")["date"].dt.strftime("%m-%d %a").tolist()
    assert sensex == ["12-20 Fri", "12-27 Fri", "01-03 Fri", "01-07 Tue", "01-14 Tue"]


@pytest.mark.parametrize("symbol", ["NIFTY", "BANKNIFTY"])
def test_matches_nse_contract_files(symbol):
    """Every expiry day seen in NSE's F&O files (2014 - Jun 2026) is predicted, and vice versa
    (except days missing from the files). The lists in tests/data are written by scripts/run_all.py."""
    obs = pd.DatetimeIndex(pd.to_datetime(pd.read_csv(DATA / f"observed_expiries_{symbol}.csv")["date"]))
    rule = ex.expiry_dates(symbol, TD, "2014-01-01", str(obs.max().date()))["date"]
    missing_from_files = {pd.Timestamp("2020-11-05"), pd.Timestamp("2020-11-12")}
    assert set(obs) == set(rule) - missing_from_files


def test_matches_sensex_option_files():
    files = pd.to_datetime(pd.read_csv(DATA / "hf_option_files_SENSEX.csv")["expiry"])
    rule = set(ex.expiry_dates("SENSEX", TD, str(files.min().date()), str(files.max().date()))["date"])
    assert set(files) <= rule                      # every file is an expiry day under the rules


def test_flags_and_table():
    tab = ex.expiry_table(TD)
    f = ex.expiry_flags(tab, "nifty50")
    assert f.loc["2024-04-04", "own_weekly"] == 1 and f.loc["2024-04-04", "other_major"] == 0
    assert f.loc["2024-04-03", "other_major"] == 1       # Bank Nifty's Wednesday expiry
    # Friday 8 Mar 2024 was a holiday, so Sensex expired on Thursday 7 Mar, with Nifty
    assert f.loc["2024-03-07", "own_weekly"] == 1 and f.loc["2024-03-07", "other_major"] == 1
    assert f.loc["2024-03-28", "own_monthly"] == 1
    assert set(np.unique(tab["NIFTY"])) <= {0, 1, 2}


def test_placebo_rules_keep_dates_and_structure():
    rng = np.random.default_rng(0)
    pl = ex.placebo_rules(rng)
    for product, rules in ex.PRODUCTS.items():
        assert [(r.start, r.end) for r in rules] == [(r.start, r.end) for r in pl[product]]
        for real, fake in zip(rules, pl[product]):
            assert (real.weekly is None) == (fake.weekly is None)
            assert (real.monthly is None) == (fake.monthly is None)
            if real.weekly is not None and real.weekly == real.monthly:
                assert fake.weekly == fake.monthly
