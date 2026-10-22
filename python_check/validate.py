"""
Independent Python check of the R engine (R/portfolio_engine.R).

Same data, same math, same constraints. If both scripts agree, the numbers
in the README are reproducible in two languages.

Usage:  python python_check/validate.py
Reads:  data/prices_adjusted.csv
Writes: python_check/python_results.csv  (headline numbers to compare with R)
"""
import numpy as np
import pandas as pd
import quadprog

TICKERS = ["TSLA", "TM", "HMC", "BMWKY", "GELHY"]
LOOKBACK = 756      # 3 years of trading days for walk-forward estimation
MAX_W = 0.40        # no single stock above 40% in optimized portfolios
OOS_START = 2014    # first out-of-sample year (needs 3 years of history)


def load_prices(path="data/prices_adjusted.csv"):
    p = pd.read_csv(path, parse_dates=["Date"]).set_index("Date")[TICKERS]
    return p.dropna()


def simulate(rets, weight_fn, rebalance=True):
    """Daily drift between rebalances; rebalance on first trading day of each year.
    weight_fn(date) -> target weights (np.array). Returns (daily returns, weights log, turnover log)."""
    out, wlog, tlog = [], [], []
    hold = None
    prev = None
    for dt, row in rets.iterrows():
        if hold is None or (rebalance and dt.year != prev.year):
            target = weight_fn(dt)
            if hold is None:
                turnover = np.nan
                value = 1.0
            else:
                value = hold.sum()
                turnover = 0.5 * np.abs(target - hold / value).sum()
            hold = target * value
            wlog.append((dt.year, *target))
            tlog.append((dt.year, turnover))
        start = hold.sum()
        hold = hold * (1 + row.values)
        out.append(hold.sum() / start - 1)
        prev = dt
    return pd.Series(out, index=rets.index), wlog, tlog


def min_var(cov, cap=MAX_W):
    """Long-only, fully invested, each weight <= cap. Same QP and solver (quadprog) as the R script."""
    n = len(cov)
    D = 2 * cov + np.eye(n) * 1e-10
    A = np.column_stack([np.ones(n), np.eye(n), -np.eye(n)])
    b = np.concatenate([[1.0], np.zeros(n), -cap * np.ones(n)])
    w = np.clip(quadprog.solve_qp(D, np.zeros(n), A, b, meq=1)[0], 0, None)
    return w / w.sum()


def max_sharpe(mu, cov, cap=MAX_W):
    """Tangency portfolio (rf = 0), long-only with a weight cap.
    Convex trick: minimise y'Sigma y s.t. mu'y = 1, y >= 0, y_i <= cap * sum(y);
    then w = y / sum(y). Falls back to min-variance if infeasible or no asset has mu > 0."""
    n = len(mu)
    if (mu <= 0).all():
        return min_var(cov, cap)
    D = 2 * cov + np.eye(n) * 1e-10
    A = np.column_stack([mu, np.eye(n), cap * np.ones((n, n)) - np.eye(n)])
    b = np.concatenate([[1.0], np.zeros(2 * n)])
    try:
        y = quadprog.solve_qp(D, np.zeros(n), A, b, meq=1)[0]
    except ValueError:
        return min_var(cov, cap)
    y = np.clip(y, 0, None)
    return y / y.sum()


def stats(r):
    yrs = len(r) / 252
    growth = (1 + r).cumprod()
    cagr = growth.iloc[-1] ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(252)
    dd = (growth / growth.cummax() - 1).min()
    yearly = (1 + r).groupby(r.index.year).prod() - 1
    return {"CAGR": cagr, "Vol": vol, "Return_per_Risk": cagr / vol, "Max_DD": dd,
            "Calmar": cagr / abs(dd), "Worst_Year": yearly.min(), "Best_Year": yearly.max()}


def main():
    prices = load_prices()
    rets = prices.pct_change().dropna()
    n = len(TICKERS)
    ew = np.repeat(1 / n, n)

    rows = []
    # Full period (Jun 2010 - Feb 2026), CAGR on calendar time to match the v2 workbook
    span = (prices.index[-1] - prices.index[0]).days / 365.25
    for t in TICKERS:
        cagr = (prices[t].iloc[-1] / prices[t].iloc[0]) ** (1 / span) - 1
        rows.append(("full", t, "CAGR", cagr))

    for name, cols, reb in [("EW_Rebalanced", TICKERS, True), ("EW_BuyHold", TICKERS, False),
                            ("EW_ExTSLA_Rebalanced", TICKERS[1:], True)]:
        k = len(cols)
        r, _, _ = simulate(rets[cols], lambda d, k=k: np.repeat(1 / k, k), reb)
        cagr = (1 + r).prod() ** (1 / span) - 1
        st = stats(r)
        rows += [("full", name, "CAGR", cagr), ("full", name, "Max_DD", st["Max_DD"]),
                 ("full", name, "Vol", st["Vol"])]

    # Walk-forward window
    oos = rets[rets.index.year >= OOS_START]

    def trailing(dt):
        hist = rets[rets.index < dt].tail(LOOKBACK)
        return hist.mean().values * 252, hist.cov().values * 252

    strategies = {
        "EW_Rebalanced": (lambda d: ew, True),
        "EW_BuyHold": (lambda d: ew, False),
        "MinVar_WalkForward": (lambda d: min_var(trailing(d)[1]), True),
        "MaxSharpe_WalkForward": (lambda d: max_sharpe(*trailing(d)), True),
    }
    for name, (fn, reb) in strategies.items():
        r, wlog, tlog = simulate(oos, fn, reb)
        for k, v in stats(r).items():
            rows.append(("oos_2014", name, k, v))
        to = [t for _, t in tlog if not np.isnan(t)]
        rows.append(("oos_2014", name, "Avg_Turnover", np.mean(to) if to else 0.0))

    out = pd.DataFrame(rows, columns=["Window", "Series", "Metric", "Value"])
    out.to_csv("python_check/python_results.csv", index=False)
    print(out.pivot_table(index=["Window", "Series"], columns="Metric", values="Value").round(4).to_string())


if __name__ == "__main__":
    main()
