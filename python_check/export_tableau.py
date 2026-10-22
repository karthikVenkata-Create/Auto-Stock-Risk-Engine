"""
Python mirror of the export section of R/portfolio_engine.R (writes to python_check/mirror/).
Writes the same files as the R tableau/ export with the same columns, so the dashboards
can be built and the R output can be diffed against it.

Usage: python python_check/export_tableau.py   (from the project root)
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
import quadprog
from validate import (TICKERS, LOOKBACK, OOS_START, load_prices, simulate,
                      min_var, max_sharpe, stats)

os.makedirs("python_check/mirror", exist_ok=True)

prices = load_prices()
rets = prices.pct_change().dropna()
vol_raw = pd.read_csv("data/volume.csv", parse_dates=["Date"]).set_index("Date")[TICKERS]
span = (prices.index[-1] - prices.index[0]).days / 365.25
FULL, OOS = "Full 2010-2026", "Out-of-sample 2014-2026"


def yearly(r):
    return (1 + r).groupby(r.index.year).prod() - 1


def growth_dd(r, series, window):
    g = 10000 * (1 + r).cumprod()
    return pd.DataFrame({"Window": window, "Series": series, "Date": r.index.strftime("%Y-%m-%d"),
                         "Growth_of_10k": g.values, "Drawdown": (g / g.cummax() - 1).values})


# Stocks
rows = []
for t in TICKERS:
    p, r = prices[t], rets[t]
    cagr = (p.iloc[-1] / p.iloc[0]) ** (1 / span) - 1
    vol = r.std() * np.sqrt(252)
    g = (1 + r).cumprod()
    rows.append({"Ticker": t, "CAGR": cagr, "Vol": vol, "Return_per_Risk": cagr / vol,
                 "Max_DD": (g / g.cummax() - 1).min(), "Down_Years": int((yearly(r) < 0).sum()),
                 "Ten_K_Became": 10000 * p.iloc[-1] / p.iloc[0],
                 "Zero_Volume_Days_Pct": (vol_raw[t] == 0).mean(),
                 "Zero_Return_Days_Pct": (r == 0).mean()})
pd.DataFrame(rows).to_csv("python_check/mirror/stock_metrics.csv", index=False)

c = rets.corr()
pd.DataFrame([{"Ticker_A": a, "Ticker_B": b, "Correlation": c.loc[a, b]}
              for b in TICKERS for a in TICKERS]).to_csv("python_check/mirror/correlation_long.csv", index=False)

# Strategies
n = len(TICKERS)
ew = lambda k: (lambda d: np.repeat(1 / k, k))
full_runs = {
    "EW_Rebalanced": simulate(rets, ew(5), True),
    "EW_BuyHold": simulate(rets, ew(5), False),
    "EW_ExTSLA_Rebalanced": simulate(rets[TICKERS[1:]], ew(4), True),
}


def trailing(d):
    h = rets[rets.index < d].tail(LOOKBACK)
    return h.mean().values * 252, h.cov().values * 252


oos = rets[rets.index.year >= OOS_START]
oos_runs = {
    "EW_Rebalanced": simulate(oos, ew(5), True),
    "EW_BuyHold": simulate(oos, ew(5), False),
    "MinVar_WalkForward": simulate(oos, lambda d: min_var(trailing(d)[1]), True),
    "MaxSharpe_WalkForward": simulate(oos, lambda d: max_sharpe(*trailing(d)), True),
}

mrows = []
for nm, (r, _, _) in full_runs.items():
    s = stats(r)
    s["CAGR"] = (1 + r).prod() ** (1 / span) - 1
    s["Return_per_Risk"] = s["CAGR"] / s["Vol"]
    s["Calmar"] = s["CAGR"] / abs(s["Max_DD"])
    mrows.append({"Window": FULL, "Strategy": nm, **s, "Avg_Turnover": np.nan})
for nm, (r, _, tl) in oos_runs.items():
    to = [t for _, t in tl if not np.isnan(t)]
    mrows.append({"Window": OOS, "Strategy": nm, **stats(r), "Avg_Turnover": np.mean(to) if to else 0.0})
metrics = pd.DataFrame(mrows)
metrics.to_csv("python_check/mirror/strategy_metrics.csv", index=False)

# Growth & drawdown
parts = [growth_dd(r, nm, FULL) for nm, (r, _, _) in full_runs.items()]
parts += [growth_dd(r, nm, OOS) for nm, (r, _, _) in oos_runs.items()]
parts += [growth_dd(rets[t], t, FULL) for t in TICKERS]
pd.concat(parts).to_csv("python_check/mirror/growth_drawdown_long.csv", index=False)

# Walk-forward weights
wrows = []
for nm in ["MinVar_WalkForward", "MaxSharpe_WalkForward"]:
    for rec in oos_runs[nm][1]:
        for t, w in zip(TICKERS, rec[1:]):
            wrows.append({"Strategy": nm, "Year": rec[0], "Ticker": t, "Weight": w})
pd.DataFrame(wrows).to_csv("python_check/mirror/walkforward_weights.csv", index=False)

# Calendar returns
crows = []
for t in TICKERS:
    for y, v in yearly(rets[t]).items():
        crows.append({"Series": t, "Year": y, "Return": v})
for nm, (r, _, _) in full_runs.items():
    for y, v in yearly(r).items():
        crows.append({"Series": nm, "Year": y, "Return": v})
pd.DataFrame(crows).to_csv("python_check/mirror/calendar_returns.csv", index=False)

# Rolling 1-year risk
def long(s, series, metric):
    s = s.dropna()
    return pd.DataFrame({"Date": s.index.strftime("%Y-%m-%d"), "Series": series,
                         "Metric": metric, "Value": s.values})

rv = rets.rolling(252).std() * np.sqrt(252)
parts = [long(rv[t], t, "Rolling_Vol_1Y") for t in TICKERS]
parts.append(long(full_runs["EW_Rebalanced"][0].rolling(252).std() * np.sqrt(252),
                  "EW_Rebalanced", "Rolling_Vol_1Y"))
parts.append(long(rets["TM"].rolling(252).corr(rets["HMC"]), "TM vs HMC", "Rolling_Corr_1Y"))
tsla = sum(rets["TSLA"].rolling(252).corr(rets[t]) for t in TICKERS[1:]) / 4
parts.append(long(tsla, "TSLA vs others (avg)", "Rolling_Corr_1Y"))
pd.concat(parts).to_csv("python_check/mirror/rolling_risk.csv", index=False)

# Efficient frontier (full sample, long only, no cap; arithmetic mean returns)
mu, cov = rets.mean().values * 252, rets.cov().values * 252
frows = []
for tg in np.linspace(mu.min(), mu.max(), 40):
    A = np.column_stack([np.ones(n), mu, np.eye(n)])
    bb = np.concatenate([[1.0, tg], np.zeros(n)])
    try:
        wf = quadprog.solve_qp(2 * cov + np.eye(n) * 1e-10, np.zeros(n), A, bb, meq=2)[0]
    except ValueError:
        continue
    frows.append({"Point": "Frontier", "Label": "", "Exp_Return": tg,
                  "Vol": float(np.sqrt(wf @ cov @ wf))})
for i, t in enumerate(TICKERS):
    frows.append({"Point": "Stock", "Label": t, "Exp_Return": mu[i], "Vol": float(np.sqrt(cov[i, i]))})
w = np.repeat(0.2, n)
frows.append({"Point": "Portfolio", "Label": "Equal weight", "Exp_Return": mu @ w,
              "Vol": float(np.sqrt(w @ cov @ w))})
pd.DataFrame(frows).to_csv("python_check/mirror/efficient_frontier.csv", index=False)

print(metrics.round(4).to_string(index=False))
print("hindsight max-Sharpe:", dict(zip(TICKERS, max_sharpe(mu, cov).round(2))))
