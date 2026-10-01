"""The expiry calendar of Indian index options, 2014-2026.

Each option product (NIFTY, BANKNIFTY, ...) follows a rule such as "weekly contracts
expire every Thursday; the monthly contract expires on the last Thursday of the month".
The exchanges changed these rules many times. Every change is listed below with its
effective date. These changes are the natural experiments of the study: if expiry makes
an index more (or less) volatile, the unusual day should move when the expiry day moves.

Three rules apply to every product and period:
* Holiday rule: if the scheduled day is not a trading day, the contracts expire on the
  previous trading day.
* Weekly contracts are not listed in the week in which the monthly contract expires, so
  that week has a single expiry (the monthly one). This matters only when the weekly and
  monthly weekdays differ (e.g. Bank Nifty from Sep 2023 to Feb 2024: weekly Wednesday,
  monthly last Thursday).
* A day can be the expiry day of several products at once (e.g. Nifty and Bank Nifty on
  Thursdays before Sep 2023).

Weekdays are numbered as in pandas: 0 = Monday, 1 = Tuesday, ..., 4 = Friday.
The calendar is checked against the expiry dates found in NSE's own contract files
(tests/test_expiries.py and notebook 0).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

MON, TUE, WED, THU, FRI = range(5)
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri"]
FAR_FUTURE = "2099-12-31"


@dataclass(frozen=True)
class Rule:
    """One expiry rule of one product, valid from `start` to `end` (calendar days, inclusive)."""
    start: str
    end: str
    weekly: int | None    # weekday of the weekly expiry, or None if there are no weekly contracts
    monthly: int | None   # the monthly contract expires on the LAST such weekday of the month
    note: str = ""


# ---------------------------------------------------------------------------------------
# The rules. Sources are listed in the README and in the paper (Section 2, Table 1).
# ---------------------------------------------------------------------------------------
PRODUCTS: dict[str, list[Rule]] = {
    # NSE, Nifty 50 index options
    "NIFTY": [
        Rule("2000-01-01", "2019-02-10", None, THU, "monthly contracts only"),
        Rule("2019-02-11", "2025-08-31", THU, THU, "weekly options launched 11 Feb 2019 (Thursday)"),
        Rule("2025-09-01", FAR_FUTURE, TUE, TUE, "NSE moves all expiries to Tuesday (last Thursday expiry 28 Aug 2025)"),
    ],
    # NSE, Nifty Bank index options
    "BANKNIFTY": [
        Rule("2000-01-01", "2016-05-26", None, THU, "monthly contracts only"),
        Rule("2016-05-27", "2023-09-03", THU, THU, "weekly options launched 27 May 2016 (Thursday)"),
        Rule("2023-09-04", "2024-02-29", WED, THU, "weekly moved to Wednesday (first 6 Sep 2023); monthly stays last Thursday"),
        Rule("2024-03-01", "2024-11-19", WED, WED, "monthly moved to last Wednesday (first 27 Mar 2024)"),
        Rule("2024-11-20", "2025-01-01", None, WED, "weekly contracts discontinued (SEBI; last weekly 13 Nov 2024)"),
        Rule("2025-01-02", "2025-08-31", None, THU, "monthly moved to last Thursday (NSE circular, 29 Nov 2024)"),
        Rule("2025-09-01", FAR_FUTURE, None, TUE, "monthly moved to last Tuesday"),
    ],
    # BSE, Sensex index options (relaunched 15 May 2023; earlier contracts barely traded)
    "SENSEX": [
        Rule("2023-05-15", "2025-01-03", FRI, FRI, "relaunched 15 May 2023 with Friday expiry"),
        Rule("2025-01-04", "2025-08-31", TUE, TUE, "moved to Tuesday from 1 Jan 2025 (last Friday expiry 3 Jan, first Tuesday 7 Jan)"),
        Rule("2025-09-01", FAR_FUTURE, THU, THU, "moved to Thursday from 1 Sep 2025"),
    ],
    # NSE, Nifty Financial Services index options (no index prices used; expiry days only)
    "FINNIFTY": [
        Rule("2021-01-11", "2021-10-14", THU, THU, "launched 11 Jan 2021 (Thursday)"),
        Rule("2021-10-15", "2024-11-19", TUE, TUE, "moved to Tuesday (first 19 Oct 2021)"),
        Rule("2024-11-20", "2025-01-01", None, TUE, "weekly contracts discontinued (last weekly 19 Nov 2024)"),
        Rule("2025-01-02", "2025-08-31", None, THU, "monthly moved to last Thursday"),
        Rule("2025-09-01", FAR_FUTURE, None, TUE, "monthly moved to last Tuesday"),
    ],
    # NSE, Nifty Midcap Select index options (25 mid-cap stocks)
    "MIDCPNIFTY": [
        Rule("2022-01-24", "2023-08-16", TUE, TUE, "launched 24 Jan 2022 (Tuesday)"),
        Rule("2023-08-17", "2024-11-18", MON, MON, "moved to Monday (first 21 Aug 2023)"),
        Rule("2024-11-19", "2025-01-01", None, MON, "weekly contracts discontinued (last weekly 18 Nov 2024)"),
        Rule("2025-01-02", "2025-08-31", None, THU, "monthly moved to last Thursday"),
        Rule("2025-09-01", FAR_FUTURE, None, TUE, "monthly moved to last Tuesday"),
    ],
    # BSE, Bankex index options
    "BANKEX": [
        Rule("2023-05-15", "2023-10-15", FRI, FRI, "relaunched 15 May 2023 with Friday expiry"),
        Rule("2023-10-16", "2024-11-18", MON, MON, "moved to Monday from 16 Oct 2023"),
        Rule("2024-11-19", "2024-12-31", None, MON, "weekly contracts discontinued (last weekly 18 Nov 2024)"),
        Rule("2025-01-01", "2025-08-31", None, TUE, "monthly moved to last Tuesday"),
        Rule("2025-09-01", FAR_FUTURE, None, THU, "monthly moved to last Thursday"),
    ],
}

# Which option product belongs to which index in the price data.
# Nifty Midcap Select (MIDCPNIFTY) is not the same index as Nifty Midcap 50, but its
# 25 stocks are mid-caps of the same kind, so its expiries are the mid-cap index's "own".
OWN_PRODUCT = {"nifty50": "NIFTY", "banknifty": "BANKNIFTY", "sensex": "SENSEX", "midcap50": "MIDCPNIFTY"}
MAJOR_PRODUCTS = ("NIFTY", "BANKNIFTY", "SENSEX")
MINOR_PRODUCTS = ("FINNIFTY", "MIDCPNIFTY", "BANKEX")


@dataclass(frozen=True)
class Event:
    """A change in one index's own expiry calendar (one natural experiment)."""
    name: str
    index: str                       # key of OWN_PRODUCT
    date: str                        # first calendar day of the new rule
    gain: tuple[int, ...] = ()       # weekdays that become (weekly) expiry days
    lose: tuple[int, ...] = ()       # weekdays that stop being (weekly) expiry days
    major: bool = True               # False for small option markets (Midcap Select)
    tags: tuple[str, ...] = field(default=())


EVENTS: list[Event] = [
    Event("Bank Nifty weekly launch (Thu)", "banknifty", "2016-05-27", gain=(THU,)),
    Event("Nifty weekly launch (Thu)", "nifty50", "2019-02-11", gain=(THU,)),
    Event("Midcap Select launch (Tue)", "midcap50", "2022-01-24", gain=(TUE,), major=False),
    Event("Sensex relaunch (Fri)", "sensex", "2023-05-15", gain=(FRI,)),
    Event("Midcap Select Tue to Mon", "midcap50", "2023-08-17", gain=(MON,), lose=(TUE,), major=False),
    Event("Bank Nifty Thu to Wed", "banknifty", "2023-09-04", gain=(WED,), lose=(THU,)),
    Event("Midcap Select weekly removed (Mon)", "midcap50", "2024-11-19", lose=(MON,), major=False),
    Event("Bank Nifty weekly removed (Wed)", "banknifty", "2024-11-20", lose=(WED,)),
    Event("Sensex Fri to Tue", "sensex", "2025-01-04", gain=(TUE,), lose=(FRI,)),
    Event("Nifty Thu to Tue", "nifty50", "2025-09-01", gain=(TUE,), lose=(THU,)),
    Event("Sensex Tue to Thu", "sensex", "2025-09-01", gain=(THU,), lose=(TUE,)),
]

# Other dated market-structure changes used in the analysis.
POLICY_DATES = {
    "sebi_nov2024": "2024-11-20",   # SEBI index-derivatives measures: one weekly product per exchange,
                                    # larger contracts, extra 2% margin on short options on expiry day
    "sebi_order_jul2025": "2025-07-03",  # SEBI interim order on alleged expiry-day index manipulation
    "closing_auction": "2026-08-03",     # closing auction session replaces the 30-minute VWAP close
}


# ---------------------------------------------------------------------------------------
def _last_weekday_of_month(year: int, month: int, weekday: int) -> pd.Timestamp:
    last = pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)
    return last - pd.Timedelta(days=(last.weekday() - weekday) % 7)


def _week_key(day: pd.Timestamp) -> tuple[int, int]:
    iso = day.isocalendar()
    return int(iso[0]), int(iso[1])


def scheduled_dates(product: str, start: str, end: str, rules: dict | None = None) -> pd.DataFrame:
    """Scheduled (pre-holiday) expiry dates of one product between `start` and `end`.

    Returns columns `scheduled` (date) and `kind` ("weekly" or "monthly").
    `rules` replaces the real calendar (PRODUCTS), e.g. by a placebo calendar.
    """
    rules = PRODUCTS if rules is None else rules
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    monthly, weekly = [], []
    for rule in rules[product]:
        r_lo = max(pd.Timestamp(rule.start), lo - pd.Timedelta(days=40))
        r_hi = min(pd.Timestamp(rule.end), hi + pd.Timedelta(days=40))
        if r_lo > r_hi:
            continue
        if rule.monthly is not None:
            for period in pd.period_range(r_lo, r_hi, freq="M"):
                day = _last_weekday_of_month(period.year, period.month, rule.monthly)
                if pd.Timestamp(rule.start) <= day <= pd.Timestamp(rule.end):
                    monthly.append(day)
        if rule.weekly is not None:
            first = r_lo + pd.Timedelta(days=(rule.weekly - r_lo.weekday()) % 7)
            for day in pd.date_range(first, r_hi, freq="7D"):
                if pd.Timestamp(rule.start) <= day <= pd.Timestamp(rule.end):
                    weekly.append(day)
    monthly = sorted(set(monthly))
    monthly_weeks = {_week_key(d) for d in monthly}
    weekly = sorted(d for d in set(weekly) if d not in set(monthly) and _week_key(d) not in monthly_weeks)
    out = pd.DataFrame({"scheduled": monthly + weekly, "kind": ["monthly"] * len(monthly) + ["weekly"] * len(weekly)})
    out = out[(out.scheduled >= lo - pd.Timedelta(days=10)) & (out.scheduled <= hi + pd.Timedelta(days=10))]
    return out.sort_values("scheduled").reset_index(drop=True)


def _as_days(trading_days) -> pd.DatetimeIndex:
    """Sorted, unique, time-free dates from any list-like of dates."""
    return pd.DatetimeIndex(sorted(pd.DatetimeIndex(pd.to_datetime(trading_days)).normalize().unique()))


def expiry_dates(product: str, trading_days, start: str | None = None, end: str | None = None,
                 rules: dict | None = None) -> pd.DataFrame:
    """Actual expiry days of one product: scheduled dates moved to the previous trading day
    when they fall on a holiday.

    `trading_days` must cover the whole period (a list of dates on which the exchange traded).
    Returns columns `date` (the expiry day), `kind`, `scheduled` and `shifted` (True if moved by a holiday).
    """
    days = _as_days(trading_days)
    start = start or str(days[0].date())
    end = end or str(days[-1].date())
    sched = scheduled_dates(product, start, end, rules)
    pos = days.searchsorted(sched["scheduled"].to_numpy(), side="right") - 1   # last trading day <= scheduled
    ok = pos >= 0
    sched = sched[ok].copy()
    sched["date"] = days[pos[ok]]
    sched["shifted"] = sched["date"] != sched["scheduled"]
    sched = sched[(sched["date"] >= pd.Timestamp(start)) & (sched["date"] <= pd.Timestamp(end))]
    # a shifted weekly date can land on the same day as another expiry of the product: keep one row
    sched = sched.sort_values(["date", "kind"]).drop_duplicates("date", keep="first")  # "monthly" sorts first
    return sched[["date", "kind", "scheduled", "shifted"]].reset_index(drop=True)


def expiry_table(trading_days, products=None, rules: dict | None = None) -> pd.DataFrame:
    """One row per trading day, one column per product: 0 = no expiry, 1 = weekly expiry,
    2 = monthly expiry. Extra columns `<product>_shifted` mark expiries moved by a holiday."""
    rules = PRODUCTS if rules is None else rules
    products = tuple(rules) if products is None else tuple(products)
    days = _as_days(trading_days)
    out = pd.DataFrame(index=days)
    for product in products:
        e = expiry_dates(product, days, rules=rules).set_index("date")
        code = pd.Series(0, index=days, dtype=int)
        code.loc[e.index[e.kind == "weekly"]] = 1
        code.loc[e.index[e.kind == "monthly"]] = 2
        out[product] = code
        shifted = pd.Series(False, index=days)
        shifted.loc[e.index[e.shifted]] = True
        out[f"{product}_shifted"] = shifted
    return out


def expiry_flags(table: pd.DataFrame, index: str) -> pd.DataFrame:
    """Expiry indicators for one index (key of OWN_PRODUCT), one row per trading day.

    own          the index's own options expire today (weekly or monthly)
    own_weekly   ... a weekly (non-monthly) contract
    own_monthly  ... the monthly contract (also the day index futures expire)
    other_major  options on another major index (Nifty, Bank Nifty, Sensex) expire today
    other_minor  options on a smaller index (Fin Nifty, Midcap Select, Bankex) expire today
    shifted      today's own expiry was moved here by a holiday
    """
    own = OWN_PRODUCT[index]
    f = pd.DataFrame(index=table.index)
    f["own"] = (table[own] > 0).astype(int)
    f["own_weekly"] = (table[own] == 1).astype(int)
    f["own_monthly"] = (table[own] == 2).astype(int)
    f["other_major"] = (table[[p for p in MAJOR_PRODUCTS if p != own]] > 0).any(axis=1).astype(int)
    f["other_minor"] = (table[[p for p in MINOR_PRODUCTS if p != own]] > 0).any(axis=1).astype(int)
    f["shifted"] = table[f"{own}_shifted"].astype(int)
    return f


def regime_label(product: str, day) -> str:
    """Short description of the rule in force on `day` (for tables and plots)."""
    day = pd.Timestamp(day)
    for rule in PRODUCTS[product]:
        if pd.Timestamp(rule.start) <= day <= pd.Timestamp(rule.end):
            w = WEEKDAY_NAMES[rule.weekly] if rule.weekly is not None else "none"
            m = f"last {WEEKDAY_NAMES[rule.monthly]}" if rule.monthly is not None else "none"
            return f"weekly: {w}; monthly: {m}"
    return "no listed options"


def rules_table() -> pd.DataFrame:
    """All rules of all products as a table (Table 1 of the paper)."""
    rows = []
    for product, rules in PRODUCTS.items():
        for r in rules:
            rows.append({"product": product, "from": r.start, "to": r.end if r.end != FAR_FUTURE else "",
                         "weekly": WEEKDAY_NAMES[r.weekly] if r.weekly is not None else "-",
                         "monthly": f"last {WEEKDAY_NAMES[r.monthly]}" if r.monthly is not None else "-",
                         "note": r.note})
    return pd.DataFrame(rows)


def change_dates(product: str, rules: dict | None = None) -> list[pd.Timestamp]:
    """First days of every rule of a product after its first one (dates on which its calendar changed)."""
    rules = PRODUCTS if rules is None else rules
    return [pd.Timestamp(r.start) for r in rules[product][1:]]


def placebo_rules(rng: np.random.Generator, rules: dict | None = None) -> dict[str, list[Rule]]:
    """A placebo calendar: every rule keeps its dates, but its weekdays are drawn at random.

    When a rule has the same weekday for weekly and monthly contracts, the placebo keeps
    them on one (random) weekday; otherwise the two are drawn separately. Used for
    randomization inference: if expiry had no effect, the real calendar's estimate would
    look like a typical estimate from these placebo calendars.
    """
    rules = PRODUCTS if rules is None else rules
    out = {}
    for product, product_rules in rules.items():
        new = []
        for r in product_rules:
            w = int(rng.integers(5)) if r.weekly is not None else None
            if r.monthly is None:
                m = None
            elif r.weekly is not None and r.monthly == r.weekly:
                m = w
            else:
                m = int(rng.integers(5))
            new.append(replace(r, weekly=w, monthly=m, note="placebo"))
        out[product] = new
    return out


def compare_with_actual(product: str, actual_dates, trading_days, start: str, end: str) -> pd.DataFrame:
    """Rule-based expiry days vs. expiry days observed in exchange contract files.

    Returns one row per date that appears in either list, with columns `rule` and `actual`
    (True/False). Used by the tests and the data notebook.
    """
    days = _as_days(trading_days)
    rule = set(expiry_dates(product, days, start, end)["date"])
    actual = {pd.Timestamp(d) for d in pd.to_datetime(actual_dates)}
    actual = {d for d in actual if pd.Timestamp(start) <= d <= pd.Timestamp(end)}
    every = sorted(rule | actual)
    return pd.DataFrame({"date": every, "rule": [d in rule for d in every], "actual": [d in actual for d in every]})


def weekday_of(dates) -> np.ndarray:
    return pd.DatetimeIndex(dates).weekday.to_numpy()
