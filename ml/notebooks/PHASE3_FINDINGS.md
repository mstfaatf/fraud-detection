# Phase 3 Findings — Random Forest and XGBoost

Summary of `03_random_forest.ipynb` and `04_xgboost.ipynb`. Phase 3-so-far scope: both tree-based
models trained and evaluated individually — no formal side-by-side model comparison or threshold
selection yet (next step), and no SHAP (deferred to Phase 4).

## Setup

Identical feature pipeline (`ml/src/preprocessing.py`) and identical adjusted time-based split
(`ml/src/split.py`, `time_based_split_adjusted`, cutoff step ≤ 575) as Phase 2, so results below
are directly comparable to the Logistic Regression baseline.

`RandomForestClassifier(n_estimators=200, max_depth=12, class_weight='balanced', random_state=42)`
— reasonable first-pass hyperparameters, not tuned. `class_weight='balanced'` mirrors the Phase 2
class-weighting-first approach.

**SMOTE:** not repeated here. Deferred to the model-comparison notebook, where it can be judged
against all variants (LR-balanced, LR-SMOTE, RF-balanced, RF-SMOTE, XGBoost, ...) at once rather
than piecemeal per model.

## PR-AUC comparison

All three numbers are evaluated on the identical adjusted test set (step 576–719, 0.97% fraud
rate).

| model | PR-AUC |
|---|---|
| Phase 2 — `LogisticRegression(class_weight='balanced')` | 0.5087 |
| Phase 2 — `LogisticRegression` + SMOTE (0.1 ratio) | 0.6102 |
| **Phase 3 — `RandomForest(class_weight='balanced')`** | **0.999963** |

Random Forest is a dramatic jump over both Logistic Regression variants (+0.39 over SMOTE,
+0.49 over balanced-weight) — large enough that it was checked rather than just reported.

**Why it's this high, and why that's legitimate rather than a bug:** the driver is
`amount_to_balance_ratio`. It is not leakage — it's built only from `amount` and `oldbalanceOrg`,
both known before the transaction executes — but PaySim's fraud-generation logic makes it an
almost deterministic signal: simulated fraud drains the origin account (`amount ≈ oldbalanceOrg`),
pushing the ratio to ≈1.0 in the overwhelming majority of fraud rows (test-set fraud median
0.999998), while legitimate transactions scatter across many orders of magnitude with no such
concentration. Confirmed quantitatively in the notebook: a single-feature classifier using the
raw ratio value scores a PR-AUC of only 0.0078 (the pattern is a narrow band near 1.0, not
"higher ratio ⇒ more fraud", so a monotonic/linear read of the feature fails), which is exactly
why Logistic Regression — structurally limited to linear/monotonic per-feature contributions —
can't exploit it, while a tree ensemble can carve out the band directly with a couple of
threshold splits. This also explains the qualitative jump from Phase 2 to Phase 3: it isn't that
Random Forest is generically "smarter" here, it's specifically able to reach a narrow-band pattern
the linear models' functional form cannot express.

At the default 0.5 threshold, Random Forest gets 1571/1572 fraud (recall 0.9994) with only 2 false
positives out of 160,449 legitimate test transactions (precision 0.9987) — a precision/recall
tradeoff far better than either Phase 2 variant's default-threshold numbers (see
`BASELINE_FINDINGS.md`).

## Feature importance sanity check

Built-in (mean-decrease-in-impurity) importances, not SHAP — that's Phase 4.

`amount_to_balance_ratio` dominates by a wide margin, consistent with the PR-AUC discussion above.
`oldbalanceOrg` and `amount` rank next, matching the EDA finding that fraud skews toward larger
amounts and co-occurs with larger origin balances. The four transaction-type dummies
(`type_CASH_IN`, `type_PAYMENT`, `type_TRANSFER`, `type_CASH_OUT`) all show broadly comparable,
moderate importance — expected for `TRANSFER`/`CASH_OUT` (the only two types that carry any fraud
in PaySim), and not a red flag for `CASH_IN`/`PAYMENT` either, since ruling a type *out* (it's
never fraud) is still useful splitting information for a tree. `type_DEBIT` and `day_of_week` are
both ~0, consistent with `DEBIT` never carrying fraud and no meaningful weekly pattern in the
simulation.

**Collinearity flag (documented, not fixed):** per the Phase 3 forward-note in `CLAUDE.md`,
`is_merchant_dest` and `type_PAYMENT` are perfectly collinear in PaySim. Their importances came
out split unevenly (0.052 vs. 0.061, ratio ≈0.85) rather than identical — unlike the Phase 2
Logistic Regression coefficients, which L2's minimum-norm solution forced to be exactly equal
under the same collinearity. Impurity-based importance has no such guarantee: whichever feature a
given tree happens to split on first claims the credit, so the split can come out uneven and would
plausibly shuffle under a different `random_state`. This is exactly the instability flagged in
advance — it should be read as "these two features are collinear and share credit somewhat
arbitrarily," not as "`type_PAYMENT` matters more than `is_merchant_dest`." SHAP (Phase 4) is
expected to give a more principled treatment of this pair.

## Not done in the Random Forest notebook (by design)

No XGBoost (covered separately below), no SHAP (Phase 4), no hyperparameter tuning beyond
first-pass defaults + `class_weight`, no SMOTE re-run for Random Forest (deferred to the
model-comparison notebook), no formal threshold selection.

---

# XGBoost

Summary of `04_xgboost.ipynb`.

## Setup

Identical feature pipeline and adjusted split as Random Forest / Phase 2.
`XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1, scale_pos_weight=<computed>)` —
first-pass hyperparameters, not tuned. `max_depth=6` is deliberately shallower than Random
Forest's `max_depth=12`, since boosted trees are conventionally kept shallow and get their power
from sequential correction rather than individually deep trees.

**`scale_pos_weight` was computed from the actual adjusted train fold, not guessed:**
`n_neg / n_pos = 6,193,958 / 6,359 = 974.05`. This is meaningfully different from the ~1:775 ratio
mentioned as a rough guide in the task prompt (which appears to reflect something closer to the
full-dataset or naive-split ratio) — the adjusted split's train fold has its own, lower fraud rate
(~0.10%) than the full PaySim dataset (~0.13%), so computing the ratio directly from the fold
actually used avoids baking in a mismatched assumption.

## PR-AUC comparison

All four numbers are evaluated on the identical adjusted test set (step 576–719, 0.97% fraud
rate).

| model | PR-AUC |
|---|---|
| Phase 2 — `LogisticRegression(class_weight='balanced')` | 0.5087 |
| Phase 2 — `LogisticRegression` + SMOTE (0.1 ratio) | 0.6102 |
| Phase 3 — `RandomForest(class_weight='balanced')` | 0.999963 |
| **Phase 3 — `XGBoost(scale_pos_weight=974.05)`** | **0.989184** |

XGBoost is, like Random Forest, a dramatic jump over both Logistic Regression variants, for the
same underlying reason documented above: `amount_to_balance_ratio`'s narrow-band (~1.0) signal
from PaySim's account-draining fraud pattern is something tree-based models can exploit directly
and linear models structurally can't. XGBoost's gain-based importance confirms this even more
starkly than Random Forest's did — see below.

**XGBoost scores slightly lower than Random Forest here (0.9892 vs. 0.999963)**, not the reverse
of what's sometimes assumed about gradient boosting vs. bagging. This is a first-pass,
untuned-hyperparameter comparison on one metric — not a claim that Random Forest is the better
algorithm in general, and not something this pass investigates further (e.g. via a learning-rate
or depth sweep). That kind of side-by-side judgment is exactly what's deferred to the next
(model-comparison) step, along with formal threshold selection.

At the default 0.5 threshold: 1562/1572 fraud caught (recall 0.9936), 187 false positives out of
160,449 legitimate test transactions (precision 0.8931) — clearly better than either Phase 2
variant's default-threshold numbers, but noticeably more false positives than Random Forest's 2 at
the same threshold.

## Feature importance sanity check

Built-in `gain` and `weight` importances, not SHAP (Phase 4).

**By gain, `amount_to_balance_ratio` overwhelmingly dominates** (~90% of total gain across all
splits in the model) — the same driver as Random Forest, and consistent with the PR-AUC discussion
above. **By weight** (how often a feature is used to split at all, regardless of how useful each
split is), the ranking looks different — `oldbalanceDest`, `amount`, and
`amount_to_balance_ratio` are all used a comparable number of times, and time-based features
(`hour_of_day`, `day_of_week`) show up more than they do by gain. `amount_to_balance_ratio` being
both frequently used *and* by far the most valuable per-use is why it dominates the model as
strongly as it does. `TRANSFER`/`CASH_OUT`/`CASH_IN` all register non-trivial gain (matching EDA
expectations — the two fraud-carrying types, plus `CASH_IN` being useful to rule out), and
`type_DEBIT` is near-zero, consistent with `DEBIT` never carrying fraud in PaySim.

**Collinearity flag — `is_merchant_dest` / `type_PAYMENT` — shows up here too, and more extremely
than in Random Forest:** `type_PAYMENT` gets **exactly zero** gain and weight importance in this
model; `is_merchant_dest` (perfectly collinear with it — confirmed via the same crosstab as
`BASELINE_FINDINGS.md`) picks up all of the corresponding signal instead. This is a *more* extreme
version of the same instability documented for Random Forest (0.052 vs. 0.061 there — uneven but
both nonzero). The mechanism differs by model family: Random Forest's bagging (bootstrap samples
plus, optionally, per-split feature subsampling) gives both collinear columns a chance to get
chosen across different trees, so credit ends up split unevenly but nonzero on both sides.
XGBoost's sequential, greedy boosting has no equivalent source of randomness pushing it to use
both — once an early tree splits on one of two identical columns, there is no remaining gradient
signal for the other column to improve on, so it can end up entirely unused. **This should be read
as "XGBoost happened to route the entire merchant-destination signal through `is_merchant_dest`
instead of `type_PAYMENT`," not as "`type_PAYMENT` doesn't matter."** This is precisely the kind
of case the Phase 3 forward-note in `CLAUDE.md` anticipated SHAP would need to handle more
carefully than raw importance scores — not attempted in this pass.

## Not done here (by design)

No SHAP (Phase 4), no hyperparameter tuning beyond first-pass defaults + `scale_pos_weight`, no
SMOTE comparison for XGBoost (deferred to the model-comparison notebook, same as Random Forest),
no formal threshold selection, and no formal side-by-side model-selection judgment across all four
models — that's the next step now that Random Forest, XGBoost, and both Phase 2 Logistic
Regression variants all exist on the identical split and feature set.

---

# Model Comparison and Threshold Selection

Summary of `05_model_comparison.ipynb`. All four models below were retrained in that notebook
(none were serialized from their individual notebooks) using the exact documented hyperparameters
and `random_state=42` — the resulting PR-AUC values reproduce the individually-reported numbers
exactly, confirming this isn't introducing a new source of variation.

## Comparison table

All four evaluated on the identical adjusted test set (step 576–719, 0.97% fraud rate). Full
precision/recall/F1 at four thresholds (0.1, 0.3, 0.5, 0.7) per model are in the notebook; the 0.5
(default) row for each is reproduced here:

| model | PR-AUC | precision @0.5 | recall @0.5 | F1 @0.5 | FP @0.5 | FN @0.5 |
|---|---|---|---|---|---|---|
| LR (balanced) | 0.5087 | 0.1087 | 0.9567 | 0.1953 | 12,329 | 68 |
| LR + SMOTE | 0.6102 | 0.3671 | 0.6921 | 0.4797 | 1,876 | 484 |
| Random Forest | 0.999963 | 0.9987 | 0.9994 | 0.9990 | 2 | 1 |
| XGBoost | 0.989184 | 0.8931 | 0.9936 | 0.9407 | 187 | 10 |

The overlaid PR curves make the tree-vs-linear gap visually obvious; a zoomed Random
Forest-vs-XGBoost view shows Random Forest's curve sitting at or above XGBoost's across nearly the
entire recall range — the PR-AUC gap is a real, consistent operating-point advantage, not an
artifact of the aggregate metric.

## Chosen model: XGBoost — despite Random Forest's higher PR-AUC

**By PR-AUC alone, Random Forest wins** (0.999963 vs. 0.989184) and would be the model to carry
forward if that were the only consideration. **XGBoost is chosen instead**, based on measurements
taken specifically because this project's architecture makes them relevant — not a hypothetical
concern:

| | Random Forest | XGBoost |
|---|---|---|
| single-transaction `predict_proba` latency | ~40 ms | ~1.6 ms (~25x faster) |
| full test-set (162K rows) batch latency | 0.18 s | 0.09 s |
| pickled model size | 55.1 MB | 0.6 MB (~92x smaller) |

`CLAUDE.md` establishes this as a **real-time** fraud detector — a payment is scored before it
executes, meaning one `predict_proba` call per incoming transaction in the backend, not a batch
job — which makes single-prediction latency and deployed model size directly relevant engineering
considerations. Both effects trace to the same cause: 200 trees at `max_depth=12` (Random Forest)
is a much larger, deeper structure than 200 trees at `max_depth=6` (XGBoost) — the extra depth is
exactly what let Random Forest capture the `amount_to_balance_ratio` signal a hair more
completely, but the same depth makes each prediction and the serialized model proportionally
larger.

**Reasoning for choosing XGBoost:**

1. Both models are already far beyond what's needed to demonstrate the ML story — XGBoost's
   default-threshold numbers (recall 0.9936, 187 FP) are strong in absolute terms even though
   Random Forest's are better (recall 0.9994, 2 FP). The remaining PR-AUC gap is "excellent" vs.
   "even more excellent," not "excellent" vs. "unusable."
2. The inference-cost gap (~25x latency, ~92x size) is large and directly tied to this project's
   stated real-time architecture, while the PR-AUC gap lives entirely inside PaySim's synthetic
   account-draining pattern — a signal that would need re-validation on any real-world dataset
   regardless of which tree model is picked. Weighing an engineering tradeoff instead of
   mechanically taking the top metric is itself part of what this project is meant to demonstrate.
3. XGBoost's smaller, shallower structure is a modest interpretability win heading into Phase 4's
   SHAP work — fewer, shallower trees are cheaper to explain than 200 depth-12 trees.

**This is an explicit judgment call specific to this project's real-time constraint, not a
mechanical rule** — a system without that constraint (or with unlimited compute) could reasonably
choose Random Forest instead.

## Threshold selection for XGBoost: ≈0.61 (not the default 0.5)

**Target: maximize precision subject to recall ≥ 99%.** Missing fraud (a false negative) is
generally costlier than an extra manual review (a false positive), so recall is prioritized —
but not without bound, since false positives carry real operational cost too. Among every
threshold on XGBoost's PR curve with recall ≥ 99% (92,377 candidate thresholds), the one with the
highest precision was selected — the least aggressive threshold that still clears the recall bar,
rather than an arbitrary round number.

**Chosen threshold: 0.6145** → precision 0.8969, recall 0.9905 (TP=1,557, FP=179, FN=15,
TN=160,270). Compared to the default 0.5 (precision 0.8931, recall 0.9936, FP=187, FN=10), this is
a small, reasoned adjustment — trading a little recall for a little precision — consistent with
XGBoost's PR curve already being fairly flat in this region.

**This threshold is provisional for the demo/dashboard phase, not a production-calibrated
business decision.** The 99%-recall target is a reasonable demonstrative choice, not one derived
from real cost inputs. A genuine production threshold would need the actual dollar cost of a
missed fraud transaction, the actual cost of a false positive (review time, customer friction),
and how those trade off at a business's specific scale — none of which exist for a synthetic
PaySim-based project.

## Residual split skew applies equally to this comparison

The adjusted split's ~9.5x train/test fraud-rate skew (see `CLAUDE.md`, "Time-Based Split
Methodology") applies identically to all four models compared here — same training-fold rate
(~0.10%), same test-fold rate (~0.97%) for every model — so while it plausibly understates
absolute recall for all four relative to a hypothetical rate-matched split, it does not bias the
comparison or the resulting model/threshold choice.

## Not done here (by design)

No formal hyperparameter tuning for any model (all four remain first-pass configurations), no
SMOTE comparison for the tree-based models (judged not worth adding given how far ahead of the
Logistic Regression variants both already are), no production-grade cost-based threshold
calibration. Phase 4 (SHAP-based explainability on the chosen XGBoost model) is next.
