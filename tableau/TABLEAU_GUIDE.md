# Tableau build guide

All files in this folder are long format (one row per date per series), so every chart is a drag-and-drop with `Series` on Color. The R script regenerates them; the copies here came from the Python check and should match.

| File | What it holds |
|---|---|
| `growth_drawdown_long.csv` | Date, Window, Series, Growth_of_10k, Drawdown for every stock and strategy |
| `strategy_metrics.csv` | CAGR, Vol, Return_per_Risk, Max_DD, Calmar, worst/best year, turnover |
| `stock_metrics.csv` | Per-stock CAGR, vol, drawdown, down years, $10K became, data-quality flags |
| `walkforward_weights.csv` | Year, Strategy, Ticker, Weight for the two optimized portfolios |
| `rolling_risk.csv` | 1-year rolling volatility and correlation |
| `correlation_long.csv` | 5x5 correlation matrix |
| `calendar_returns.csv` | Return by year for each stock and strategy |
| `efficient_frontier.csv` | Frontier curve plus the five stocks and the equal-weight point |

## Dashboard 1: Rebalancing vs buy-and-hold

1. Connect `growth_drawdown_long.csv`. Filter `Window = Full 2010-2026` and `Series` in EW_Rebalanced, EW_BuyHold.
2. **Growth sheet:** Date (exact date, continuous) on Columns, Growth_of_10k on Rows, Series on Color. Right-click the axis, Edit Axis, tick Logarithmic. Use ONE axis, not dual axis: both lines are in dollars, so they belong on the same scale.
3. **Drawdown sheet:** same setup with Drawdown on Rows, formatted as percentage. Add a reference line at 0.
4. Stack the two sheets vertically and turn on Dashboard Action > Highlight on Series so hovering one line highlights it in both.
5. Title: "Buy-and-hold earned more, but rebalancing cut the worst drop from -71% to -39%."

## Dashboard 2: Does optimization beat equal weight?

1. Same growth file, filter `Window = Out-of-sample 2014-2026`. Growth line chart with the four strategies.
2. Connect `strategy_metrics.csv`, filter to the out-of-sample window. Two bar charts side by side: Return_per_Risk and Max_DD by Strategy (one color; the label names the strategy).
3. Connect `walkforward_weights.csv`. Stacked bar: Year on Columns, SUM(Weight) on Rows, Ticker on Color, Strategy as a filter or on Rows for two small multiples. This shows how unstable the max-Sharpe weights are year to year, which is the reason it needs twice the turnover.
4. Title: "Out of sample, max-Sharpe roughly tied equal weight with double the trading."

## Dashboard 3: Stock risk profile

1. `stock_metrics.csv`: scatter with Vol on Columns, CAGR on Rows, Ticker as Label. Size by Ten_K_Became if you want.
2. `efficient_frontier.csv`: Vol on Columns, Exp_Return on Rows, Point on Color; use a line mark for Frontier rows (filter) and circles for Stock/Portfolio rows via a dual-mark layer (same axes, so this is fine). Note: these are arithmetic mean returns, so they sit above the CAGRs.
3. `correlation_long.csv`: Ticker_A on Columns, Ticker_B on Rows, Correlation on Color (sequential single hue) and Label. Highlights TM-HMC at 0.73 and Tesla near 0.25 with everything.
4. `rolling_risk.csv` filtered to Metric = Rolling_Corr_1Y: line chart of the two correlation series over time.

## Publishing

Save to Tableau Public (File > Save to Tableau Public), then put the link in the README and on LinkedIn Featured.
