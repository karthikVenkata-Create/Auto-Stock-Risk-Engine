"""Static PNG charts for the GitHub README (Tableau holds the interactive versions).
Usage: python python_check/make_readme_charts.py   (after export_tableau.py)"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mt
import pandas as pd

os.makedirs("images", exist_ok=True)
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.facecolor": SURF, "figure.facecolor": SURF})


def style(ax, title, sub):
    ax.set_title(title, loc="left", color=INK, fontsize=13, fontweight="bold", pad=22)
    ax.text(0, 1.02, sub, transform=ax.transAxes, color=INK2, fontsize=9.5)
    ax.grid(axis="y", color=GRID, lw=0.8)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)


g = pd.read_csv("tableau/growth_drawdown_long.csv", parse_dates=["Date"])
full = g[g.Window == "Full 2010-2026"]
series = [("EW_BuyHold", "Buy and hold", ORANGE), ("EW_Rebalanced", "Rebalanced yearly", BLUE)]

# 1. Growth of $10k
fig, ax = plt.subplots(figsize=(9, 4.6))
for key, lab, col in series:
    s = full[full.Series == key]
    ax.plot(s.Date, s.Growth_of_10k, color=col, lw=2, label=lab)
    ax.annotate(f"{lab}\n${s.Growth_of_10k.iloc[-1]/1000:,.0f}K", (s.Date.iloc[-1], s.Growth_of_10k.iloc[-1]),
                xytext=(6, 0), textcoords="offset points", va="center", color=INK, fontsize=9)
ax.set_yscale("log")
ax.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"${v/1000:,.0f}K"))
ax.legend(frameon=False, loc="upper left", labelcolor=INK)
style(ax, "Buy-and-hold made more money...",
      "Growth of $10,000, equal-weight 5 auto stocks, Jun 2010 - Feb 2026 (log scale)")
plt.subplots_adjust(right=0.82)
fig.savefig("images/1_growth.png", dpi=160, bbox_inches="tight")
plt.close(fig)

# 2. Drawdown
fig, ax = plt.subplots(figsize=(9, 4.2))
for key, lab, col in series:
    s = full[full.Series == key]
    ax.plot(s.Date, s.Drawdown * 100, color=col, lw=1.6, label=lab)
    lo = s.loc[s.Drawdown.idxmin()]
    ax.annotate(f"{lo.Drawdown:.0%}", (lo.Date, lo.Drawdown * 100), xytext=(6, -2),
                textcoords="offset points", color=INK, fontsize=9)
ax.axhline(0, color=INK2, lw=0.8)
ax.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
ax.legend(frameon=False, loc="lower left", labelcolor=INK)
style(ax, "...but rebalancing cut the worst drop from -71% to -39%",
      "Drawdown from previous peak")
fig.savefig("images/2_drawdown.png", dpi=160, bbox_inches="tight")
plt.close(fig)

# 3. Out-of-sample comparison: return per unit of risk and max drawdown
m = pd.read_csv("tableau/strategy_metrics.csv")
m = m[m.Window == "Out-of-sample 2014-2026"].set_index("Strategy")
order = ["EW_Rebalanced", "MaxSharpe_WalkForward", "MinVar_WalkForward", "EW_BuyHold"]
names = ["Equal weight, rebalanced", "Max-Sharpe (walk-forward)", "Min-variance (walk-forward)", "Equal weight, buy & hold"]
m = m.loc[order]
fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
for ax, col, title, fmt in [(axes[0], "Return_per_Risk", "Return per unit of risk", "{:.2f}"),
                            (axes[1], "Max_DD", "Worst drawdown", "{:.0%}")]:
    vals = m[col].values if col != "Max_DD" else -m[col].values
    y = range(len(order))[::-1]
    ax.barh(list(y), vals, color=BLUE, height=0.55)
    for yy, v, raw in zip(y, vals, m[col].values):
        ax.text(v, yy, "  " + fmt.format(raw), va="center", color=INK, fontsize=9)
    ax.set_title(title, loc="left", color=INK, fontsize=10.5)
    ax.set_xticks([])
    for s in ["top", "right", "bottom"]:
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)
axes[0].set_yticks(list(range(len(order))[::-1]))
axes[0].set_yticklabels(names, color=INK)
fig.suptitle("Out of sample (2014-2026), optimization did not beat plain equal weight",
             x=0.01, ha="left", color=INK, fontsize=13, fontweight="bold")
fig.tight_layout()
fig.savefig("images/3_out_of_sample.png", dpi=160, bbox_inches="tight")
plt.close(fig)
print("saved images/")
