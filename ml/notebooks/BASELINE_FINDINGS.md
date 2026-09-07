# Baseline Model Findings — Logistic Regression

Summary of `02_baseline_model.ipynb`. Phase 2 scope: Logistic Regression only — no Random Forest,
no XGBoost (that's Phase 3).

## Split used

The **adjusted** cutoff from `ml/src/split.py`, not the naive 80/20 one. The notebook prints both
so this is verifiable rather than assumed:

| split | rows | fraud | fraud rate | steps |
|---|---|---|---|---|
| naive train | 6,239,040 | 6,559 | 0.1051% | 1–594 |
| naive test | 123,580 | 1,654 | 1.3384% | 595–743 |
| **adjusted train (used)** | 6,200,317 | 6,359 | 0.1026% | 1–575 |
| **adjusted test (used)** | 162,021 | 1,572 | 0.9702% | 576–719 |

**Bug found and fixed while wiring this up:** `propose_adjusted_cutoff()` only recomputed the
cutoff *value* — feeding that value into the plain `time_based_split()` still let the test side
run to the dataset's true max step, so PaySim's degenerate all-fraud day 30 (step 720–743, 282/282
rows fraud, zero legitimate transactions) stayed in the test set regardless. Fixed in
`ml/src/split.py` with a new `time_based_split_adjusted()` that also upper-bounds the test side at
the last usable step (719). This is now covered by regression tests in `ml/tests/test_split.py`.

**Residual skew, by design not fully removed:** the adjusted split still has a 9.5x fraud-rate gap
(train 0.103% vs. test 0.970%) — see "Interpretation caveat" below.

## PR-AUC (headline metric)

Accuracy is meaningless at this fraud rate ("always predict legitimate" scores 99.03% while
catching zero fraud) and ROC-AUC is misleading too — with legitimate transactions outnumbering
fraud roughly 100:1 in this test set, the false-positive-rate axis is dominated by an enormous
negative class, so ROC-AUC can look strong even at operating points with poor real-world precision.
PR-AUC (average precision) is computed purely from the positive class's perspective and is the
metric used here.

| variant | PR-AUC |
|---|---|
| **PRIMARY** — `class_weight='balanced'` | 0.5087 |
| **COMPARISON** — SMOTE (`sampling_strategy=0.1`) | 0.6102 |
| difference | **+0.1014 (SMOTE higher, ~20% relative)** |

**SMOTE outperformed `class_weight='balanced'` on this test set, by a clear and non-trivial
margin.** This was checked, not assumed to go the "expected" way: both models converged cleanly
(70 and 44 iterations respectively, well under `max_iter=1000`, no convergence warnings), so the
gap isn't a fitting artifact.

The confusion-matrix table (four illustrative thresholds — 0.1/0.3/0.5/0.7, formal threshold
selection deferred) shows why: at every threshold, SMOTE trades some recall for a large precision
gain over the balanced-weight model. At the default 0.5 threshold: balanced-weight catches more
fraud (recall 0.9567, precision 0.1087) while SMOTE is more conservative but far more useful in
practice (recall 0.6921, precision 0.3671). The balanced-weight model's very high recall comes with
so many false positives (12,329 at t=0.5, out of 148,449 legitimate test transactions) that it
would be operationally unusable as-is; SMOTE's precision/recall balance is more usable out of the
box, even before any formal threshold tuning.

**On `sampling_strategy=0.1`:** this ratio was picked once, from reasoning, not tuned via grid
search — no other ratios (e.g. 0.05, 0.3, 0.5, or full 1:1 rebalancing) were tried in this pass.
The 0.1 choice was driven by two considerations documented in the notebook: keeping the resampled
training set's compute cost bounded (full 1:1 SMOTE on ~6.2M training rows would synthesize
another ~6.2M rows), and a methodological concern about synthesizing further interpolations of
PaySim's already-algorithmically-generated fraud examples. **This means the reported SMOTE PR-AUC
(0.6102) is one point on an untuned hyperparameter, not a ceiling or a fully-controlled comparison
against `class_weight='balanced'`** — some meaningful fraction of the +0.1014 PR-AUC gap could be
specific to this ratio rather than to SMOTE-vs-class-weighting as a general strategy. A proper
sweep over `sampling_strategy` (and, for that matter, over decision thresholds/regularization
strength for both variants) is left for a later pass if this comparison needs to bear more weight
than "SMOTE is a reasonable comparison point to carry forward" — which is as far as this finding is
used for in the Phase 3 recommendation below.

## Was SMOTE worth the added complexity?

**Yes, on this evidence.** It's a genuinely more complex pipeline (a resampling step that must be
scoped correctly to the training fold — verified here via `imblearn.pipeline.Pipeline`, whose
resampling step runs during `.fit()` but is structurally skipped during `.predict()`, so there's no
code path for test-set leakage) versus a single constructor argument for `class_weight='balanced'`.
That complexity earned a real, meaningful PR-AUC gain and a much more usable precision/recall
tradeoff at the default threshold — not a marginal difference that wouldn't justify the extra
moving part.

## Coefficient sanity check (`class_weight='balanced'` model)

Coefficients are on the standardized feature scale, so magnitudes are roughly comparable across
features with very different original units.

| feature | coefficient |
|---|---|
| type_CASH_IN | -106.88 |
| type_CASH_OUT | +64.40 |
| type_TRANSFER | +37.82 |
| oldbalanceOrg | +34.05 |
| type_PAYMENT | +6.85 |
| is_merchant_dest | +6.85 |
| amount_to_balance_ratio | -6.08 |
| amount | -3.91 |
| type_DEBIT | -2.64 |
| hour_of_day | -0.46 |
| oldbalanceDest | -0.08 |
| day_of_week | +0.01 |

**Matches EDA expectations on the signal that matters most:** `TRANSFER` and `CASH_OUT` — the only
two types that carry any fraud in PaySim — sit clearly on the positive side, well separated from
`CASH_IN` (zero fraud in the data, and by far the most negative coefficient). The model has
correctly learned the type split the EDA identified.

**`oldbalanceOrg` (+34.1) is positive and largely independent** of `amount`/`amount_to_balance_ratio`
(correlation checked directly: r ≈ -0.005 and r ≈ -0.04 respectively) — consistent with the EDA
finding that fraud drains the origin account (fraud's `amount ≈ oldbalanceOrg`), so larger origin
balances co-occur with fraud in this data.

**Two caveats surfaced by the sanity check, not swept under the rug:**

1. `amount` (-3.91) and `amount_to_balance_ratio` (-6.08) are both negative, which is *not* a clean
   "larger amount → less fraud" reading. The two are correlated at r ≈ 0.82 in the training data,
   so under L2 regularization their individual coefficients trade off against each other and
   shouldn't be interpreted in isolation — the raw EDA correlation (fraud skews toward much larger
   amounts, 1.47M mean vs. 178K) is not contradicted by this, it's just not decomposable into these
   two specific numbers.
2. `is_merchant_dest` and `type_PAYMENT` have **identical** coefficients (+6.85) because they are
   **perfectly collinear** in this dataset — confirmed directly via a crosstab (every `PAYMENT`
   transaction goes to a merchant and vice versa, zero exceptions). They are literally duplicate
   columns; L2 regularization's unique minimum-norm solution splits any total effect exactly in
   half between two identical columns, which is exactly what's observed. Their *combined*
   contribution (+13.7) still sits well below `TRANSFER`/`CASH_OUT` and well above `CASH_IN`, so the
   ranking among type-related coefficients remains sane — but a single one of these two numbers
   read alone ("merchant destinations raise fraud risk") would be the wrong takeaway.

All five `type_*` dummies are included with none dropped as a reference category. This is normally
the dummy-variable trap for OLS, but `sklearn`'s default L2-regularized `LogisticRegression`
handles exact collinearity gracefully (unique minimum-norm solution), so this was a deliberate
choice, not an oversight — see `preprocessing.py` and the notebook markdown.

## Interpretation caveat: residual train/test fraud-rate skew

Even after excluding PaySim's fully degenerate day 30, the adjusted split's test set still runs at
a ~9.5x higher fraud rate (0.97%) than the training set (0.10%), because of the *gradual*
legitimate-transaction-volume decline across days 17–29 that the adjustment doesn't (and isn't
meant to) fully flatten — see `CLAUDE.md` and `ml/src/split.py`.

**Practical effect on these numbers:** both models were trained to recognize fraud against a
background rate roughly 9-10x lower than what they're evaluated against. A model calibrated
against a rarer positive class tends to be more conservative — it takes more evidence to push a
score above a given threshold — than one trained on a rate matching the test distribution. This
plausibly **understates recall** for both variants relative to a hypothetical rate-matched split,
and should be kept in mind when comparing these absolute numbers to any future model evaluated on
a differently-adjusted split. It does not obviously bias the *relative* comparison between the two
variants (both are trained and evaluated on the identical split), which is why the SMOTE-vs-balanced
comparison above is trusted more than the absolute PR-AUC values in isolation.

## Recommendation for Phase 3

Carry the **SMOTE-resampled approach** forward as the comparison point for Random Forest and
XGBoost, alongside `class_weight='balanced'` (tree-based models support `class_weight` natively
too, so both approaches remain cheap to compare again at that stage). Do not treat either Phase 2
PR-AUC value as a hard target — Phase 3 models are expected to do meaningfully better, and the
residual split skew above means Phase 2 and Phase 3 numbers are only comparable to each other if
evaluated on the exact same adjusted test set (which they should be, for consistency).

## Not done here (by design)

No Random Forest, no XGBoost, no formal threshold selection (the four illustrated thresholds are
for showing the precision/recall tradeoff, not a recommendation), no hyperparameter tuning beyond
defaults + `class_weight`/`sampling_strategy`. Per Phase 2 scope: Logistic Regression baseline only.
