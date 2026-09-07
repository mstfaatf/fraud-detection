# Case Study

## Problem Statement

A payment has to be scored for fraud before it executes, at the moment a transaction is submitted,
using only the account and transaction state that actually exists at that instant. Nothing that
depends on the transaction having already gone through is fair game. That constraint drives every
other decision in this project: it rules out any feature derived from post-transaction state, no
matter how predictive it looks in hindsight, and it means an explanation for why a transaction was
flagged has to be available in real time too. A fraud system that can't tell an operator (or a
payment processor's own rules layer) why it blocked something is much harder to trust or debug. I
built this pipeline end to end: a real-time scorer, trained and evaluated with that pre-transaction
constraint enforced throughout, with a per-decision SHAP explanation attached to every prediction,
on PaySim, a synthetic but fully interpretable financial transactions dataset.

## Key Technical Decisions

### The leakage decision

`newbalanceOrig` and `newbalanceDest`, the account balances *after* a transaction completes, are
excluded from the feature set entirely, along with anything derived from them. The reasoning holds
regardless of how predictive those fields are: they don't exist yet at real-time decision time, so
using them would be leakage for this use case specifically. This isn't a marginal call. My EDA
found the single strongest raw signal anywhere in the dataset in exactly these excluded fields:
97.7% of fraud transactions drain the origin account to zero, versus 0% of legitimate transactions.
I excluded that signal anyway, on principle, because a payment can't be scored using a balance that
only exists once the payment has already gone through.

### Why PR-AUC, not accuracy or ROC-AUC

The dataset's fraud rate is 0.1291% (roughly 1 in 775). At that rate, accuracy is a meaningless
metric: a classifier that always predicts "legitimate" scores 99.03% accuracy while catching zero
fraud. ROC-AUC is misleading for the same underlying reason: with legitimate transactions
outnumbering fraud roughly 100:1 in the test set, the false-positive-rate axis is dominated by an
enormous negative class, so ROC-AUC can look strong even at operating points with poor real-world
precision. I used PR-AUC (average precision), computed purely from the positive class's
perspective, as the metric throughout this project.

### Class imbalance handling: class-weighting vs. SMOTE

I compared two strategies head to head on identical Logistic Regression models, trained and
evaluated on the same time-based split: `class_weight='balanced'` scored 0.5087 PR-AUC, while SMOTE
(`sampling_strategy=0.1`, fit on the training fold only, inside an `imblearn.pipeline.Pipeline` so
resampling is structurally skipped at predict time) scored 0.6102, a real, non-trivial margin
(+0.1014 PR-AUC, roughly 20% relative). I carried SMOTE forward as the recommended approach. The
added complexity of a resampling pipeline (versus a single `class_weight` constructor argument) was
worth it specifically because the PR-AUC gain was real and meaningful, not a marginal difference
that wouldn't justify the extra moving part, and because the pipeline structure eliminates the
obvious failure mode (resampled synthetic rows leaking into the test fold) by construction rather
than by discipline.

### The two-model layered design: XGBoost (primary) + Isolation Forest (advisory-only)

The deployed system runs two models per transaction, not one. XGBoost is the supervised, primary
scorer: its probability output is what determines `is_fraud`. Isolation Forest runs unsupervised
(fit with no fraud labels at all) as a secondary anomaly signal, surfaced as its own separate field
and never blended into the fraud probability. That split comes from a concrete result, not a
stylistic choice: of 1,572 fraud transactions in the test set, 293 were caught by both models,
1,264 by XGBoost only, and exactly 0 by Isolation Forest only. Isolation Forest's 1,123
uniquely-flagged transactions were **100% false alarms**. None of them were fraud. On this dataset,
Isolation Forest added zero incremental true positives beyond what XGBoost already caught, which is
exactly why I wired it into the system as an advisory signal a human or a downstream rule can look
at, never as something that can independently block a transaction. (I'm scoping that result
deliberately: PaySim's fraud generator produces only one fraud shape, the account-draining pattern,
so this specific evaluation can't demonstrate Isolation Forest's actual selling point, catching a
genuinely novel pattern the supervised model has never seen, because no second pattern exists in
the dataset to catch. The 0%-unique-precision result is accurate here, but it shouldn't be read as
"Isolation Forest has no value" in a setting with more heterogeneous fraud.)

### Threshold selection

I chose the deployed decision threshold (≈0.6145, not the default 0.5) by maximizing precision
subject to recall ≥ 99%, evaluated directly off XGBoost's actual precision-recall curve (92,377
candidate thresholds), landing at precision 0.8969 and recall 0.9905. This is explicitly a
demonstrative choice, not a production one: the 99%-recall target is reasonable for showing the
tradeoff exists and can be tuned, but it isn't derived from real fraud/false-positive cost data,
which doesn't exist for a synthetic, PaySim-based project. A real deployment would set this
threshold from the actual dollar cost of a missed fraud versus the cost of a false decline, and I
don't have access to either.

### SHAP's role and the collinearity finding

SHAP (`TreeExplainer`) is reconstructed fresh from the loaded model at startup for every
prediction, attaching a per-feature explanation to each score rather than leaving the decision
opaque. One finding from applying it is worth stating precisely, because it generalizes well beyond
this project: `is_merchant_dest` and `type_PAYMENT` are perfectly collinear in PaySim (every
`PAYMENT` transaction goes to a merchant, and vice versa, with zero exceptions). The fitted XGBoost
model routes all of that shared signal through `is_merchant_dest`, leaving `type_PAYMENT` with an
exact `0.0` SHAP value on every single test row. SHAP doesn't, and structurally can't, split credit
between the two more sensibly than the model's own gain-based importance did. A feature a fitted
model never splits on has zero effect on that model's output, and therefore zero Shapley value, as
a mathematical necessity, not because SHAP happens to agree with gain. No post-hoc attribution
method, Shapley-based or otherwise, can recover signal from a column a model's training algorithm
routed around. The practical rule this produces: an importance of exactly zero for `type_PAYMENT`
has to be read together with `is_merchant_dest`, which carries 100% of their combined signal.
Presenting it as "transaction type doesn't matter here" would be a misreading of what the number
actually means.

### Docker Compose

A full three-service Docker Compose stack (Postgres, backend, frontend) exists in this repository
as a packaging deliverable and containerization exercise. It's explicitly not part of how I
actually built this project. Real development ran `uvicorn --reload` and `npm run dev` directly on
the host against a local Postgres instance the whole way through, and Compose has no connection to
the live public deployment in either direction: Render runs the backend from a plain git checkout
with no Docker involved at all, and Vercel builds the frontend from its own Git-connected pipeline.
The Compose stack is hard-wired to always use its own local Postgres container rather than
Supabase, specifically so it can never accidentally reach the production database. This is stated
plainly rather than leaving it implied, because conflating "containerized and demoable" with "how
this was actually built and deployed" would misrepresent both.

## Quantified Results

| Model | PR-AUC |
|---|---|
| Logistic Regression, `class_weight='balanced'` | 0.5087 |
| Logistic Regression + SMOTE (0.1 ratio) | 0.6102 |
| Random Forest, `class_weight='balanced'` | 0.999963 |
| **XGBoost, `scale_pos_weight` (computed)** | **0.989184** |

- **Chosen model: XGBoost.** Not the highest PR-AUC (Random Forest's is higher and dominates
  XGBoost's curve at nearly every operating point), but I chose it for roughly 25x faster
  single-transaction inference (~1.6ms vs. ~40ms) and a roughly 92x smaller serialized model
  (0.6MB vs. 55.1MB), both directly relevant to a real-time, one-prediction-per-transaction
  architecture.
- **Chosen threshold: ≈0.6145**, giving precision 0.8969 at recall 0.9905 on the held-out test set.
- **Isolation Forest overlap**: 0 of 1,572 test-set fraud transactions were caught uniquely by
  Isolation Forest; its 1,123 uniquely-flagged transactions were 100% false alarms.
- **Measured real-world cold-start latency**: approximately 95 to 105 seconds, measured directly
  after a genuine ~12-hour-20-minute idle window against the live free-tier Render + Supabase
  deployment (with the keep-alive ping deliberately disabled for the test), roughly 2x an earlier,
  unmeasured estimate of 20 to 50 seconds.

## What This Project Deliberately Is Not

This isn't a production fraud detection system. The dataset is synthetic (PaySim), the decision
threshold is a demonstrative choice rather than one calibrated against real fraud/false-positive
costs, and the (test-mode) Stripe integration maps a real payment onto this model's schema through
several documented simplifications (a synthetic wallet balance stored in Stripe Customer metadata
standing in for `oldbalanceOrg`, a fixed destination balance and transaction type), not a real
payment processor's actual risk data. There's no authentication or authorization layer on the API.
Every endpoint is public by design, with per-IP rate limiting as the only, explicitly demo-scale
protection. None of the four trained models went through a hyperparameter search. I'm stating these
as fixed, load-bearing facts about what this project is, not as gaps waiting to be closed.
