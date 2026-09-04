# Isolation Forest Findings — Phase 4 (part 2)

Full notebook: `07_isolation_forest.ipynb`. **Scope: exploratory/evaluative only — no backend or API
integration.** This closes out Phase 4 (SHAP explainability, part 1, is in `SHAP_FINDINGS.md`).

Isolation Forest (`n_estimators=200`, `max_samples="auto"`, first-pass/reasonable hyperparameters,
not tuned) was fit **unsupervised** — `isFraud` was never passed to `.fit()` — on the same adjusted
time-based split and feature pipeline as every prior model. This notebook also marks the first time
anything from Phase 4's serialized artifacts (`ml/models/xgboost_model.pkl`,
`ml/models/model_metadata.json`) has actually been loaded and reused rather than retrained.

## The contamination hyperparameter: not defaulted to the known fraud rate

`contamination` only sets a percentile-based threshold on the anomaly score for hard flagging —
confirmed by reading `IsolationForest.fit()`'s source (`self.offset_ = np.percentile(scores, 100 *
contamination)`); it has zero effect on the trees themselves or on the continuous score ranking
used for PR-AUC. Two label-light methods were used to choose it, deliberately **not** simply setting
it to the ~0.97% test-set fraud rate (which would quietly reintroduce the label into an otherwise
unsupervised model, and wouldn't generalize to a real deployment where the true rate is unknown):

1. **A candidate sweep** (0.001 to 0.1), evaluated against labels purely for comparison, not for
   fitting: precision falls steadily as the flagged set grows (21.3% at 0.005 → 6.6% at 0.1) while
   recall climbs (8.5% → 61.5%). None approach XGBoost's 89.7% precision at 99.05% recall.
2. **A label-free elbow in the training anomaly-score distribution.** Per-0.25-percentile deltas
   are essentially flat (~0.0012–0.0018) from p90 to p97, then accelerate sharply: 0.0060 by p98.0,
   0.0093 by p98.75, 0.0130 by p99.0, 0.0299 by p99.5 — a clear "the top ~1% is a different, sparser
   population" shape, found without touching `isFraud` at all.

**Chosen: `contamination = 0.01`**, driven by the elbow (method 2), landing right where the tail
visibly opens up. It's worth noting — as a cross-check, not the justification — that this also lands
close to both the test-set fraud rate (0.97%) and XGBoost's realized flag rate (1.07%), a
reassuring sign the label-free reasoning didn't land somewhere obviously wrong.

## PR-AUC: 0.1022 — an unsupervised ranking evaluated against labels it never saw

**This is not a fair comparison with XGBoost, and shouldn't be read as one.** XGBoost (PR-AUC
0.989184, Phase 3) had direct access to labeled fraud history; Isolation Forest had none. A large
gap here is the expected, correct outcome of comparing a supervised model to an unsupervised one on
a metric that specifically rewards knowing the label — not a sign Isolation Forest is a bad model
at its actual job.

Isolation Forest's PR-AUC is still **~10.5x the no-skill baseline** (0.0097), so its label-blind
ranking does correlate with actual fraud to a real, if modest, degree — confirmed by the anomaly
score distribution (fraud mean 0.543 vs. legitimate mean 0.452, overlapping heavily but shifted).
The concrete reason the correlation isn't stronger: PaySim's dominant fraud signal
(`amount_to_balance_ratio` ≈ 1.0) is a **relationship between two features**, not an extreme value
in any single raw feature — several of XGBoost's highest-confidence true positives (`predict_proba`
≈ 1.0) score at or below the *median* of Isolation Forest's entire training distribution, because
neither the raw `amount` nor the raw `oldbalanceOrg` alone is unusual, only their near-equality is.
A supervised model can be explicitly optimized to find that split; a generic random-partitioning
detector has no particular reason to isolate it.

## What Isolation Forest is actually for here

Not to outscore XGBoost — to catch statistically unusual transactions that don't resemble *any*
labeled fraud XGBoost has learned from, including, hypothetically, fraud patterns that don't exist
yet in training data. XGBoost can only ever learn to flag what looked like fraud in its training
set (the draining pattern); a transaction that's suspicious in some other way would score low on
`predict_proba` almost by definition, no matter how anomalous it looks by other measures.

**PaySim can't fully exercise this advantage** — its synthetic fraud generator only ever produces
one fraud shape, so this test set has no "genuinely novel pattern" for Isolation Forest to uniquely
catch. What the overlap analysis below shows is the honest, empirical answer for *this* dataset —
not a verdict on the general value of anomaly detection.

## Overlap analysis — the actual point of this notebook

| bucket | n | of which fraud | fraud rate in bucket |
|---|---|---|---|
| Both flag | 293 | 293 | 100% |
| XGBoost only | 1,443 | 1,264 | 87.6% |
| Isolation Forest only | 1,123 | 0 | 0% |
| Neither | 159,162 | 15 | 0.009% |

Jaccard overlap (both / either): **0.1025**.

**On this test set, Isolation Forest adds zero incremental true positives beyond XGBoost.** Every
fraud transaction in Isolation Forest's flagged set is already caught by XGBoost too (the "both"
bucket). Isolation Forest's 1,123 uniquely-flagged transactions are **100% false alarms** — mostly
very large `TRANSFER`s with an origin balance of exactly zero and a large pre-existing destination
balance (e.g. a $2.54M transfer from a $0 account into one already holding $5.4M). This is a
genuinely different *kind* of statistical outlier than PaySim's fraud pattern (which drains a
*nonzero* origin balance to near-zero) — exactly the sort of thing an unsupervised detector should
surface — it simply isn't fraud in this dataset.

**The more interesting direction**: 310 of XGBoost's uniquely-caught fraud transactions
(`predict_proba` 0.997–1.000) score *below the median* of Isolation Forest's entire training
distribution — completely unremarkable to it. A $135,100.36 `CASH_OUT` that exactly empties a
$135,100.36 origin account isn't unusual in Isolation Forest's eyes because neither figure alone is
extreme across the dataset; only their equality is suspicious, and that relational signal is
invisible to a detector built around isolating extreme individual values.

## Recommendation: secondary "anomaly flag," not a second fraud model

**Do not surface Isolation Forest as an independent, equally-weighted alert queue.** On this
dataset, that would add 1,123 extra manual reviews (per test-set-sized window) with zero true
positives among them — pure operational noise, no offsetting benefit. It should also never be
blended into a single combined score with XGBoost's fraud probability — averaging the two would
obscure exactly the disagreement cases that are the whole point of having both.

**Do surface it as a distinct, clearly-labeled secondary signal** — e.g. a light "Unusual
transaction pattern" badge shown alongside, not merged into, the XGBoost fraud probability on each
transaction's dashboard view. Its most useful moment is specifically the quadrant this test set
didn't happen to produce any real fraud in: **low XGBoost probability + high Isolation Forest
anomaly score** — a transaction that looks nothing like historical fraud (so XGBoost has no reason
to flag it) but also looks nothing like a normal transaction (so it's still worth a human glance).
That combination is precisely what unsupervised anomaly detection is suited to contribute, even
though it happened to be empty of true fraud in this particular evaluation.

**Never use an Isolation Forest flag to auto-block, override, or replace an XGBoost decision** —
advisory-only, given its demonstrated 0% unique-catch precision here. And in any portfolio-facing
description of this project, Isolation Forest should be framed as "a complementary, unsupervised
signal explored as an anomaly-detection paradigm" — not as "a second fraud-detection model nearly
as good as XGBoost," which the numbers above do not support.

## Known limitation

PaySim's fraud generator produces a single, homogeneous fraud shape (the account-draining pattern).
Isolation Forest's actual selling point — catching a *genuinely novel* fraud pattern XGBoost has
never seen — cannot be empirically demonstrated on this dataset, because no such pattern exists in
it to catch. The 0%-unique-precision result above is accurate for this data, but should not be read
as "Isolation Forest has no value" in a setting with more heterogeneous fraud.
