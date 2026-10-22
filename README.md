# Multi-Stock Risk & Return Engine: 5 Auto Stocks (R + Tableau)

**Karthik Bommisetty** | UIC MBA (Finance) + MS Business Analytics

This started as an Excel project in March 2026 (pivots, a dashboard, buy/sell calls). I rebuilt it in October around compound growth and drawdowns, and this version moves the whole thing into R so I could answer a harder question: if you actually tried to optimize a portfolio of these stocks, without knowing the future, would it beat just splitting the money five ways?

Stocks: Tesla (TSLA), Toyota (TM), Honda (HMC), BMW (BMWKY), Geely (GELHY). Window: Tesla's IPO on 29 Jun 2010 to 13 Feb 2026, 3,932 trading days, dividend- and split-adjusted daily prices.

## What I found

**1. Tesla was the whole story.** It compounded at 42.8% a year ($10K became $2.6M) with a 74% max drawdown. Toyota was the steadiest (11.3% a year, 23% vol), Honda the weakest (2.8% a year, 6 down calendar years). Tesla moved with the other four at a correlation of only about 0.25, while Toyota and Honda moved together at 0.73.

**2. Rebalancing didn't make more money, it made a smoother ride.** An equal-weight portfolio reset every January returned 23.9% a year. Leaving it alone (buy-and-hold) returned 29.4%, because Tesla's weight was allowed to grow. But buy-and-hold fell 71% peak to trough by early 2023, versus 39% for the rebalanced version, and its volatility was 43% versus 27%. Per unit of risk, rebalancing won (0.87 vs 0.68). Without Tesla, the rebalanced portfolio returned only 13.0%.

**3. Optimization did not beat equal weight out of sample.** Every January from 2014 on, I estimated means and covariances from only the previous three years, solved for the minimum-variance and maximum-Sharpe portfolios (long only, max 40% in one stock), and held them for the year. Results for 2014 to Feb 2026:

| Strategy | CAGR | Volatility | Return / risk | Max drawdown | Avg yearly turnover |
|---|---|---|---|---|---|
| Equal weight, rebalanced | 20.2% | 26.9% | 0.75 | -39% | 13% |
| Max-Sharpe, walk-forward | 23.6% | 30.9% | 0.76 | -46% | 26% |
| Min-variance, walk-forward | 8.5% | 21.6% | 0.39 | -35% | 12% |
| Equal weight, buy & hold | 21.5% | 39.8% | 0.54 | -66% | 0% |

Max-Sharpe basically tied equal weight on return per unit of risk, but with twice the trading and a deeper drawdown, so after transaction costs it would likely lose. Min-variance kept cutting Tesla (it was the most volatile stock) and missed most of the gains. This lines up with the academic finding that 1/N is very hard to beat once estimation error is real.

## How it works

- `R/portfolio_engine.R` does everything: loads prices, computes simple (not log) returns, runs a portfolio simulator where holdings drift daily and reset each January, solves the optimizations as quadratic programs with `quadprog`, and exports long-format CSVs for Tableau. It also checks my own rebalancing simulator against `PerformanceAnalytics::Return.portfolio` and prints the gap between them, and if `quantmod` is installed and you're online it adds SPY as a market benchmark (my run was without it).
- `tableau/Auto_Stock_Risk_Engine.twbx` is the packaged Tableau workbook, built on the CSVs the R script exports. Open it in Tableau Desktop or Tableau Public (free); the data is bundled inside.

Run it:

```
Rscript R/portfolio_engine.R      # writes tableau/*.csv and outputs/results_summary.csv
```

## Tableau dashboards

1. **Rebalancing vs Buy-and-Hold:** growth of $10,000 on a log scale plus the drawdown chart, so you can see buy-and-hold pulling ahead in 2020 and then giving most of it back in 2022.
2. **Optimization vs Equal Weight:** out-of-sample growth of all four strategies, return per unit of risk, worst drawdown, and the weights each optimizer picked every January (the max-Sharpe weights jump around a lot, min-variance mostly avoids Tesla).
3. **Stock Risk Profile:** return vs risk for each stock, the correlation heatmap, and 1-year rolling correlations (Toyota and Honda stay tied together, Tesla stays on its own).

## Limitations (read before trusting any number)

- **Hindsight in the stock list.** I picked these five in 2026. Nobody in 2010 knew Tesla would go up 260x, so the equal-weight results are flattered. The walk-forward test removes look-ahead from the weights, not from the stock selection.
- **Thin trading in Geely and BMW.** Both are over-the-counter ADRs. Geely had zero volume on 6.4% of days and an unchanged price on 7.3%, which makes it look less volatile and less correlated than it really is.
- **No transaction costs, taxes or FX modeling.** Turnover is reported so the cost can be estimated.
- **Return / risk uses a zero risk-free rate,** so it is a return-to-volatility ratio rather than a true Sharpe ratio. Rates were near zero for most of 2010 to 2021, but not after.
- **Mean returns are noisy.** The max-Sharpe weights jump around year to year (see `walkforward_weights.csv`), which is the real lesson of part 3.

## Data

Daily prices from a Kaggle auto-maker stock dataset (the `multi_cars_refined_kaggle` sheet in my original workbook), filtered to the five stocks and the common window. `data/prices_adjusted.csv` and `data/volume.csv` are the cleaned inputs.
