# Analysis plan

**Study:** Does Options Expiry Move the Market? Natural Experiments from India's Changing Expiry Calendar

**Written:** 1 October 2026.

**What had been looked at before this plan was written:**
- average volatility by weekday in each expiry regime (a descriptive table);
- one set of baseline regressions (Section 5, first column).

Everything else below (robustness checks, event studies, mechanisms, policy tests, forecasting test) was specified here before it was run. The paper reports all of it, including results that are null or go the "wrong" way.

## 1. Question and hypotheses
India's index options are the most traded derivatives in the world, and almost all of the trading is in contracts that expire within days. Regulators (SEBI, Oct 2024) and the press often argue that expiry days make the market unstable. Theory allows both signs:
- **More volatility:** option writers who delta-hedge short positions buy as the index rises and sell as it falls (negative gamma), and traders may push the settlement price (the "marking the close" alleged in SEBI's July 2025 interim order).
- **Less volatility (pinning):** hedgers who are long gamma trade against moves, and writers of many short options gain if the index settles near their strikes.

Hypotheses (all two-sided):
- **H1 – expiry effect.** An index's session volatility differs on days when its own options expire.
- **H2 – the effect moves with the calendar.** When an expiry moves to another weekday, the abnormal volatility moves with it. Evidence: the natural experiments in Table 1 and holiday-shifted expiries.
- **H3 – spillovers.** Expiry of another large index's options changes an index's volatility (Nifty, Bank Nifty and Sensex share many stocks).
- **H4 – timing within the day.** Any expiry effect is concentrated in the settlement window (15:00–15:30, before Aug 2026) or at the open.
- **H5 – pinning.** On expiry days the index closes nearer to option strikes, and moves toward the strike with the most open interest.
- **H6 – shifted, not created.** Weekly options move volatility between weekdays without raising the week's total volatility.
- **H7 – regulation.** The expiry effect changed after SEBI's measures of 20 Nov 2024 and after the interim order of 3 Jul 2025.
- **H8 – forecasting.** A HAR model that knows the expiry calendar forecasts next-day volatility better than plain HAR (as in paper 1).

## 2. Data and sample
- **Daily bars (Yahoo Finance):** Nifty 50, Bank Nifty, Sensex, Nifty Midcap 50. Sample: 1 Jan 2014 – 31 Jul 2026. It ends before the closing auction session (3 Aug 2026), which changed how closing and settlement prices are set.
- **1-minute bars (Hugging Face, CC BY-NC 4.0):**
  - Nifty 50 and Bank Nifty: May 2021 – Jul 2026
  - Sensex: Sep 2022 – Jul 2026
- **NSE F&O contract files (bhavcopy):** Nifty and Bank Nifty options, 2014 – Jun 2026. Used to:
  - check the expiry calendar;
  - measure open interest by strike for the pinning test;
  - describe how option trading concentrates on expiry days.
- **Cleaning:**
  - Weekends, Muhurat sessions, incomplete bars and bars with High ≤ Low are dropped and logged.
  - Expiry days follow the published rules plus the holiday rule (if the scheduled day is a holiday, the contract expires on the previous trading day).
  - The rule-based calendar must match NSE's contract files on every day both cover.

## 3. Outcomes
- **Primary:** log Garman–Klass variance of the session (`lgk`).
- **Secondary:**
  - log Parkinson and Rogers–Satchell variances;
  - log squared open-to-close return;
  - log close-to-close variance (overnight gap plus session);
  - log squared overnight gap (for this one an expiry effect is not expected);
  - realized variance from 5-minute returns (2021+);
  - realized variance of the last 30 minutes;
  - realized variance in each 30-minute slot.

## 4. Treatment variables (one row per index and day)
- `own_weekly`, `own_monthly`: the index's own options have a weekly or monthly expiry today.
  - The monthly expiry is also the day index futures expire.
- `other_major`: options on another of Nifty, Bank Nifty and Sensex expire today.
- `other_minor`: options on Fin Nifty, Midcap Select or Bankex expire today.
- Own products:
  - Nifty 50 → NIFTY
  - Bank Nifty → BANKNIFTY
  - Sensex → SENSEX
  - Midcap 50 → MIDCPNIFTY. Midcap Select is a different index but covers the same kind of stocks; it is a small market and is treated as "minor".

## 5. Main specification
`lgk[i,t] = b_w own_weekly + b_m own_monthly + g_1 other_major + g_2 other_minor + FE(index × weekday) + FE(index × week) + e`
- **Index × weekday effects** remove each index's normal weekday pattern (e.g. calm Wednesdays).
- **Index × week effects** remove the general level of volatility that week.
- So an effect is identified only from days whose expiry status differs from the usual status of their weekday: the calendar changes and holiday shifts.
- **Standard errors:** clustered by calendar week (all indices share weekly shocks).
- **Primary estimates:** pooled `b_w` and `b_m`, with per-index estimates.

## 6. Robustness (all pre-specified)
1. Add common weekday × year effects. This absorbs weekday patterns that change over time for the whole market.
2. Add date fixed effects. This compares indices on the same day only, so it measures own expiry relative to the other indices' exposure.
3. Use the difference from Midcap 50 (the index least exposed to large-cap options) as the outcome.
4. Holiday-shifted expiries only. The holiday rule moves expiries for reasons unrelated to markets.
5. Driscoll–Kraay standard errors (5-day bandwidth).
6. Drop 2020 (COVID crash).
7. Start in 2017 (Bank Nifty and Midcap 50 opening prices look stale before then).
8. Add the day before and the day after expiry (displacement).
9. Run each alternative outcome from Section 3.
10. Randomization inference: re-estimate with 1,000 placebo calendars that keep every rule's dates but draw the expiry weekdays at random.

## 7. Event studies
- **Events:** the 8 major changes in Table 1 (the 3 Midcap Select changes go to the appendix).
- **Windows:** ±26 weeks, cut at the previous and next change of the same index.
- **Outputs:**
  - the weekday profile before and after each change;
  - the difference-in-differences for the weekday gaining an expiry and the one losing it;
  - a stacked estimate across events.

## 8. Mechanisms (1-minute and option data)
- **Timing:** expiry minus non-expiry log realized variance in each 30-minute slot, with week × slot effects.
- **Settlement window:** realized variance from 15:00 to 15:30.
- **Pinning:**
  - share of closes within 10% of a strike step of a strike, for strike steps 50/100 (Nifty) and 100/500 (Bank Nifty, Sensex);
  - for Nifty and Bank Nifty, the move from open to close relative to the strike with the most open interest at the previous close, compared with the day before expiry.
- **Reversal:** does the afternoon return reverse the morning return more on expiry days? This is the pattern SEBI's interim order alleged for Bank Nifty in 2023–25.
- **Option activity:** share of option contracts traded in the expiring series on expiry days, by year.

## 9. Regulation
- Interact the own-expiry indicators with "after 20 Nov 2024" and "after 3 Jul 2025".
- There are few observations after these dates, so these tests have low power. A null result is not evidence of no change.

## 10. Forecasting (link to paper 1)
- **Models:** for each index, a HAR model and HAR plus expiry indicators for the next day (known in advance). Both are fitted with paper 1's Gamma (QLIKE-matching) loss.
- **Target:** close-to-close variance (overnight gap plus Garman–Klass).
- **Test design:** walk-forward test 2018 – Jul 2026, expanding window, re-fitted every 22 trading days.
- **Scoring:** QLIKE and MSE, with Diebold–Mariano tests (Newey–West errors).

## 11. Inference and power
- **Primary tests:** pooled `b_w` and `b_m`.
- **Per-index tests:** Holm-adjusted across the four indices.
- **Power:** with a standard error of about 0.03, the smallest pooled effect we can reliably detect is about 0.085 log points. That is about 8–9% in variance and 4% in volatility. A null estimate therefore rules out large effects, not small ones.
