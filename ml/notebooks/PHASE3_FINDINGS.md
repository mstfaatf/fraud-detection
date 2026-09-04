# Phase 3 Findings — Random Forest

Summary of `03_random_forest.ipynb`. Phase 3-so-far scope: Random Forest only — no XGBoost yet
(deferred to a later pass in this phase) and no SHAP (deferred to Phase 4).

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

## Not done here (by design)

No XGBoost (next in Phase 3), no SHAP (Phase 4), no hyperparameter tuning beyond first-pass
defaults + `class_weight`, no SMOTE re-run for Random Forest (deferred to the model-comparison
notebook), no formal threshold selection.
