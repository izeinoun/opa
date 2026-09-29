# ML Scoring & Metrics — Learning Notes

*Working notes from building the OPA/PayGuard two-stage risk engine. Plain-English,
grounded in our actual models. Refer back when a metric or model choice feels off.*

---

## The core principle (read this first)

> **Evaluate a model by how its output is *consumed*, not by what's convenient.**

The same trained model can be judged by completely different metrics depending on
whether you use its output as a **ranking/feature**, a **flag**, or a **quantity**.
Most of our confusion came from applying flag-metrics to a model whose output is a
feature. Get the consumption right and the correct metric falls out.

---

## The two-stage pipeline (context)

```
Stage 1 — Provider Reputation  →  P_risk (calibrated probability per provider)
        (RandomForestClassifier)        │
                                         │  used as a FEATURE (a number), not a flag
                                         ▼
Stage 2 — Claim Predictor      →  P(overpayment) per claim (calibrated)
        (RandomForestClassifier)        │
                                         ▼
Audit Plan — gate on probability, rank by EV ($ × P), cut at team capacity
                                         ▼
Rules (detectors / DCE) confirm the findings
```

- **Stage 1** scores *providers*; its number feeds Stage 2 as one input feature.
- **Stage 2** scores *claims*; its calibrated probability drives the audit plan.
- **Cutoffs live at the Audit Plan**, where a threshold is an actual action.

---

## Stage 1: what it actually predicts

- It's a **binary classifier**. One row per provider(-month); features are behavioral
  aggregates (avg units/line, high-value CPT ratio, modifier usage, prior overpayment
  rate, peer deviation, …).
- **Label:** `had_confirmed_overpayment ∈ {0, 1}` — did this provider have ≥1 confirmed
  (RECOVERED) overpayment in the label window?
- **Output:** a *calibrated probability* `P(provider is a "has-overpayments" provider)`
  = **P_risk**. The prediction is continuous (0–1); the **label is binary**.

### Two legitimate uses — and where the cutoff lives

| Use | How the score is consumed | Cutoff? | Metrics that matter |
|---|---|---|---|
| **Feature** (our pipeline) | continuous number into Stage 2 | **No** | AUC + calibration (Brier) |
| **Watchlist / flag** (standalone) | threshold → "risky vs fine" list | **Yes** | precision / recall *at that cutoff* |

The pipeline uses it as a **feature**, so there is no cutoff and precision/recall are
just "what if we flagged at X" curiosities. If we ever want a standalone risky-provider
list, we threshold the *same* probabilities — no retraining needed.

**Is 0.5 the right cutoff for a watchlist?** Only if classes are balanced. They're not
(~24% positive), so a calibrated model keeps most providers under 0.5. The cutoff is an
**operational choice** — set by investigator capacity or a precision target — not a
magic 0.5. (Same lesson as the audit-plan capacity gate.)

---

## Classification vs regression (why the metric changes)

- **Classification w/ probability output** (what we have): predict `P(binary event)`,
  label is 0/1. → use **Brier, log-loss, AUC**, and (only if you threshold) accuracy/
  precision/recall.
- **Regression**: predict a continuous *quantity* (e.g., a provider's overpayment
  *rate*, or expected overpayment *dollars*), label is continuous. → use **RMSE / MAE / R²**.

Same tree family (`RandomForestClassifier` vs `RandomForestRegressor`); which error
metric applies falls straight out of whether the label is a **class** or a **quantity**.

---

## The metric families (Stage 1, and any probability model)

| Metric | Measures | Needs a cutoff? |
|---|---|---|
| **Brier / log-loss** | error of the *probability* vs the 0/1 truth | No |
| **AUC-ROC** | ranking quality (does risk order come out right) | No |
| **Accuracy / Precision / Recall / F1** | correctness *after rounding* the probability to 0/1 at a cutoff | **Yes** |

Accuracy/precision/recall live at **one point** on the ROC curve (one threshold). Brier
and AUC score the raw probability directly. That's why, for a feature/ranking model, the
honest headline metrics are **AUC + Brier**, and precision/recall are secondary
"diagnostics at a nominal cutoff."

---

## Brier score = the RMSE instinct, done right

For a probability-vs-binary prediction, the analog of "sum of squared errors" is the
**Brier score**:

```
Brier = (1/N) · Σ (p_i − y_i)²        where y_i ∈ {0, 1}
```

- It is literally the **mean squared error** between the predicted probability `p_i`
  and the 0/1 outcome `y_i`. (RMSE would be its square root.)
- **Lower = better.** 0 is perfect.
- It rewards *calibration*: a prediction of 0.7 should be right ~70% of the time.
- This is why we surface **Brier (raw → calibrated)** on the Stage-1 card — it's the
  MSE of the probability, and calibration (Platt/isotonic) is what improves it.
- Note: calibration doesn't *always* lower Brier on a small validation fold — that's
  real, not a bug. Compare sigmoid vs isotonic vs none empirically on real data.

---

## AUC-ROC, unpacked

- **AUC = Area Under the Curve; the curve is the ROC** (Receiver Operating Characteristic).
- The ROC curve plots, as you sweep the threshold from 1.0 → 0.0:
  - **y = True Positive Rate (recall)** = TP / (TP + FN) — of the truly risky, what fraction caught.
  - **x = False Positive Rate** = FP / (FP + TN) — of the truly fine, what fraction wrongly flagged.
  - High threshold → bottom-left (0,0); low threshold → top-right (1,1); sweeping traces the curve.
- **Range:** 0.5 = random (the diagonal); 1.0 = perfect (hugs the top-left corner).
- **Probabilistic meaning (the elegant part):**
  > AUC = the probability the model scores a random **positive** higher than a random **negative**.
  So AUC ≈ 0.96 → 96% of the time it ranks a truly-risky provider above a truly-fine one.
  Pure ordering — which is why it's the right metric for a ranking/feature model.
- **Why AUC is threshold-free:** the ROC curve is generated by sweeping *all* thresholds,
  and AUC integrates over the whole thing. It can't depend on any single cutoff — it
  already accounts for every cutoff at once. (This is why AUC didn't move when we changed
  the decision threshold; only precision/recall moved.)

### PR-AUC for rare events
When positives are rare (overpayments!), also watch the **Precision–Recall curve** and its
area (**PR-AUC / average precision**). ROC's FPR denominator (all negatives) is huge on
rare-event problems, so ROC can look flatteringly good. PR-AUC focuses on the positive
class. (The Stage-2 spec lists `avg_precision_mean` for exactly this reason.)

---

## Calibration (why we bother)

- A model is **calibrated** if predicted probabilities match observed frequencies
  (of everything it calls "0.30", ~30% are actually positive).
- Tree ensembles (RF/XGBoost) produce **over-confident, poorly-calibrated** raw scores →
  we wrap them in **Platt (sigmoid)** or **isotonic** calibration on a held-out fold.
- **Why it's non-negotiable here:** the audit plan computes **EV = probability × dollars**.
  That only means anything if the probability is a *true frequency*. An uncalibrated
  "decision score" (e.g., XGBoost + `scale_pos_weight` tuned around a 0.5 threshold)
  would distort EV. → We chose **RF + calibration** over the spec's XGBoost for this reason.

---

## Quick decision guide

- **Output used as a feature or ranking?** → judge by **AUC** (+ **PR-AUC** if rare) and
  **Brier**. No cutoff.
- **Output used as a flag / list?** → pick a cutoff by **capacity or a precision target**
  (not 0.5 blindly on imbalanced data), then judge by **precision/recall/F-beta** at it.
- **Predicting a continuous quantity?** → it's regression: use **RMSE/MAE/R²**.
- **Probabilities feeding a dollar calculation (EV)?** → they **must be calibrated**;
  check **Brier raw → calibrated**.
- **Rare positives?** → prefer **PR-AUC / average precision** over ROC-AUC.

---

*See also: `docs/OPA_Stage2_Feature_Specification_v1.3` (the Stage 2 feature design),
`server/app/ml/train_billing_variance.py` (Stage 1 trainer),
`server/app/ml/train_claim_predictor.py` (Stage 2 trainer).*
