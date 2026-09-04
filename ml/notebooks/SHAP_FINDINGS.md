# SHAP Explainability Findings — Phase 4

Full notebook: `06_shap_explainability.ipynb`. Scope note: this covers **SHAP explainability on the
chosen XGBoost model only**. Isolation Forest anomaly detection (also listed under Phase 4 in
`CLAUDE.md`) is a separate, not-yet-started piece of work.

Model, split, and threshold are unchanged from Phase 3: XGBoost (`n_estimators=200`, `max_depth=6`,
`learning_rate=0.1`, `scale_pos_weight=974.05` computed from the train fold), the adjusted
time-based split (`step <= 575`), and the chosen threshold (re-derived here as `0.614494`, matching
the `~0.6145` documented in `CLAUDE.md` and reproducing `PHASE3_FINDINGS.md`'s confusion matrix
exactly: TP=1,557, FP=179, FN=15, TN=160,270). No new modeling decisions were made in this phase —
this is explanation of an existing, already-chosen model, not a new one.

## Global feature importance: SHAP vs. built-in gain/weight

| feature | gain % | SHAP mean(&#124;value&#124;) % | gain rank | SHAP rank |
|---|---|---|---|---|
| `amount_to_balance_ratio` | 90.1% | 47.6% | 1 | 1 |
| `is_merchant_dest` | 3.2% | 14.3% | 2 | 2 |
| `type_CASH_IN` | 1.7% | 7.8% | 4 | 3 |
| `oldbalanceDest` | 0.5% | 7.3% | 7 | 4 |
| `amount` | 2.5% | 4.9% | 3 | 5 |
| `day_of_week` | 0.3% | 4.7% | 9 | 6 |
| `oldbalanceOrg` | 0.5% | 4.4% | 5 | 7 |
| `type_CASH_OUT` | 0.4% | 4.0% | 8 | 8 |
| `hour_of_day` | 0.2% | 3.6% | 10 | 9 |
| `type_TRANSFER` | 0.5% | 1.3% | 6 | 10 |
| `type_DEBIT` | 0.08% | 0.1% | 11 | 11 |
| `type_PAYMENT` | 0.0% | 0.0% | 12 | 12 |

**`amount_to_balance_ratio` dominates by every method** — this is the same PaySim account-draining
signal identified in Phase 3, now confirmed a third way. Beyond that, though, **SHAP tells a
meaningfully different story about the rest of the model than gain does**: gain-based importance
concentrates almost everything outside the top feature into single digits, while SHAP spreads real,
comparable weight (3.6%-14.3% each) across eight different features. This is an expected
consequence of what the two metrics measure — gain rewards whichever feature produces the single
biggest average loss improvement at a split (which one dominant, extremely informative feature will
usually win), while `mean(|SHAP|)` measures how much every feature actually moves individual
predictions, which surfaces secondary, corroborating signals (a destination account's pre-existing
balance, day of week) more evenly. The rank *order* of the top two features is actually stable
between the two methods (`amount_to_balance_ratio` #1, `is_merchant_dest` #2 in both) — it's the
magnitude gap between them, and the shape of everything below, that diverges.

## Collinearity resolution: `is_merchant_dest` / `type_PAYMENT`

This directly answers the question `CLAUDE.md`'s Phase 3 forward-note raised: does SHAP attribute
credit between this perfectly-collinear pair more sensibly than the built-in importances did?

**No — SHAP shows the exact same zero, and it can't do otherwise.** `type_PAYMENT` has a SHAP
value of exactly `0.0` on all 162,021 test-set rows, identical to its gain and weight importance.
This isn't SHAP independently confirming the built-in metrics; it's a direct mathematical
consequence of this specific fitted model never splitting on `type_PAYMENT` in any of its 200
trees. A feature a model never branches on cannot change that model's output for any input — and
SHAP measures exactly that effect, so its value there is trivially zero regardless of whether the
feature carries real-world signal.

**The generalizable finding**: SHAP explains a *fitted model as it actually behaves*, not the
"true" importance of a feature the model happened not to use. Comparing the three models trained so
far on this same collinear pair — Logistic Regression split credit evenly (L2's minimum-norm
solution under exact collinearity), Random Forest split it unevenly but nonzero on both sides
(bagging gives different trees a chance to use either column), XGBoost collapsed it entirely onto
one column (greedy sequential boosting has no such randomness) — each reflects a genuine property
of *that training algorithm*, not a difference in how well each one's chosen explanation method can
see through to the truth. No post-hoc attribution method, gain-based or SHAP-based, can retroactively
recover signal in a column a model never used.

**Where SHAP does add something new**: it puts a concrete number on how much of the model's overall
decision-making this merchant/non-merchant signal accounts for — **14.3%** of total
`mean(|SHAP|)`, entirely via `is_merchant_dest` — versus gain's much smaller **3.2%** for the same
combined signal. So even though SHAP can't split credit between the two collinear columns any more
sensibly than gain did, it reveals the underlying signal matters roughly **4.5x more** to this
model's actual predictions than gain-based importance alone would suggest.

**Practical rule going forward**: any SHAP output on this model — including whatever the eventual
dashboard shows per transaction — must not treat `type_PAYMENT`'s zero contribution as "transaction
type doesn't matter here." It must be read together with `is_merchant_dest`, which is carrying all
of that shared signal.

## Local explanations (plain English)

Four examples, one per confusion-matrix category, all drawn from the test set at the chosen
threshold (≈0.6145). "Pushes the score up/down" refers to the model's internal fraud score before
the final yes/no decision — the direction matters more than the exact number.

**1. Correctly caught fraud (true positive).** A $25,040.78 transfer that emptied the sending
account down to the last cent, sent to an account that had nothing in it beforehand. The model was
essentially certain (>99.99% confidence) this was fraud. The single biggest reason: the transaction
drained the sender's balance almost exactly to zero — the same signature seen in nearly every
fraud case in this dataset — and the fact that it was a transfer (rather than, say, a regular
purchase) added to the suspicion.

**2. A false alarm (false positive).** A $43,446.49 cash-out that also drained almost the entire
sending balance — which is why the model flagged it (>99% confidence) — but this one went to an
account that already held nearly $118,000. A real fraud "drop" account in this dataset almost
always starts out empty; this receiving account looking well-established pulled the score down a
little, but not nearly enough to outweigh how extreme the draining pattern was. In plain terms: this
transaction *looked* like fraud by the model's main rule of thumb, and wasn't — an understandable
mistake, not an obviously broken one.

**3. A missed fraud case (false negative) — arguably the most interesting example.** A $40,873.25
cash-out that, again, drained the sending account down to the cent — exactly the same red flag as
example 1. But this one moved money into an account that already held over $905,000. That looks,
on paper, like paying into an established, legitimate account rather than the usual empty
fraud-drop account, and it was enough to pull the model's confidence down to just under the
threshold (52% vs. the ~61% bar), so this one slipped through. The model didn't miss a hidden
pattern — it correctly noticed the draining behavior and then got talked out of it by a
misleadingly reassuring destination balance.

**4. An everyday transaction, correctly ignored (true negative).** A $561.22 purchase at a
merchant, drawn from an account that still had most of its $1,732 balance left afterward. The model
scored this as almost zero risk (under 0.001%), driven almost entirely by two things pointing the
same direction: the money went to a merchant (a normal purchase pattern, not a person-to-person
transfer), and only a small fraction of the account's balance was spent. Note: this transaction's
merchant destination is the same underlying fact as it being a "payment" type — but per the
collinearity finding above, the model's explanation attributes 100% of that "looks normal" credit to
"went to a merchant," and none to "was a payment," which is a property of how this model happened to
learn the pattern, not evidence that the payment type doesn't matter.

## Reuse for the backend

The trained model, the fitted SHAP explainer, and the exact feature/threshold metadata needed to
score and explain a single real-time transaction are saved to `ml/models/` (`xgboost_model.pkl`,
`shap_explainer.pkl`, `model_metadata.json` — gitignored, consistent with the rest of `ml/models/`).
This is the first notebook in the project to serialize anything; every earlier notebook retrained
from scratch since nothing downstream needed to reuse a fitted artifact until now. See the
notebook's final section for the full reuse plan, including what changes when this gets called from
FastAPI and an explicit warning to future backend code about the `is_merchant_dest`/`type_PAYMENT`
collinearity when building any per-transaction explanation response.
