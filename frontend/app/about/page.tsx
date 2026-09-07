import { Card } from "@/components/ui/card";
import { StatTile } from "@/components/ui/stat-tile";

type Decision = {
  headline: string;
  reasoning: string;
};

const DECISIONS: Decision[] = [
  {
    headline: "Excluding post-transaction balances",
    reasoning:
      "I left newbalanceOrig and newbalanceDest out of the model entirely. They do not exist yet at the moment a payment needs to be scored, even though they carry the strongest raw signal in the dataset (97.7% of fraud drains the origin account to zero).",
  },
  {
    headline: "PR-AUC over accuracy or ROC-AUC",
    reasoning:
      "At a 0.13% fraud rate, accuracy is meaningless (99.03% by always guessing legitimate) and ROC-AUC is misleading too, so I used PR-AUC, scored purely from the positive class, as the metric throughout.",
  },
  {
    headline: "SMOTE over plain class weighting",
    reasoning:
      "class_weight='balanced' scored 0.5087 PR-AUC on Logistic Regression. SMOTE, fit on the training fold only, scored 0.6102, a real 20% relative gain that justified the added pipeline complexity.",
  },
  {
    headline: "XGBoost plus Isolation Forest, never blended",
    reasoning:
      "XGBoost makes the fraud call. Isolation Forest runs as a secondary, advisory signal only, because in evaluation it caught zero fraud transactions uniquely and its 1,123 unique flags were entirely false alarms.",
  },
  {
    headline: "A provisional decision threshold",
    reasoning:
      "The ~0.6145 threshold maximizes precision at 99% recall on the evaluation set. It's a reasoned demo choice, not one calibrated against real fraud or false-positive costs, which don't exist for a synthetic dataset.",
  },
  {
    headline: "SHAP, and a real limit of explainability",
    reasoning:
      "Every prediction ships with a SHAP explanation. Two features, is_merchant_dest and type_PAYMENT, are perfectly collinear in this data, and SHAP can't split credit between them any better than the model's own training did. That's a mathematical fact about a feature the model never split on, not a shortcoming of SHAP.",
  },
  {
    headline: "Docker Compose for practice, not for the demo",
    reasoning:
      "A full Docker Compose stack exists in this repo for local convenience and containerization practice. I never used it to build this project (that was always uvicorn --reload plus npm run dev), and it has no connection to the live deployment you're looking at right now.",
  },
];

const MODEL_RESULTS = [
  { model: "Logistic Regression (class_weight='balanced')", prAuc: "0.5087", chosen: false },
  { model: "Logistic Regression + SMOTE", prAuc: "0.6102", chosen: false },
  { model: "Random Forest (class_weight='balanced')", prAuc: "0.999963", chosen: false },
  { model: "XGBoost (chosen)", prAuc: "0.989184", chosen: true },
];

const NOT_LIST = [
  {
    headline: "Not a production fraud system.",
    body: "This is a portfolio project built to demonstrate real engineering practice on a synthetic dataset, not to handle real-world payment volume.",
  },
  {
    headline: "Not a real payment processor integration.",
    body: "The Stripe flow runs entirely in test mode against a synthetic wallet balance I invented for this demo. No real payment processor ever sees this model's decision.",
  },
  {
    headline: "Not a production-calibrated threshold.",
    body: "The decision threshold is a reasoned demo choice, not one derived from real fraud or false-positive costs.",
  },
];

export default function AboutPage() {
  return (
    <div className="max-w-3xl">
      <h1 className="font-display text-3xl text-text">About</h1>
      <p className="mt-1 font-mono text-xs uppercase tracking-wide text-text-faint">
        By Mustafa Atif
      </p>

      <p className="mt-4 text-text-muted">
        I built this to score financial transactions for fraud in real time, using only the
        information actually available before a payment executes, and to explain every decision
        the model makes rather than leaving it as a black box. It runs a full stack end to end: a
        FastAPI backend, a trained XGBoost classifier, SHAP explanations, and this live Next.js
        dashboard, deployed and reachable right now, not just described in a repository.
      </p>

      <h2 className="mt-10 font-display text-xl text-text">Key decisions</h2>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {DECISIONS.map((decision) => (
          <Card key={decision.headline}>
            <p className="font-medium text-text">{decision.headline}</p>
            <p className="mt-1.5 text-sm text-text-muted">{decision.reasoning}</p>
          </Card>
        ))}
      </div>

      <h2 className="mt-10 font-display text-xl text-text">Results</h2>
      <Card className="mt-4 !p-0">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-text-faint">
              <th className="px-4 py-3 font-mono text-[11px] font-normal uppercase tracking-wide">
                Model
              </th>
              <th className="px-4 py-3 text-right font-mono text-[11px] font-normal uppercase tracking-wide">
                PR-AUC
              </th>
            </tr>
          </thead>
          <tbody>
            {MODEL_RESULTS.map((row) => (
              <tr key={row.model} className="border-b border-border last:border-0">
                <td
                  className={`px-4 py-3 font-mono ${row.chosen ? "text-accent" : "text-text-muted"}`}
                >
                  {row.model}
                </td>
                <td
                  className={`px-4 py-3 text-right font-mono ${
                    row.chosen ? "font-medium text-accent" : "text-text"
                  }`}
                >
                  {row.prAuc}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatTile
          label="Chosen model"
          value="XGBoost"
          caption="threshold ≈0.6145, ~25x faster inference than Random Forest"
        />
        <StatTile
          label="Measured cold start"
          value="~95-105s"
          caption="real overnight-idle test, keep-alive disabled"
        />
        <StatTile
          label="Isolation Forest overlap"
          value="0 unique catches"
          caption="out of 1,572 fraud rows in the test set"
        />
      </div>

      <h2 className="mt-10 font-display text-xl text-text">What this deliberately is not</h2>
      <ul className="mt-4 space-y-3">
        {NOT_LIST.map((item) => (
          <li key={item.headline} className="text-text-muted">
            <span className="font-medium text-text">{item.headline}</span> {item.body}
          </li>
        ))}
      </ul>
    </div>
  );
}
