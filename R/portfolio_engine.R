# ==============================================================================
# Multi-Stock Risk & Return Engine: 5 Auto Stocks (2010-2026)
# Karthik Bommisetty | UIC MS Business Analytics
#
# Questions this answers:
#   1. How did Tesla, Toyota, Honda, BMW and Geely compare on return, risk and
#      drawdown from Tesla's IPO (29 Jun 2010) to 13 Feb 2026?
#   2. Does rebalancing an equal-weight portfolio every year help or hurt
#      versus just buying and holding?
#   3. Do "optimized" portfolios (minimum variance, maximum Sharpe) beat plain
#      equal weight when they are tested honestly, out of sample?
#
# Run from the project root:   Rscript R/portfolio_engine.R
# Input:   data/prices_adjusted.csv  (dividend/split-adjusted closes, 3,932 days)
# Output:  tableau/*.csv  (long-format files for the Tableau dashboards)
#          outputs/results_summary.csv  (headline numbers)
# ==============================================================================

# ---- 0. Setup ----------------------------------------------------------------
pkgs <- c("xts", "zoo", "PerformanceAnalytics", "quadprog")
missing <- pkgs[!pkgs %in% rownames(installed.packages())]
if (length(missing)) install.packages(missing, repos = "https://cloud.r-project.org")
suppressPackageStartupMessages({
  library(xts); library(zoo); library(PerformanceAnalytics); library(quadprog)
})

TICKERS   <- c("TSLA", "TM", "HMC", "BMWKY", "GELHY")
LOOKBACK  <- 756    # 3 years of trading days used to estimate mean and covariance
MAX_W     <- 0.40   # cap: no stock above 40% in the optimized portfolios
OOS_START <- 2014   # first out-of-sample year (first year with 3 years of history)
dir.create("tableau", showWarnings = FALSE)
dir.create("outputs", showWarnings = FALSE)

# ---- 1. Load prices ------------------------------------------------------------
raw    <- read.csv("data/prices_adjusted.csv", stringsAsFactors = FALSE)
prices <- xts(as.matrix(raw[, TICKERS]), order.by = as.Date(raw$Date))
prices <- na.omit(prices)
rets   <- na.omit(Return.calculate(prices, method = "discrete"))  # simple returns, NOT log

cat(sprintf("Loaded %d trading days: %s to %s\n",
            nrow(prices), start(prices), end(prices)))

# Data-quality check: Geely and BMW trade over the counter (thin volume)
vol_raw <- read.csv("data/volume.csv", stringsAsFactors = FALSE)
zero_volume_pct <- colMeans(vol_raw[, TICKERS] == 0)
zero_return_pct <- colMeans(coredata(rets) == 0)

# ---- 2. Helpers ----------------------------------------------------------------
# Portfolio simulator. Holdings drift with prices every day; on the first
# trading day of each new year we reset to target weights (if rebalance = TRUE).
# weight_fn(date) returns the target weights for that date.
simulate <- function(r, weight_fn, rebalance = TRUE) {
  dates <- index(r); m <- coredata(r); n <- nrow(m)
  out <- numeric(n); hold <- NULL
  wlog <- list(); tlog <- list()
  for (i in seq_len(n)) {
    new_year <- i > 1 && format(dates[i], "%Y") != format(dates[i - 1], "%Y")
    if (is.null(hold) || (rebalance && new_year)) {
      target <- weight_fn(dates[i])
      if (is.null(hold)) {
        value <- 1; turnover <- NA
      } else {
        value <- sum(hold); turnover <- 0.5 * sum(abs(target - hold / value))
      }
      hold <- target * value
      yr <- as.integer(format(dates[i], "%Y"))
      wlog[[length(wlog) + 1]] <- c(Year = yr, setNames(target, colnames(r)))
      tlog[[length(tlog) + 1]] <- c(Year = yr, Turnover = turnover)
    }
    start_val <- sum(hold)
    hold <- hold * (1 + m[i, ])
    out[i] <- sum(hold) / start_val - 1
  }
  list(returns = xts(out, order.by = dates),
       weights = do.call(rbind, wlog),
       turnover = do.call(rbind, tlog))
}

# Minimum-variance weights: long only, fully invested, each weight <= cap
min_var <- function(cov, cap = MAX_W) {
  n <- ncol(cov)
  D <- 2 * cov + diag(1e-10, n)
  A <- cbind(rep(1, n), diag(n), -diag(n))
  b <- c(1, rep(0, n), rep(-cap, n))
  w <- solve.QP(D, rep(0, n), A, b, meq = 1)$solution
  w <- pmax(w, 0); w / sum(w)
}

# Maximum-Sharpe (tangency, rf = 0) weights with the same constraints.
# Convex reformulation: minimise y' Sigma y  s.t.  mu'y = 1, y >= 0,
# y_i <= cap * sum(y); then w = y / sum(y).
max_sharpe <- function(mu, cov, cap = MAX_W) {
  n <- length(mu)
  if (all(mu <= 0)) return(min_var(cov, cap))
  D <- 2 * cov + diag(1e-10, n)
  A <- cbind(mu, diag(n), cap * matrix(1, n, n) - diag(n))
  b <- c(1, rep(0, 2 * n))
  sol <- tryCatch(solve.QP(D, rep(0, n), A, b, meq = 1)$solution,
                  error = function(e) NULL)
  if (is.null(sol)) return(min_var(cov, cap))   # infeasible -> fall back
  y <- pmax(sol, 0); y / sum(y)
}

# Performance stats for a daily return series (all annualized on 252 days)
perf <- function(r) {
  r <- as.xts(r)
  cagr <- as.numeric(Return.annualized(r, scale = 252, geometric = TRUE))
  vol  <- as.numeric(StdDev.annualized(r, scale = 252))
  mdd  <- -as.numeric(maxDrawdown(r))
  yearly <- tapply(as.numeric(r), format(index(r), "%Y"), function(x) prod(1 + x) - 1)
  c(CAGR = cagr, Vol = vol, Return_per_Risk = cagr / vol, Max_DD = mdd,
    Calmar = cagr / abs(mdd), Worst_Year = min(yearly), Best_Year = max(yearly))
}

growth_and_dd <- function(r, start_value = 10000) {
  g <- start_value * cumprod(1 + as.numeric(r))
  data.frame(Date = index(r), Growth_of_10k = g, Drawdown = g / cummax(g) - 1)
}

# ---- 3. Individual stocks (full period) ---------------------------------------
span_years <- as.numeric(end(prices) - start(prices)) / 365.25
stock_rows <- lapply(TICKERS, function(t) {
  p <- as.numeric(prices[, t]); r <- rets[, t]
  cagr <- (tail(p, 1) / p[1])^(1 / span_years) - 1     # calendar-time CAGR
  vol  <- as.numeric(StdDev.annualized(r, scale = 252))
  yearly <- tapply(as.numeric(r), format(index(r), "%Y"), function(x) prod(1 + x) - 1)
  data.frame(Ticker = t, CAGR = cagr, Vol = vol, Return_per_Risk = cagr / vol,
             Max_DD = -as.numeric(maxDrawdown(r)), Down_Years = sum(yearly < 0),
             Ten_K_Became = 10000 * tail(p, 1) / p[1],
             Zero_Volume_Days_Pct = zero_volume_pct[[t]],
             Zero_Return_Days_Pct = zero_return_pct[[t]])
})
stock_metrics <- do.call(rbind, stock_rows)
write.csv(stock_metrics, "tableau/stock_metrics.csv", row.names = FALSE)

corr <- cor(coredata(rets))
corr_long <- data.frame(Ticker_A = rep(rownames(corr), times = ncol(corr)),
                        Ticker_B = rep(colnames(corr), each = nrow(corr)),
                        Correlation = as.vector(corr))
write.csv(corr_long, "tableau/correlation_long.csv", row.names = FALSE)

# ---- 4. Rebalancing vs buy-and-hold (full period) -----------------------------
ew <- function(k) function(d) rep(1 / k, k)
full_runs <- list(
  EW_Rebalanced        = simulate(rets, ew(5), rebalance = TRUE),
  EW_BuyHold           = simulate(rets, ew(5), rebalance = FALSE),
  EW_ExTSLA_Rebalanced = simulate(rets[, TICKERS[-1]], ew(4), rebalance = TRUE)
)

# Cross-check my simulator against PerformanceAnalytics' built-in rebalancer
pa_check <- Return.portfolio(rets, weights = rep(0.2, 5), rebalance_on = "years")
cat(sprintf("Simulator vs Return.portfolio, max daily difference: %.2e\n",
            max(abs(as.numeric(pa_check) - as.numeric(full_runs$EW_Rebalanced$returns)))))

# ---- 5. Walk-forward optimization (out of sample, 2014 onward) ---------------
# Each January: estimate mean/covariance from the PREVIOUS 3 years only,
# solve for weights, hold for the year. No look-ahead.
trailing <- function(d) {
  hist <- tail(rets[index(rets) < d], LOOKBACK)
  list(mu = colMeans(coredata(hist)) * 252, cov = cov(coredata(hist)) * 252)
}
oos <- rets[as.integer(format(index(rets), "%Y")) >= OOS_START]

oos_runs <- list(
  EW_Rebalanced         = simulate(oos, ew(5), TRUE),
  EW_BuyHold            = simulate(oos, ew(5), FALSE),
  MinVar_WalkForward    = simulate(oos, function(d) min_var(trailing(d)$cov), TRUE),
  MaxSharpe_WalkForward = simulate(oos, function(d) { e <- trailing(d); max_sharpe(e$mu, e$cov) }, TRUE)
)

# Hindsight portfolio: what max-Sharpe would have picked knowing the full future
# (shown only to illustrate look-ahead bias; never investable)
mu_full  <- colMeans(coredata(rets)) * 252
cov_full <- cov(coredata(rets)) * 252
w_hindsight <- setNames(max_sharpe(mu_full, cov_full), TICKERS)

# ---- 6. Metrics tables ---------------------------------------------------------
metric_rows <- list()
for (nm in names(full_runs)) {
  r <- full_runs[[nm]]$returns
  p <- perf(r)
  p["CAGR"] <- prod(1 + as.numeric(r))^(1 / span_years) - 1   # calendar CAGR, like the stocks
  p["Return_per_Risk"] <- p["CAGR"] / p["Vol"]
  p["Calmar"] <- p["CAGR"] / abs(p["Max_DD"])
  metric_rows[[length(metric_rows) + 1]] <-
    data.frame(Window = "Full 2010-2026", Strategy = nm, t(p), Avg_Turnover = NA)
}
for (nm in names(oos_runs)) {
  run <- oos_runs[[nm]]
  to  <- run$turnover[, "Turnover"]
  metric_rows[[length(metric_rows) + 1]] <-
    data.frame(Window = "Out-of-sample 2014-2026", Strategy = nm, t(perf(run$returns)),
               Avg_Turnover = if (all(is.na(to))) 0 else mean(to, na.rm = TRUE))
}
# Optional market benchmark (S&P 500 ETF). Needs internet + quantmod; skipped
# quietly if either is missing, so the core results never depend on it.
spy <- tryCatch({
  suppressPackageStartupMessages(library(quantmod))
  s <- getSymbols("SPY", src = "yahoo", from = start(prices) - 5, to = end(prices) + 1,
                  auto.assign = FALSE)
  na.omit(Return.calculate(Ad(s)))[paste0(start(rets), "/", end(rets))]
}, error = function(e) NULL)
if (!is.null(spy)) {
  p_full <- perf(spy)
  p_full["CAGR"] <- prod(1 + as.numeric(spy))^(1 / span_years) - 1
  p_full["Return_per_Risk"] <- p_full["CAGR"] / p_full["Vol"]
  p_full["Calmar"] <- p_full["CAGR"] / abs(p_full["Max_DD"])
  spy_oos <- spy[as.integer(format(index(spy), "%Y")) >= OOS_START]
  metric_rows[[length(metric_rows) + 1]] <-
    data.frame(Window = "Full 2010-2026", Strategy = "SPY_Benchmark", t(p_full), Avg_Turnover = NA)
  metric_rows[[length(metric_rows) + 1]] <-
    data.frame(Window = "Out-of-sample 2014-2026", Strategy = "SPY_Benchmark",
               t(perf(spy_oos)), Avg_Turnover = 0)
  cat("SPY benchmark added.\n")
} else cat("SPY benchmark skipped (no internet or quantmod).\n")

strategy_metrics <- do.call(rbind, metric_rows)
rownames(strategy_metrics) <- NULL
write.csv(strategy_metrics, "tableau/strategy_metrics.csv", row.names = FALSE)

# ---- 7. Tableau exports: growth, drawdowns, weights ---------------------------
growth_rows <- list()
for (nm in names(full_runs))
  growth_rows[[length(growth_rows) + 1]] <-
    cbind(Window = "Full 2010-2026", Series = nm, growth_and_dd(full_runs[[nm]]$returns))
for (nm in names(oos_runs))
  growth_rows[[length(growth_rows) + 1]] <-
    cbind(Window = "Out-of-sample 2014-2026", Series = nm, growth_and_dd(oos_runs[[nm]]$returns))
for (t in TICKERS)
  growth_rows[[length(growth_rows) + 1]] <-
    cbind(Window = "Full 2010-2026", Series = t, growth_and_dd(rets[, t]))
if (!is.null(spy)) {
  growth_rows[[length(growth_rows) + 1]] <-
    cbind(Window = "Full 2010-2026", Series = "SPY_Benchmark", growth_and_dd(spy))
  growth_rows[[length(growth_rows) + 1]] <-
    cbind(Window = "Out-of-sample 2014-2026", Series = "SPY_Benchmark", growth_and_dd(spy_oos))
}
growth_long <- do.call(rbind, growth_rows)
write.csv(growth_long, "tableau/growth_drawdown_long.csv", row.names = FALSE)

weight_rows <- list()
for (nm in c("MinVar_WalkForward", "MaxSharpe_WalkForward")) {
  w <- oos_runs[[nm]]$weights
  for (t in TICKERS)
    weight_rows[[length(weight_rows) + 1]] <-
      data.frame(Strategy = nm, Year = w[, "Year"], Ticker = t, Weight = w[, t])
}
write.csv(do.call(rbind, weight_rows), "tableau/walkforward_weights.csv", row.names = FALSE)

# Calendar-year returns
cal_rows <- list()
add_cal <- function(r, nm) {
  y <- tapply(as.numeric(r), format(index(r), "%Y"), function(x) prod(1 + x) - 1)
  data.frame(Series = nm, Year = as.integer(names(y)), Return = as.numeric(y))
}
for (t in TICKERS) cal_rows[[length(cal_rows) + 1]] <- add_cal(rets[, t], t)
for (nm in names(full_runs)) cal_rows[[length(cal_rows) + 1]] <- add_cal(full_runs[[nm]]$returns, nm)
write.csv(do.call(rbind, cal_rows), "tableau/calendar_returns.csv", row.names = FALSE)

# ---- 8. Rolling 1-year risk -----------------------------------------------------
roll_vol <- rollapply(rets, 252, function(x) sd(x) * sqrt(252), by.column = TRUE, align = "right")
ew_vol   <- rollapply(full_runs$EW_Rebalanced$returns, 252, function(x) sd(x) * sqrt(252), align = "right")
roll_pair <- function(a, b) rollapply(rets[, c(a, b)], 252, function(x) cor(x[, 1], x[, 2]),
                                      by.column = FALSE, align = "right")
tm_hmc <- roll_pair("TM", "HMC")
tsla_avg <- (roll_pair("TSLA", "TM") + roll_pair("TSLA", "HMC") +
             roll_pair("TSLA", "BMWKY") + roll_pair("TSLA", "GELHY")) / 4

to_long <- function(x, series, metric)
  data.frame(Date = index(x), Series = series, Metric = metric, Value = as.numeric(x))
rolling <- rbind(
  do.call(rbind, lapply(TICKERS, function(t) to_long(na.omit(roll_vol[, t]), t, "Rolling_Vol_1Y"))),
  to_long(na.omit(ew_vol), "EW_Rebalanced", "Rolling_Vol_1Y"),
  to_long(na.omit(tm_hmc), "TM vs HMC", "Rolling_Corr_1Y"),
  to_long(na.omit(tsla_avg), "TSLA vs others (avg)", "Rolling_Corr_1Y")
)
write.csv(rolling, "tableau/rolling_risk.csv", row.names = FALSE)

# ---- 9. Efficient frontier (full sample, long only, no cap) -------------------
targets <- seq(min(mu_full), max(mu_full), length.out = 40)
frontier <- do.call(rbind, lapply(targets, function(tg) {
  n <- length(mu_full)
  A <- cbind(rep(1, n), mu_full, diag(n))
  sol <- tryCatch(solve.QP(2 * cov_full + diag(1e-10, n), rep(0, n), A,
                           c(1, tg, rep(0, n)), meq = 2)$solution, error = function(e) NULL)
  if (is.null(sol)) return(NULL)
  data.frame(Point = "Frontier", Label = "", Exp_Return = tg,
             Vol = sqrt(drop(t(sol) %*% cov_full %*% sol)))
}))
stock_pts <- data.frame(Point = "Stock", Label = TICKERS, Exp_Return = mu_full,
                        Vol = sqrt(diag(cov_full)))
w_eq <- rep(0.2, 5)
eq_pt <- data.frame(Point = "Portfolio", Label = "Equal weight",
                    Exp_Return = sum(w_eq * mu_full),
                    Vol = sqrt(drop(t(w_eq) %*% cov_full %*% w_eq)))
write.csv(rbind(frontier, stock_pts, eq_pt), "tableau/efficient_frontier.csv", row.names = FALSE)

# ---- 10. Console summary --------------------------------------------------------
cat("\n=== Stocks, full period ===\n")
print(transform(stock_metrics[, c("Ticker", "CAGR", "Vol", "Return_per_Risk", "Max_DD")],
                CAGR = round(CAGR, 3), Vol = round(Vol, 3),
                Return_per_Risk = round(Return_per_Risk, 2), Max_DD = round(Max_DD, 3)))
cat("\n=== Strategies ===\n")
print(cbind(strategy_metrics[, 1:2], round(strategy_metrics[, -(1:2)], 3)))
cat("\nHindsight max-Sharpe weights (look-ahead, NOT investable):\n")
print(round(w_hindsight, 2))
cat(sprintf("\nGELHY: zero-volume on %.1f%% of days, unchanged price on %.1f%% of days\n",
            100 * zero_volume_pct[["GELHY"]], 100 * zero_return_pct[["GELHY"]]))

write.csv(strategy_metrics, "outputs/results_summary.csv", row.names = FALSE)
cat("\nDone. Tableau files are in tableau/\n")
