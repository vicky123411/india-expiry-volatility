# Study guide: "Expiry Moves the Close, Not the Day"

This guide explains the whole project in easy language, step by step, so you can understand it, present it and answer questions about it. Read it in order. Each section is short.

---

## 1. The story in 6 points
- In India, huge numbers of people trade **index options**. These are bets on where an index like the Nifty 50 will end up.
- Every option has an **expiry day**. On that day it is settled using the index's **closing value**.
- Many people (and SEBI) believe **expiry days make the market wild**.
- From 2016 to 2025 the exchanges kept **changing which weekday** options expire on, eleven times. That gives us a free experiment: *if expiry causes wildness, the wild day should move when the expiry day moves.*
- **Finding 1:** the trading day as a whole is **not much** wilder on expiry days (close to zero; event windows give about +15%).
- **Finding 2:** the **last 30 minutes (15:00–15:30)** are about **50–70% wilder** on expiry days. This wild half hour **moves with the expiry day** when the calendar changes. Until August 2026, that half hour set the price used to settle the options.

**One-line summary:** *expiry moves the close, not the day.*

---

## 2. Words you must know
| Word | Simple meaning |
|---|---|
| **Index** | One number that tracks a group of big companies (Nifty 50 = 50 companies on NSE; Sensex = 30 on BSE; Bank Nifty = bank shares). |
| **Option** | A contract that pays off depending on where the index ends up. A *call* gains if the index goes up; a *put* gains if it goes down. |
| **Strike** | The index level written in the option (e.g. Nifty 25,000). |
| **Expiry day** | The last day of the option. At the close it is settled and disappears. |
| **Weekly / monthly expiry** | Weekly options expire every week on one weekday; the monthly one on the last such weekday of the month. |
| **0DTE** | "Zero days to expiry": trading an option on the day it expires. In 2024, 59% of all Nifty option contracts traded were 0DTE. |
| **Settlement price** | The index value used to pay out expiring options. Until 3 Aug 2026 it was the **average price from 15:00 to 15:30**. |
| **Volatility** | How much prices jump around. **Variance** is volatility squared. |
| **Realized variance** | Add up the squares of many small price moves (every 1 or 5 minutes) in a period. Bigger = wilder. |
| **Garman–Klass** | A way to estimate a day's variance from just open, high, low and close (used when we only have daily data). |
| **Natural experiment** | Something outside our control changes for one group but not another, so we can compare, almost like a lab experiment. |
| **Difference-in-differences (DiD)** | Compare the change in the group that got the change with the change in a group that didn't. |
| **Fixed effects** | A statistical way of saying "compare like with like" (same index, same week, same weekday). |
| **Clustered standard errors** | A way to get honest error bars when days in the same week are related. |
| **Placebo test** | Pretend the expiry happened on a random day and redo the test. If that also gives a big effect, our result is not trustworthy. |
| **p-value** | Roughly: how likely is a result this big if there were really no effect? Below 0.05 is usually called "significant". |
| **Pinning** | The index sticking to a round strike price at expiry. |
| **HAR model** | The classic volatility forecasting model from paper 1. |

**Reading the numbers:** a coefficient of 0.10 (in "log variance") ≈ 10% more variance ≈ 5% more volatility. A coefficient of 0.425 ≈ 53% more variance.

---

## 3. Why this topic is good
- **Very topical.** SEBI cut weekly expiries in Nov 2024. SEBI's July 2025 interim order against Jane Street was about expiry-day trading. The whole world debates 0DTE options.
- **Causal, not just correlation.** Simple studies compare expiry days with other days, but expiry always falls on the same weekday, and weekdays differ anyway (Mondays are often jumpier). The calendar changes let us separate "expiry" from "weekday".
- **New.** The one journal paper on this (Chhimwal, Pandey & Pandey 2025, *Review of Derivatives Research*) uses one change. We use all eleven, including the 2024–25 changes nobody has studied.
- **Builds on paper 1.** Same volatility measure, same HAR forecasting model.

---

## 4. The data (what and why)
- **Daily prices 2014 – Jul 2026** for Nifty 50, Bank Nifty, Sensex and Nifty Midcap 50 (Yahoo Finance).
  - Midcap 50 is the "least affected" index: almost nobody trades options on mid-caps.
- **1-minute prices** for Nifty 50 and Bank Nifty (2021–2026) and Sensex (2022–2026). We need these to see *when* in the day things happen.
- **NSE option files (bhavcopy), 2014–2026.** These show which contracts traded and how much open interest each strike had. We use them to check our calendar, to measure 0DTE trading, and to test pinning.
- **Why the sample stops on 31 Jul 2026:** on 3 Aug 2026 NSE started a **closing auction**, which changed how the closing price is set. Mixing the two systems would muddy the results.

---

## 5. The expiry calendar (the heart of the project)
- We wrote down every rule for six option products (Table 1 in the paper). Examples:
  - **Bank Nifty:** weekly Thursday (2016) → Wednesday (Sep 2023) → weekly removed (Nov 2024).
  - **Sensex:** Friday (May 2023) → Tuesday (Jan 2025) → Thursday (Sep 2025).
  - **Nifty:** weekly Thursday (Feb 2019) → Tuesday (Sep 2025).
- **Holiday rule:** if expiry day is a holiday, expiry moves to the day before.
- **Checked against reality:** the calendar matches NSE's own files on **all 932** Nifty/Bank Nifty expiry days (0 mistakes), and all 148 Sensex expiry dates in another dataset.
  - Two small surprises we found and fixed:
    - NSE sometimes keeps the old (holiday) date as the contract's label.
    - The last Friday Sensex contract (3 Jan 2025) still expired after the switch to Tuesday.

---

## 6. The method, step by step
1. **Measure volatility for every index on every day.** Whole day, and the last 30 minutes.
2. **Mark every day:** does this index's own option expire (weekly or monthly)? Does another big index's option expire?
3. **Compare fairly:**
   - Same index, **same week** (so a crisis week is compared with itself).
   - Against that index's **usual weekday level** (so a jumpy Monday isn't blamed on expiry).
   - With both of these, the only thing that can show an effect is a day whose expiry status is *unusual for its weekday*. That only happens because the calendar changed (or a holiday moved the expiry). That is the natural experiment.
4. **Look at each calendar change separately** (event study): 6 months before vs 6 months after, for the weekday that gained the expiry and the one that lost it.
5. **Try to break the result** (robustness):
   - Add weekday × year effects.
   - Compare indices on the same day.
   - Use other error bars.
   - Control for holidays.
   - Run 1,000 **placebo calendars** with random weekdays.

---

## 7. The results, with numbers
| What | Result | Meaning |
|---|---|---|
| Whole day, weekly expiry | −2.4% (range −8% to +4%) | No effect |
| Whole day, monthly expiry | +5.7% (range −4% to +16%) | No clear effect |
| Whole day, weekday *gaining* an expiry (event windows) | about +15% (uncertain) | Small; can't be ruled out |
| **Last 30 min, weekly expiry** | **+53%** | Big effect |
| **Last 30 min, monthly expiry** | **+67%** | Big effect |
| Last 30 min, Sensex weekly | +146% | Biggest |
| Last 30 min, Bank Nifty weekly | +34% | Clear |
| When a weekday **gains** an expiry | its last 30 min **+65%** (higher in all 5 cases) | The wildness moves in |
| When a weekday **loses** an expiry | its last 30 min **−31%** (lower in 4 of 5 cases) | ... and mostly moves out |
| Placebo calendars (1,000) | none as big as the real one | Not luck (p = 0.001) |

**Extra findings**
- **Timing:** the effect is near zero at 9:15, small during the day, and peaks at 15:00–15:15.
- **Pinning:** almost none. Only Bank Nifty closes slightly more often near 100-point strikes. On expiry days Nifty, if anything, moves *away* from the strike with the most open interest.
- **Reversal:** for Bank Nifty in 2023–25 (the period in SEBI's allegations), the last half hour tends to *undo* the day's move on expiry days. This is only suggestive, because it is one test among many.
- **Over time:** the last-30-minute effect stayed large: 0.19 (2021–23), 0.60 (2024), 0.49 (Nov 2024 – Jul 2025), 0.92 (after Jul 2025).
  - It did not go away after SEBI's Nov 2024 rules or the Jul 2025 order.
  - These period numbers are descriptive: the set of indices with weekly expiries also changed.
- **Total weekly volatility:** no reliable evidence that weekly options raise it.
- **Forecasting:** adding the calendar to the HAR model makes daily forecasts slightly *worse* (≈1–2%). Makes sense: the effect sits in 30 minutes, not in the whole day.

---

## 8. Why it matters (policy message)
- SEBI's 2024 limits on **how often** options expire were mainly about protecting small traders. If the worry is **market stability**, our data say the whole day is not the problem.
- The problem we **do** see is in **how the settlement price is set**: the last half hour.
- So tools like **closing auctions** (NSE started one on 3 Aug 2026), longer averaging windows, or closer monitoring of the last minutes are better targeted.
- **Early look at the closing auction (only 2 months of hourly data):** no sign yet that it removed the effect. Too early to judge, and the hourly bar may not show the auction price itself.

---

## 9. Limitations (say these yourself before someone else does)
- Nifty, Bank Nifty and Sensex share many stocks, so "own" and "spillover" effects overlap.
- Minute data only start in 2021. The 2025 changes have only 6–10 months of data after them.
- Volatility in the last half hour could be "noise" (price pressure that reverses) or information. Our tests only partly tell them apart.
- We cannot say *who* causes the effect, or prove manipulation by anyone.
- The calendars of the three small products (Fin Nifty, Midcap Select, Bankex) are from rules, not checked against files. They are only controls.

---

## 10. Questions you may be asked, and answers
1. **"Why not just compare expiry days with other days?"**
   - Because expiry always fell on the same weekday, and weekdays differ anyway.
   - The calendar changes let us separate "expiry" from "weekday".
2. **"How do you know the calendar changes weren't caused by volatility?"**
   - They were caused by exchange competition, SEBI rules and a SEBI-directed swap.
   - None was a reaction to a particular weekday's volatility.
   - Also, the event-time chart is flat *before* each change and jumps right *after* it.
3. **"Couldn't something else have happened on those weekdays at the same time?"**
   - We add weekday × year effects and even same-day comparisons across indices. The result survives.
   - Placebo calendars with random weekdays never produce such a big effect.
4. **"Why is the last half hour special?"**
   - Until Aug 2026 its average price *was* the settlement price.
   - Traders with big option positions care about that price, and hedgers adjust positions there.
5. **"Is this manipulation?"**
   - We can't say. We measure volatility, not intent.
   - The Bank Nifty reversal pattern in 2023–25 fits the timing of SEBI's allegations, but it is one test among many.
6. **"Your daily result is zero. Isn't that a failure?"**
   - No. A precise zero is a finding. It rules out large whole-day effects, and it tells us *where* the effect is (the close).
7. **"What is the Holm adjustment?"**
   - When you test four indices, one may look significant by luck. Holm makes the p-values stricter to account for that.
8. **"Why log variance?"**
   - Variance is very skewed (crash days are huge). Logs make it well-behaved, and coefficients read as % changes.
9. **"How does this connect to your first paper?"**
   - Same volatility measure and HAR model. Paper 1 asked how to *forecast* volatility. Paper 2 asks what *causes* a specific part of it.
   - Adding the expiry calendar doesn't help daily forecasts, which fits the "last half hour" finding.
10. **"What would you do next?"**
    - Study the closing auction properly once a year of data exists.
    - Use stock-level data to see which stocks drive the closing-window moves.
    - Use trader-level data (if SEBI releases it) to see who trades in that window.

---

## 11. How to run it (copy–paste)
```bash
git clone https://github.com/vicky123411/india-options-expiry-effects.git
cd india-options-expiry-effects
pip install -r requirements.txt
pytest -q                       # checks (few seconds)
python scripts/run_all.py       # everything (~10 minutes, downloads data first time)
jupyter lab notebooks/          # open the 3 notebooks and Run All
```
- **Paper:** upload the `paper/` folder to Overleaf (it includes `figures/`, `tables/` and `references.bib`) and compile with pdfLaTeX.

---

## 12. Before you submit
- **Read the paper once fully** and run the notebooks yourself, so you can explain every table.
- **Fill in the author line:** full name and affiliation (marked `TODO` in `paper/main.tex`).
- **AI-use policy:** many journals require you to state whether AI tools helped. A draft "Use of AI tools" sentence is in the paper's Declarations — adjust it to the journal's rules.
- **Suitable venues to consider:**
  - *Finance Research Letters* (short version);
  - *Journal of Futures Markets*;
  - *Review of Derivatives Research*;
  - *Emerging Markets Review*;
  - *Journal of Risk and Financial Management*;
  - conferences such as the IEEE CIFEr or ACM ICAIF workshops.
