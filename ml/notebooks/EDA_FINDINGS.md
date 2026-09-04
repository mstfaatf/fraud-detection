# EDA Findings — PaySim

Summary of `01_eda.ipynb`, run against the full dataset (6,362,620 rows). All numbers below are
from that notebook's actual output, not assumptions.

## What we found

**Class distribution.** 8,213 fraud out of 6,362,620 transactions — a fraud rate of **0.1291%**
(roughly 1 in 775). This is the number that drives everything downstream: accuracy is a
meaningless metric here, we'll need PR-AUC / recall-at-precision style metrics, and we'll need a
resampling strategy (SMOTE or similar, hence `imbalanced-learn` already in the ML requirements)
before training anything.

**Missing values.** None. Zero missing values across all 11 columns — expected for a synthetic
dataset, but confirmed rather than assumed.

**Duplicates.** Zero fully-duplicated rows. Separately, only **0.15%** of `nameOrig` values
appear more than once — almost every simulated "customer" transacts exactly once in this
dataset. That matters for feature engineering (see below): there's essentially no repeat-customer
history to build velocity/behavioral features from.

**`amount` distribution.** Heavily right-skewed, as expected for financial data (mean 179,862 vs.
median 74,872; max 92.4M). Fraud transactions skew toward larger amounts than legitimate ones —
fraud mean is 1,467,967 vs. 178,197 for non-fraud, fraud median is 441,423 vs. 74,685. Log-scale
views in the notebook make the shape usable for modeling/visualization.

**Fraud by transaction `type` — confirmed.** Fraud occurs **only** in `TRANSFER` and `CASH_OUT`.
`PAYMENT`, `CASH_IN`, and `DEBIT` have exactly zero fraud cases in this dataset (2.15M, 1.4M, and
41K transactions respectively, all fraud-free). Within the two fraud-eligible types, `TRANSFER`
has a meaningfully higher per-transaction fraud rate (0.77%) than `CASH_OUT` (0.18%), even though
`CASH_OUT` has ~4x the volume — the two types end up contributing almost the same raw fraud count
(4,097 vs. 4,116).

**Time patterns — the "rate by hour" view is misleading.** Fraud *count* per hour-of-day is
essentially flat (roughly 300–375 fraud cases in every single hour, all 24 hours). But *legitimate*
transaction volume follows a strong daily cycle — as low as ~1,200–2,000 transactions/hour
overnight (hours 3–5) vs. ~450,000–650,000/hour during the day. Because fraud count stays flat
while the legitimate denominator collapses at night, the *fraud rate* spikes to 16–22% in the
overnight hours purely as an artifact of that denominator, not because fraud actually concentrates
at night. **Flagged below as a leakage-adjacent trap** — see next section.

**Balance consistency — the standout finding.** For legitimate transactions, the origin balance
equation (`newbalanceOrig == oldbalanceOrg - amount`) holds only **20.1%** of the time. For fraud,
it holds **99.45%** of the time. Even more striking: in **97.7%** of fraud transactions, the
origin account is left with `oldbalanceOrg == amount` and `newbalanceOrig == 0` — i.e. the account
is drained to exactly zero. Legitimate transactions show this pattern **0%** of the time. This is
by far the strongest signal in the dataset, and it's almost certainly a direct artifact of how
PaySim injects synthetic fraud (its published fraud-injection method empties the origin account),
not a subtle pattern a model has to work to find. **Flagged below as the main leakage/artifact
risk.**

Destination-side consistency (`newbalanceDest == oldbalanceDest + amount`) is a weaker signal:
34.2% consistent for legitimate vs. 43.5% for fraud — present, but nowhere near as dramatic.

**Merchant destinations.** Every `nameDest` starting with `M` (merchant) has `oldbalanceDest` and
`newbalanceDest` exactly 0, with zero exceptions (2,151,495 rows checked) — merchant balances are
simply never tracked in this simulation. Separately, merchant destinations occur **only** on
`PAYMENT` transactions — every other type (`TRANSFER`, `CASH_OUT`, `CASH_IN`, `DEBIT`) goes to a
customer (`C`-prefixed) destination. Since `PAYMENT` has zero fraud anyway, this degenerate
merchant-balance behavior doesn't hurt the fraud-relevant subset of the data.

**Correlation analysis.** Raw pairwise correlation with `isFraud` is weak across the board:
`amount` 0.077, `isFlaggedFraud` 0.044, `step` 0.032, everything else under 0.01. This confirms
the strongest signal (origin-balance-drained) is a **joint/nonlinear relationship between three
columns**, not something a simple correlation would surface — engineered features matter here,
plain linear correlation doesn't tell the real story.

**`isFlaggedFraud` — verified empirically, not assumed.** Only **16 rows** in the entire 6.36M-row
dataset have `isFlaggedFraud == 1`, and all 16 are genuine fraud (100% precision, but recall
against the 8,213 actual fraud cases is ~0.19% — functionally useless as a detector). The
documented rule ("flags transfers over 200,000") does **not** hold empirically: 409,110
`TRANSFER`s exceed 200,000, of which only 16 are flagged and only 2,740 are even fraud. Whatever
actually triggers `isFlaggedFraud` is far narrower than documented — inspecting the 16 flagged
rows shows all of them have `newbalanceOrig == oldbalanceOrg` (the balance field wasn't decremented
at all, a different anomaly than the "drained to zero" pattern seen in the rest of the fraud
population). Conclusion: **`isFlaggedFraud` is not a usable feature** — near-zero coverage, and
the field appears to reflect a narrow/buggy internal simulator rule rather than a general
detection signal.

## What changes in our planned feature schema

This resolves the open question in `CLAUDE.md` ("final feature schema not yet finalized pending
EDA"):

- We can likely **restrict modeling to `TRANSFER` and `CASH_OUT` transactions**, or at minimum
  make `type` a first-class feature — the other three types contribute zero fraud signal and
  mostly just add class-imbalance noise if included undifferentiated.
- **Customer-history / velocity features are not really buildable** from this dataset — with only
  0.15% of `nameOrig` values repeating, there isn't enough repeat-customer activity to compute
  meaningful rolling windows, transaction counts, or behavioral baselines per account. If we want
  that kind of feature for the explainability story, it'll need to be flagged as a limitation or
  synthetically supplemented, not derived from PaySim as-is.
- `nameOrig` / `nameDest` themselves are not usable as categorical features directly (near-unique,
  high cardinality) — their only real value is the derived `dest_is_merchant` flag and (very
  limited) repeat-customer lookups.

## Potential leakage / artifact traps

1. **Origin-balance-drained is too clean to be a "learned" pattern — and, separately, it's
   unusable for our real-time use case regardless.** 97.7% fraud vs. 0% legitimate is close to a
   hard rule, not a statistical tendency, and it's almost certainly an artifact of PaySim's
   synthetic fraud-injection method rather than evidence real-world fraud looks like this. But
   there's a second, independent, and more decisive problem: **`newbalanceOrig` and
   `newbalanceDest` are post-transaction state.** Our platform scores a payment *before* it
   executes — at decision time, the transaction hasn't happened yet, so these fields (and anything
   derived from them) don't exist yet. **DECISION (locked in): `newbalanceOrig`, `newbalanceDest`,
   and all features derived from them (`errorBalanceOrig`, `errorBalanceDest`,
   `origin_fully_drained`) are excluded from the model's feature set entirely** — not flagged as a
   caveat, not included with a warning label, excluded. This holds even if the drained-to-zero
   pattern were a genuine (non-artifact) fraud behavior: it would still be leakage for a
   pre-transaction real-time scorer.
2. **Fraud rate by hour-of-day is confounded by volume, not a real time-of-day effect.** Don't
   feed a naive "hourly fraud rate" feature into the model — it would just be re-encoding
   legitimate-transaction volume troughs as a fraud signal. If time-of-day is used at all, prefer
   raw `hour_of_day` and let the model weigh it, rather than a precomputed rate lookup.
3. **`isFlaggedFraud` should not be used as a predictive input** — with 16 positive rows total, it
   would function more as a near-constant column than a real feature, and including it risks the
   model (or, worse, a reader of the results) mistaking it for a legitimate detection signal it
   isn't.

## Updated proposed feature list (finalized)

**Real (raw, usable — available at pre-transaction decision time)**
- `step`
- `type` (categorical — encode; only `TRANSFER`/`CASH_OUT` carry fraud)
- `amount`
- `oldbalanceOrg`
- `oldbalanceDest`

**Engineered (derived only from pre-transaction fields, no leakage)**
- `hour_of_day` = `step % 24`
- `day` = `step // 24`
- `log_amount` = `log1p(amount)` (for models/visualizations sensitive to skew)
- `amount_to_balance_ratio` = `amount / (oldbalanceOrg + 1)` — uses only the *pre*-transaction
  origin balance, safe for real-time scoring
- `dest_is_merchant` = `nameDest.startswith("M")`

**Excluded — leakage (not available at real-time decision time)**
- `newbalanceOrig`, `newbalanceDest` — post-transaction state; a payment is scored *before* it
  executes, so these values don't exist yet at decision time
- `errorBalanceOrig`, `errorBalanceDest`, `origin_fully_drained` — all derived from the
  post-transaction balance fields above, so they inherit the same leakage problem even though
  `origin_fully_drained` was the single strongest raw correlate with fraud found in this EDA.
  Excluded regardless of predictive power — see leakage trap #1 above.

**Excluded — insufficient data for the trained model (velocity)**
- Account-history / velocity features (transaction count or frequency per account, rolling
  windows, etc.) — EDA found only 0.15% of `nameOrig` values repeat, so PaySim cannot support
  meaningful behavioral/velocity features for training. **Not included in the model's input
  list.** Note: a later-phase transaction simulator may still generate velocity-style demo
  scenarios (rapid repeated transactions) for dashboard/UI purposes — those are demo inputs only,
  not features the trained model was fit on. This is a documented dataset limitation, not a
  silently dropped feature.

**Drop / deprioritize**
- `nameOrig`, `nameDest` as raw identifiers — too high-cardinality, minimal repeat activity
- `isFlaggedFraud` — empirically confirmed non-predictive (see above); may keep as a passthrough
  reference column, not as a model input

**Synthetic / demo-only (not present in PaySim; never trained-model inputs)**
- Merchant category, device/channel, geo-style fields — useful for dashboard flavor and
  explainability storytelling later, but PaySim has no such fields and the trained model will
  never see them as inputs. Ties into the still-open "Stripe field-mapping adapter" item in
  `CLAUDE.md`.

## Not done here (by design)

No preprocessing, train/test splitting, resampling, or modeling in this pass — EDA only, per
scope. Next step is deciding the actual preprocessing pipeline based on the findings above.
