"""Figures for the paper and notebooks (matplotlib, one consistent style)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import expiries as ex  # noqa: E402

# validated categorical palette (light mode), fixed order
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df"
INDEX_COLOR = {"nifty50": BLUE, "banknifty": ORANGE, "sensex": AQUA, "midcap50": YELLOW}
LABEL = {"nifty50": "Nifty 50", "banknifty": "Bank Nifty", "sensex": "Sensex", "midcap50": "Midcap 50",
         "pooled": "All indices"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.titlesize": 9.5, "axes.titleweight": "bold",
    "axes.labelsize": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False, "figure.dpi": 150,
    "savefig.bbox": "tight", "savefig.dpi": 200, "lines.linewidth": 2,
})


def save(fig, path_stem: str):
    fig.savefig(f"{path_stem}.png")
    fig.savefig(f"{path_stem}.pdf")
    plt.close(fig)


def pct(logdiff) -> np.ndarray:
    """A difference in log variance as a % change in variance."""
    return 100 * (np.exp(np.asarray(logdiff, dtype=float)) - 1)


def coef_panel(ax, table: pd.DataFrame, rows, labels, title: str, colors=None):
    """Horizontal coefficient plot with 95% intervals, in % change of variance."""
    y = np.arange(len(rows))[::-1]
    for i, (key, lab) in enumerate(zip(rows, labels)):
        r = table.loc[key]
        c = (colors or [BLUE] * len(rows))[i]
        ax.plot(pct([r["lo"], r["hi"]]), [y[i]] * 2, color=c, lw=2, solid_capstyle="round")
        ax.plot(pct(r["coef"]), y[i], "o", color=c, ms=6, mec="white", mew=1.2)
    ax.axvline(0, color=INK2, lw=0.8)
    ax.set_yticks(y, labels)
    ax.set_title(title, loc="left")
    ax.grid(axis="y", visible=False)


def fig_main(main_daily: pd.DataFrame, main_last: pd.DataFrame, path_stem: str):
    """Whole session vs last half hour: expiry effects by index (weekly and monthly expiries)."""
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.6), sharey=True)
    order = ["pooled", "nifty50", "banknifty", "sensex"]
    for ax, tab, title in [(axes[0], main_daily, "A. Whole session (daily range, 2014–2026)"),
                           (axes[1], main_last, "B. Settlement window, 15:00–15:30 (2021–2026)")]:
        y0 = np.arange(len(order))[::-1]
        for j, (term, col, lab) in enumerate([("own_weekly", BLUE, "weekly expiry"),
                                              ("own_monthly", ORANGE, "monthly expiry")]):
            for i, s in enumerate(order):
                r = tab[(tab["sample"] == s) & (tab["term"] == term)]
                if r.empty:
                    continue
                r = r.iloc[0]
                yy = y0[i] + (0.14 if j == 0 else -0.14)
                ax.plot(pct([r["lo"], r["hi"]]), [yy] * 2, color=col, lw=2, solid_capstyle="round")
                ax.plot(pct(r["coef"]), yy, "o", color=col, ms=5.5, mec="white", mew=1, label=lab if i == 0 else None)
        ax.axvline(0, color=INK2, lw=0.8)
        ax.set_yticks(y0, [LABEL[s] for s in order])
        ax.grid(axis="y", visible=False)
        ax.set_title(title, loc="left")
        ax.set_xlabel("Change in variance on expiry days (%)")
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=2, fontsize=8, bbox_to_anchor=(0.5, -0.04))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, path_stem)


def fig_moving(profiles: dict, path_stem: str, ylabel: str):
    """Small multiples: weekday profile before and after each calendar change."""
    names = list(profiles)
    n = len(names)
    cols = 3
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(8.4, 2.45 * rows), sharey=True)
    axes = np.atleast_1d(axes).ravel()
    x = np.arange(5)
    for ax, name in zip(axes, names):
        p = profiles[name]
        ev = p["event"]
        ax.bar(x - 0.19, pct(p["before"]["mean"].reindex(ex.WEEKDAY_NAMES)), width=0.36, color=MUTED,
               label="before", edgecolor="white", linewidth=0.8)
        ax.bar(x + 0.19, pct(p["after"]["mean"].reindex(ex.WEEKDAY_NAMES)), width=0.36, color=BLUE,
               label="after", edgecolor="white", linewidth=0.8)
        ax.axhline(0, color=INK2, lw=0.8)
        labels = []
        for i, d in enumerate(ex.WEEKDAY_NAMES):
            tag = d
            if i in ev.gain:
                tag += "\n(new)"
            elif i in ev.lose:
                tag += "\n(old)"
            labels.append(tag)
        ax.set_xticks(x, labels, fontsize=8)
        for i in ev.gain:
            ax.get_xticklabels()[i].set_color(BLUE)
            ax.get_xticklabels()[i].set_fontweight("bold")
        ax.set_title(ev.name.replace(" (", "\n("), loc="left", fontsize=8.5)
        ax.grid(axis="x", visible=False)
    for ax in axes[len(names):]:
        ax.axis("off")
    for ax in axes[::cols]:
        ax.set_ylabel(ylabel)
    axes[0].legend(loc="upper left", fontsize=7.5)
    fig.tight_layout()
    save(fig, path_stem)


def fig_intraday(slot_tab: pd.DataFrame, path_stem: str):
    """Expiry effect in each slot of the session."""
    fig, ax = plt.subplots(figsize=(7.8, 3.4))
    starts = sorted(slot_tab["start"].unique())
    x = np.arange(len(starts))
    for term, col, lab, dx in [("own_weekly", BLUE, "own weekly expiry", -0.12),
                               ("own_monthly", ORANGE, "own monthly expiry", 0.0),
                               ("other_major", AQUA, "another large index expires", 0.12)]:
        t = slot_tab[slot_tab["term"] == term].set_index("start").reindex(starts)
        ax.vlines(x + dx, pct(t["lo"]), pct(t["hi"]), color=col, lw=1.3)
        ax.plot(x + dx, pct(t["coef"]), "o-", color=col, ms=3.8, lw=1.1, mec="white", mew=0.7, label=lab)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.axvspan(len(starts) - 2.5, len(starts) - 0.5, color=YELLOW, alpha=0.12, lw=0)
    ax.text(len(starts) - 1.5, ax.get_ylim()[1] * 0.92, "settlement\nwindow", ha="center", va="top", fontsize=7.5, color=INK2)
    ax.set_xticks(x[::2], starts[::2], rotation=0, fontsize=7.5)
    ax.set_xlabel("Start of 15-minute slot (India time)")
    ax.set_ylabel("Change in variance (%)")
    ax.legend(loc="upper left", fontsize=7.5)
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    save(fig, path_stem)


def fig_event_time(et_last: pd.DataFrame, et_day: pd.DataFrame, bin_weeks: int, path_stem: str):
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.1), sharex=True)
    for ax, et, title in [(axes[0], et_day, "A. Whole session"), (axes[1], et_last, "B. Settlement window, 15:00–15:30")]:
        x = et["bin"].to_numpy() * bin_weeks + bin_weeks / 2
        ax.vlines(x, pct(et["lo"]), pct(et["hi"]), color=BLUE, lw=1.8)
        ax.plot(x, pct(et["coef"]), "o", color=BLUE, ms=5, mec="white", mew=1)
        ax.axhline(0, color=INK2, lw=0.8)
        ax.axvline(0, color=ORANGE, lw=1.2, ls="--")
        ax.set_title(title, loc="left")
        ax.set_xlabel("Weeks since the expiry day changed")
    axes[0].set_ylabel("New minus old expiry weekday (%)")
    fig.tight_layout()
    save(fig, path_stem)


def fig_periods(per: pd.DataFrame, path_stem: str):
    """Settlement-window expiry effect by period, per index."""
    fig, ax = plt.subplots(figsize=(7.6, 3.2))
    periods = list(dict.fromkeys(per["period"]))
    x = np.arange(len(periods))
    for k, (idx, col) in enumerate([("nifty50", BLUE), ("banknifty", ORANGE), ("sensex", AQUA)]):
        t = per[(per["sample"] == idx)].set_index("period").reindex(periods)
        dx = (k - 1) * 0.16
        ax.vlines(x + dx, pct(t["lo"]), pct(t["hi"]), color=col, lw=1.8)
        ax.plot(x + dx, pct(t["coef"]), "o", color=col, ms=5, mec="white", mew=1, label=LABEL[idx])
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_xticks(x, [p.replace(" (minute data: 2021-23)", "").replace("2019-23", "2021–23").replace(" to ", " to\n")
                      for p in periods], fontsize=7.5)
    ax.set_ylabel("Settlement-window variance on\nown expiry days (% change)")
    ax.legend(loc="upper left", fontsize=7.5, ncol=3)
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    save(fig, path_stem)


def fig_activity(act: pd.DataFrame, path_stem: str):
    """Share of all option contracts of a year traded in the expiring series on expiry days."""
    fig, ax = plt.subplots(figsize=(6.4, 2.9))
    for idx, col in [("nifty50", BLUE), ("banknifty", ORANGE)]:
        a = act[act["index"] == idx]
        ax.plot(a["year"], 100 * a["share_0dte_of_year"], "o-", color=col, ms=4.5, lw=1.8, mec="white", mew=0.8, label=LABEL[idx])
    ax.set_ylabel("Share of the year's option\ncontracts traded on expiry day\nin the expiring series (%)")
    ax.set_ylim(0, None)
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    save(fig, path_stem)


def fig_placebo(placebo: pd.Series, actual: float, path_stem: str, label: str):
    fig, ax = plt.subplots(figsize=(5.6, 2.8))
    ax.hist(pct(placebo), bins=40, color=MUTED, edgecolor="white", linewidth=0.5)
    ax.axvline(pct(actual), color=ORANGE, lw=2)
    ax.text(pct(actual), ax.get_ylim()[1] * 0.95, " real calendar", color=INK, fontsize=8, va="top")
    ax.set_xlabel(f"{label}: change in variance (%)")
    ax.set_ylabel("Placebo calendars")
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    save(fig, path_stem)
