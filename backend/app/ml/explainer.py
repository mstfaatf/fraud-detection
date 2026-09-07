"""Builds a SHAP TreeExplainer fresh from the loaded XGBoost model at startup.

Deliberately does NOT unpickle ml/models/shap_explainer.pkl. Per the version-
compatibility caveat documented in CLAUDE.md (Known Limitations) and
ml/notebooks/SHAP_FINDINGS.md (Phase 4 part 1): shap_explainer.pkl was pickled
against whatever shap/xgboost versions happened to be installed when it was
created, with no version pin recorded in either requirements.txt, so unpickling
it in the backend's own environment could silently break or produce different
explanations if versions drift. Reconstructing is cheap (<0.05s, per
06_shap_explainability.ipynb) and sidesteps the compatibility question
entirely.
"""

from __future__ import annotations

from typing import Any

import shap


def build_explainer(model: Any) -> shap.TreeExplainer:
    return shap.TreeExplainer(model)
